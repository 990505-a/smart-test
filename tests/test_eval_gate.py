"""门禁表达式测试（``src/app/eval/gate.py``）。

门禁是平台对外承诺"能进 CI"的全部依据——``python -m src.app.eval.cli --gate ...``
的退出码直接决定流水线红绿，但在本轮之前它**没有任何测试**。这里覆盖三件事：

1. 语法解析：四种聚合函数、五种比较符、``all()`` 免比较、``&&`` 与 ``,`` 等价；
2. 求值语义：布尔按 1/0 聚合、CATEGORICAL 不参与、多子句全过才算过；
3. **fail-closed**：门禁写了一个没人产出的分数名时判失败而不是"没有约束"——
   这是最要紧的一条，写错名字若无副作用，门禁就形同虚设。
"""

from __future__ import annotations

import pytest

from src.app.eval.gate import parse_gate, evaluate_gate
from src.app.eval.scorers import ScoreResult


def _bool(name: str, value: bool) -> ScoreResult:
    return ScoreResult(name=name, value=value, data_type="BOOLEAN")


def _num(name: str, value: float) -> ScoreResult:
    return ScoreResult(name=name, value=value, data_type="NUMERIC")


def _cat(name: str, value: str) -> ScoreResult:
    return ScoreResult(name=name, value=value, data_type="CATEGORICAL")


class TestParse:
    def test_parses_all_four_aggregations(self):
        clauses = parse_gate("avg(a)>=0.8 && min(b)>=0.6, max(c)<=2")
        assert [(c.fn, c.score, c.op, c.threshold) for c in clauses] == [
            ("avg", "a", ">=", 0.8),
            ("min", "b", ">=", 0.6),
            ("max", "c", "<=", 2.0),
        ]

    def test_all_takes_no_comparison(self):
        clause = parse_gate("all(tool_sequence)")[0]
        assert clause.fn == "all" and clause.op is None and clause.threshold is None

    def test_comma_and_ampersand_are_equivalent(self):
        assert parse_gate("avg(a)>=1,min(b)>=1") == parse_gate("avg(a)>=1&&min(b)>=1")

    def test_score_name_keeps_underscores_and_hyphens(self):
        # 分数名里两种字符都常见：task_output_match、webui_case_pass_rate…
        assert parse_gate("avg(task_output_match)>=1")[0].score == "task_output_match"
        assert parse_gate("min(task-output-match)>=1")[0].score == "task-output-match"

    @pytest.mark.parametrize("expression, message", [
        ("", "表达式为空"),
        ("   ", "表达式为空"),
        ("avg(a)", "缺少比较"),            # 只有 all() 可以不带比较
        ("median(a)>=1", "无法解析"),
        ("avg(a) => 1", "无法解析"),
        ("avg(a)>=abc", "无法解析"),
    ])
    def test_syntax_errors_name_the_offender(self, expression, message):
        with pytest.raises(ValueError, match=message):
            parse_gate(expression)

    def test_render_round_trips(self):
        assert [c.render() for c in parse_gate("avg(a)>=0.8,all(b)")] == [
            "avg(a)>=0.8", "all(b)"]


class TestEvaluate:
    def test_avg_across_rows_and_items(self):
        rows = [[_num("judge", 1.0)], [_num("judge", 0.5)], [_num("judge", 0.0)]]
        result = evaluate_gate("avg(judge)>=0.5", rows)
        assert result.ok is True
        assert "实测 0.5" in result.lines[0]

    def test_avg_below_threshold_fails(self):
        assert evaluate_gate("avg(judge)>=0.9", [[_num("judge", 0.5)]]).ok is False

    def test_booleans_aggregate_as_one_and_zero(self):
        rows = [[_bool("task_output_match", True)], [_bool("task_output_match", False)]]
        assert evaluate_gate("avg(task_output_match)>=0.5", rows).ok is True
        assert evaluate_gate("min(task_output_match)>=1", rows).ok is False
        assert evaluate_gate("all(task_output_match)", rows).ok is False

    def test_all_passes_only_when_every_item_is_true(self):
        rows = [[_bool("ok", True)], [_bool("ok", True)]]
        assert evaluate_gate("all(ok)", rows).ok is True

    def test_max_is_a_guardrail_on_the_worst_item(self):
        rows = [[_num("tool_errors", 0)], [_num("tool_errors", 5)]]
        assert evaluate_gate("max(tool_errors)<=2", rows).ok is False
        assert evaluate_gate("max(tool_errors)<=5", rows).ok is True

    def test_categorical_scores_do_not_enter_the_numbers(self):
        """CATEGORICAL 是"这一项没算出数"的标记（如打分器抛错），不能当 0 分算。

        否则一个 judge 端点挂掉会把 avg 拖垮，门禁判失败的原因就变成了基础设施
        故障——那不是它在测的东西。
        """
        rows = [[_num("judge", 1.0), _cat("llm_judge_error", "endpoint down")]]
        assert evaluate_gate("avg(judge)>=1", rows).ok is True

    def test_only_categorical_yields_fail_closed(self):
        rows = [[_cat("judge_error", "boom")]]
        result = evaluate_gate("avg(judge)>=0.5", rows)
        assert result.ok is False
        assert "从未产出" in result.lines[0]

    def test_unknown_score_name_fails_closed(self):
        """门禁写错分数名必须判失败，而不是"这条没有约束"。"""
        rows = [[_bool("task_output_match", True)]]
        result = evaluate_gate("avg(task_output_mach)>=1", rows)  # 少一个 t
        assert result.ok is False
        assert "从未产出" in result.lines[0]

    def test_every_clause_is_reported_and_any_failure_fails_the_gate(self):
        rows = [[_num("judge", 1.0), _num("tool_errors", 9)]]
        result = evaluate_gate("avg(judge)>=0.5,max(tool_errors)<=2", rows)
        assert result.ok is False
        assert len(result.lines) == 2
        assert result.lines[0].startswith("✓")
        assert result.lines[1].startswith("✗")

    def test_all_clauses_pass(self):
        rows = [[_num("judge", 0.9), _num("tool_errors", 0)]]
        result = evaluate_gate("avg(judge)>=0.8,max(tool_errors)<=2", rows)
        assert result.ok is True
        assert all(line.startswith("✓") for line in result.lines)

    def test_no_rows_at_all_fails_closed(self):
        """一项都没跑（批次为空/全部中断）时，任何聚合都无值可算 → 失败。"""
        assert evaluate_gate("avg(judge)>=0.5", []).ok is False
