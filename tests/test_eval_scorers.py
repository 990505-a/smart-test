"""确定性打分器测试（``src/app/eval/scorers.py``）。

打分器决定每一条用例得几分，而分数又是门禁的输入——这一层此前同样零覆盖。
覆盖范围：五个确定性打分器各自的"有期望/无期望/命中/未命中"四条分支、
``WebUiExecutionResults`` 对 Playwright 报告解析的边界（空报告不产出分数）、
以及 ``score_run`` 的**降级语义**：一个打分器抛错不能让这一项丢掉其它分数。
"""

from __future__ import annotations

import asyncio

import pytest

from src.app.eval.dataset import EvalItem, Expectations, ToolExpectation
from src.app.eval.scorers import (
    EvidenceExists,
    FinalResponseContains,
    ForbiddenContent,
    ToolCallSequence,
    ToolErrorBudget,
    WebUiExecutionResults,
    score_run,
)
from src.app.eval.tracing import RunTrace, ToolSpan


def _record(*, output: str = "", expected: Expectations | None = None,
            tools: list[tuple[str, bool]] | None = None,
            evidence: list[dict] | None = None):
    """构造一条待打分的运行记录。tools 是 (名字, 是否报错) 列表。"""
    item = EvalItem(id="item-1", input="做点什么", expected=expected)
    trace = RunTrace(session_id="sess-1", output=output)
    for index, (name, is_error) in enumerate(tools or []):
        trace.tools.append(ToolSpan(
            call_id=f"call-{index}", name=name, arguments={},
            started_at=0.0, ended_at=1.0, is_error=is_error,
        ))
    from src.app.eval.scorers import RunRecord
    return RunRecord(item=item, trace=trace, duration_ms=12, evidence=list(evidence or []))


def _score(scorer, record) -> list:
    return asyncio.run(scorer.score(record))


class TestFinalResponseContains:
    def test_no_expectation_produces_no_score(self):
        assert _score(FinalResponseContains(), _record(output="随便")) == []

    def test_hit_is_true(self):
        record = _record(output="登录成功，跳转到首页",
                         expected=Expectations(contains=["首页", "登录成功"]))
        score = _score(FinalResponseContains(), record)[0]
        assert score.name == "task_output_match"
        assert score.value is True
        assert "命中" in score.comment

    def test_miss_is_false_and_names_what_was_expected(self):
        record = _record(output="无法登录",
                         expected=Expectations(contains=["首页"]))
        score = _score(FinalResponseContains(), record)[0]
        assert score.value is False
        assert "首页" in score.comment


class TestForbiddenContent:
    def test_absent_forbidden_content_is_true(self):
        record = _record(output="一切正常",
                         expected=Expectations(not_contains=["500", "报错"]))
        assert _score(ForbiddenContent(), record)[0].value is True

    def test_present_forbidden_content_is_false(self):
        record = _record(output="页面返回 500",
                         expected=Expectations(not_contains=["500"]))
        score = _score(ForbiddenContent(), record)[0]
        assert score.value is False
        assert "500" in score.comment


class TestToolCallSequence:
    def test_subsequence_mode_allows_extra_calls_between(self):
        record = _record(
            expected=Expectations(tools=ToolExpectation(sequence=["ls", "read_file"])),
            tools=[("ls", False), ("grep", False), ("read_file", False)])
        assert _score(ToolCallSequence(), record)[0].value is True

    def test_subsequence_mode_fails_when_order_is_wrong(self):
        record = _record(
            expected=Expectations(tools=ToolExpectation(sequence=["read_file", "ls"])),
            tools=[("ls", False), ("read_file", False)])
        assert _score(ToolCallSequence(), record)[0].value is False

    def test_exact_mode_rejects_extra_calls(self):
        record = _record(
            expected=Expectations(tools=ToolExpectation(
                sequence=["ls", "read_file"], mode="exact")),
            tools=[("ls", False), ("grep", False), ("read_file", False)])
        assert _score(ToolCallSequence(), record)[0].value is False

    def test_exact_mode_accepts_an_identical_sequence(self):
        record = _record(
            expected=Expectations(tools=ToolExpectation(
                sequence=["ls", "read_file"], mode="exact")),
            tools=[("ls", False), ("read_file", False)])
        assert _score(ToolCallSequence(), record)[0].value is True


class TestToolErrorBudget:
    def test_reports_the_raw_error_count(self):
        record = _record(expected=Expectations(max_tool_errors=2),
                         tools=[("ls", False), ("grep", True), ("read_file", True)])
        score = _score(ToolErrorBudget(), record)[0]
        assert score.name == "tool_errors"
        assert score.value == 2
        assert score.data_type == "NUMERIC"

    def test_no_budget_produces_no_score(self):
        assert _score(ToolErrorBudget(), _record(tools=[("ls", True)])) == []


class TestEvidenceExists:
    def test_exact_path_hit(self):
        record = _record(expected=Expectations(evidence="report/index.html"),
                         evidence=[{"name": "report/index.html"}])
        assert _score(EvidenceExists(), record)[0].value is True

    def test_single_star_wildcard(self):
        record = _record(expected=Expectations(evidence="screens/*.png"),
                         evidence=[{"name": "screens/home.png"}])
        assert _score(EvidenceExists(), record)[0].value is True

    def test_miss_lists_what_was_actually_produced(self):
        record = _record(expected=Expectations(evidence="report/index.html"),
                         evidence=[{"name": "traces/trace.zip"}])
        score = _score(EvidenceExists(), record)[0]
        assert score.value is False
        assert "traces/trace.zip" in score.comment

    def test_path_key_is_accepted_as_well_as_name(self):
        record = _record(expected=Expectations(evidence="a/b.json"),
                         evidence=[{"path": "a/b.json"}])
        assert _score(EvidenceExists(), record)[0].value is True


class TestWebUiExecutionResults:
    def _payload(self, expected: int, unexpected: int, *, status: str = "passed") -> str:
        import json
        return json.dumps({"status": status,
                           "report": {"stats": {"expected": expected,
                                                "unexpected": unexpected,
                                                "skipped": 0}}})

    def test_emits_rate_and_all_passed(self):
        record = _record(tools=[("webui_run_spec", False)])
        record.trace.tools[0].output = self._payload(3, 1)
        rate, all_passed = _score(WebUiExecutionResults(), record)
        assert rate.name == "webui_case_pass_rate"
        assert rate.value == pytest.approx(0.75)
        assert all_passed.name == "webui_cases_all_passed"
        assert all_passed.value is False

    def test_all_green(self):
        record = _record(tools=[("webui_run_spec", False)])
        record.trace.tools[0].output = self._payload(4, 0)
        rate, all_passed = _score(WebUiExecutionResults(), record)
        assert rate.value == pytest.approx(1.0)
        assert all_passed.value is True

    def test_no_execution_at_all_produces_no_score(self):
        """没跑过 webui_run_spec → 不产出分数（而不是记 0 分）。

        区分很重要：0 分表示"跑了但全挂"，不产出表示"这一项没有执行证据"，
        后者在门禁里走的是 fail-closed 的"该分数从未产出"分支。
        """
        assert _score(WebUiExecutionResults(), _record(output="我只是回答了一下")) == []

    def test_empty_report_is_not_counted_as_a_run(self):
        record = _record(tools=[("webui_run_spec", False)])
        record.trace.tools[0].output = self._payload(0, 0)
        assert _score(WebUiExecutionResults(), record) == []

    def test_markdown_fenced_json_is_rehydrated(self):
        record = _record(tools=[("webui_run_spec", False)])
        record.trace.tools[0].output = "```json\n" + self._payload(2, 0) + "\n```"
        assert _score(WebUiExecutionResults(), record)[0].value == pytest.approx(1.0)


class TestScoreRunDegradation:
    def test_a_throwing_scorer_does_not_void_the_others(self):
        """打分器抛错 → 降级成一条 CATEGORICAL 备注，其余分数照常产出。

        这条是"judge 端点挂了不该让确定性分数一起消失"的实现保证。
        """

        class _Boom:
            name = "boom"

            async def score(self, record):
                raise RuntimeError("judge endpoint down")

        record = _record(output="登录成功", expected=Expectations(contains=["登录成功"]))
        scores = asyncio.run(score_run([FinalResponseContains(), _Boom()], record))

        by_name = {s.name: s for s in scores}
        assert by_name["task_output_match"].value is True
        assert by_name["boom_error"].data_type == "CATEGORICAL"
        assert "judge endpoint down" in by_name["boom_error"].value

    def test_all_scores_are_collected_in_order(self):
        record = _record(output="500 错误",
                         expected=Expectations(contains=["500"], not_contains=["500"]))
        scores = asyncio.run(score_run(
            [FinalResponseContains(), ForbiddenContent()], record))
        assert [s.name for s in scores] == ["task_output_match", "no_forbidden_content"]
        assert [s.value for s in scores] == [True, False]
