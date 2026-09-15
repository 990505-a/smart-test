"""Offline teaching model, not a Pi port or an LLM client. Python 3.10+."""

from dataclasses import dataclass
from typing import Callable


@dataclass
class Tool:
    description: str
    parameters: dict
    execute: Callable[..., str]


def add(a: int, b: int) -> str:
    return str(a + b)


TOOLS = {
    "add": Tool(
        description="Add two integers.",
        parameters={
            "type": "object",
            "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
            "required": ["a", "b"],
            "additionalProperties": False,
        },
        execute=add,
    )
}


def validate_arguments(args: dict, schema: dict) -> dict:
    # This demo supports exactly the flat, required-integer schema used above.
    if not isinstance(args, dict) or set(args) != set(schema["required"]):
        raise ValueError("Expected exactly the required argument names")
    if any(type(value) is not int for value in args.values()):
        raise ValueError("All arguments must be integers (not booleans)")
    return args


def execute_tool(call: dict, tools: dict[str, Tool]) -> dict:
    try:
        tool = tools[call["name"]]
        args = validate_arguments(call["arguments"], tool.parameters)
        result, is_error = tool.execute(**args), False
    except (KeyError, ValueError, TypeError) as error:
        result, is_error = f"{type(error).__name__}: {error}", True
    return {
        "role": "toolResult",
        "toolCallId": call["id"],
        "toolName": call["name"],
        "content": [{"type": "text", "text": result}],
        "isError": is_error,
    }


def run_agent(user_text, model, tools, max_turns=5, trace=print):
    messages = [{"role": "user", "content": user_text}]
    specs = [
        {"name": name, "description": tool.description, "parameters": tool.parameters}
        for name, tool in tools.items()
    ]
    for turn in range(max_turns):
        reply = model(messages, specs)
        messages.append(reply)
        trace(f"model turn {turn + 1}: {reply}")
        if reply.get("stopReason") in {"error", "aborted", "length"}:
            raise RuntimeError("Model failed, was cancelled, or returned truncated output")
        calls = [block for block in reply["content"] if block["type"] == "toolCall"]
        if not calls:
            return messages
        for call in calls:
            result = execute_tool(call, tools)
            messages.append(result)
            trace(f"tool result: {result}")
    raise RuntimeError("Turn budget exhausted; no successful final answer")


def scripted_model(messages, tool_specs):
    """A fixed stand-in for the model, only for the 23 + 19 lesson."""
    if messages[-1]["role"] == "user":
        return {
            "role": "assistant",
            "stopReason": "toolUse",
            "content": [{
                "type": "toolCall", "id": "call-1", "name": "add",
                "arguments": {"a": 23, "b": 19},
            }],
        }
    result = messages[-1]
    text = result["content"][0]["text"]
    return {
        "role": "assistant",
        "stopReason": "stop",
        "content": [{"type": "text", "text": f"Tool reported: {text}"}],
    }


if __name__ == "__main__":
    history = run_agent("Use add to calculate 23 + 19", scripted_model, TOOLS)
    print("\nMessage roles:", [message["role"] for message in history])
    print("Final answer:", history[-1]["content"][0]["text"])
