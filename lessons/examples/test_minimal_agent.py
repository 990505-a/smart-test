import unittest

from minimal_agent import TOOLS, execute_tool, run_agent, scripted_model


def quiet(_message):
    pass


class AgentLoopTests(unittest.TestCase):
    def test_tool_result_is_visible_to_second_model_call(self):
        history = run_agent("23 + 19", scripted_model, TOOLS, trace=quiet)
        self.assertEqual([m["role"] for m in history], ["user", "assistant", "toolResult", "assistant"])
        self.assertEqual(history[2]["content"][0]["text"], "42")
        self.assertEqual(history[2]["toolCallId"], history[1]["content"][0]["id"])
        self.assertEqual(history[-1]["content"][0]["text"], "Tool reported: 42")

    def test_unknown_tool_becomes_error_result(self):
        result = execute_tool({"id": "x", "name": "missing", "arguments": {}}, TOOLS)
        self.assertTrue(result["isError"])
        self.assertEqual(result["toolCallId"], "x")

    def test_bad_argument_types_are_rejected(self):
        for args in ({"a": "23", "b": 19}, {"a": True, "b": 19}, {"a": 23}):
            with self.subTest(args=args):
                result = execute_tool({"id": "x", "name": "add", "arguments": args}, TOOLS)
                self.assertTrue(result["isError"])

    def test_run_has_a_turn_budget(self):
        def looping_model(messages, specs):
            return scripted_model([{"role": "user"}], specs)
        with self.assertRaisesRegex(RuntimeError, "Turn budget exhausted"):
            run_agent("loop", looping_model, TOOLS, max_turns=2, trace=quiet)

    def test_truncated_call_is_not_executed(self):
        def truncated_model(messages, specs):
            reply = scripted_model(messages, specs)
            reply["stopReason"] = "length"
            return reply
        with self.assertRaisesRegex(RuntimeError, "truncated"):
            run_agent("23 + 19", truncated_model, TOOLS, trace=quiet)

    def test_model_sees_descriptions_not_executable_functions(self):
        def inspect_model(messages, specs):
            self.assertEqual(set(specs[0]), {"name", "description", "parameters"})
            return {"role": "assistant", "content": [{"type": "text", "text": "done"}]}
        self.assertEqual(len(run_agent("hello", inspect_model, TOOLS, trace=quiet)), 2)


if __name__ == "__main__":
    unittest.main()
