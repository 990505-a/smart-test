"""Eval module (测评模块) — Langfuse 闭环。

    python -m src.app.eval.cli --help

构成（参考 dsh-eval-automation 的设计，见 DOCKER.md / EVAL.md）：

    langfuse_client.py  Langfuse 传输层（手写 HTTP，只依赖 httpx）
    tracing.py          确定性 traceId + agent 事件流 → trace 树
    dataset.py          YAML 评测集
    scorers.py          确定性打分器 / LLM-as-judge
    gate.py             质量门禁表达式
    runner.py           主循环（驱动 agent、打分、上报）
    cli.py              命令行入口
"""

from src.app.eval.dataset import EvalDataset, EvalItem, load_dataset
from src.app.eval.gate import evaluate_gate, parse_gate
from src.app.eval.langfuse_client import LangfuseClient
from src.app.eval.scorers import ScoreResult, deterministic_scorers, LlmJudge
from src.app.eval.tracing import RunTrace, trace_id_for

__all__ = [
    "EvalDataset", "EvalItem", "load_dataset",
    "evaluate_gate", "parse_gate",
    "LangfuseClient", "ScoreResult", "deterministic_scorers", "LlmJudge",
    "RunTrace", "trace_id_for",
]
