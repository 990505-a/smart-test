"""Quality gate expressions (测评模块).

Ported from dsh-eval-automation's ``report.ts`` so the two systems take the
same gate syntax:

    avg(task_output_match)>=0.8     mean across items
    min(llm_judge)>=0.6             worst item
    max(tool_errors)<=2             worst-case guardrail
    all(tool_sequence)              every item's boolean score is true

Booleans aggregate as 1/0; CATEGORICAL scores are skipped. A gate naming a
score nobody produced **fails closed** — a typo in a gate must never read as
"no constraint".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.app.eval.scorers import ScoreResult

_FUNCTIONS = ("avg", "min", "max", "all")
_COMPARISONS = (">=", "<=", ">", "<", "==")


@dataclass
class GateClause:
    fn: str
    score: str
    op: str | None = None
    threshold: float | None = None

    def render(self) -> str:
        if self.op is None:
            return f"{self.fn}({self.score})"
        return f"{self.fn}({self.score}){self.op}{self.threshold}"


@dataclass
class GateResult:
    ok: bool
    lines: list[str]


def parse_gate(expression: str) -> list[GateClause]:
    """Parse a gate expression; every syntax error names the offending clause."""
    clauses = [part.strip() for part in re.split(r"&&|,", expression) if part.strip()]
    if not clauses:
        raise ValueError("gate: 表达式为空")
    parsed: list[GateClause] = []
    for clause in clauses:
        match = re.fullmatch(
            r"(avg|min|max|all)\(([\w-]+)\)\s*(>=|<=|>|<|==)?\s*([\d.]+)?", clause)
        if match is None:
            raise ValueError(f"gate: 无法解析子句 {clause!r}")
        fn, score, op, threshold = match.groups()
        if fn == "all" and op is None:
            parsed.append(GateClause(fn=fn, score=score))
            continue
        if op is None or threshold is None:
            raise ValueError(
                f"gate: 子句 {clause!r} 缺少比较，例如 {fn}({score})>=0.8")
        parsed.append(GateClause(fn=fn, score=score, op=op, threshold=float(threshold)))
    return parsed


def _aggregate(clause: GateClause, rows: list[list[ScoreResult]]) -> float | None:
    values: list[float] = []
    for scores in rows:
        for score in scores:
            if score.name != clause.score:
                continue
            if isinstance(score.value, bool):
                values.append(1.0 if score.value else 0.0)
            elif isinstance(score.value, (int, float)):
                values.append(float(score.value))
    if not values:
        return None
    if clause.fn == "avg":
        return sum(values) / len(values)
    if clause.fn == "min":
        return min(values)
    if clause.fn == "max":
        return max(values)
    return 1.0 if all(value == 1.0 for value in values) else 0.0


def evaluate_gate(expression: str, rows: list[list[ScoreResult]]) -> GateResult:
    """Evaluate a gate; each clause reports its computed value and verdict."""
    lines: list[str] = []
    ok = True
    for clause in parse_gate(expression):
        value = _aggregate(clause, rows)
        if value is None:
            ok = False
            lines.append(f"✗ {clause.render()}：该分数从未产出——检查打分器配置")
            continue
        if clause.op is None:
            passed = value == 1.0
        else:
            passed = _compare(value, clause.op, clause.threshold or 0.0)
        if not passed:
            ok = False
        lines.append(f"{'✓' if passed else '✗'} {clause.render()} — 实测 {round(value, 3)}")
    return GateResult(ok=ok, lines=lines)


def _compare(value: float, op: str, threshold: float) -> bool:
    if op == ">=":
        return value >= threshold
    if op == "<=":
        return value <= threshold
    if op == ">":
        return value > threshold
    if op == "<":
        return value < threshold
    return value == threshold
