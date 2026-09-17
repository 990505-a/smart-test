"""Eval batches and case results (测评模块).

A batch is one `python -m src.app.eval.cli` invocation: a dataset run against
one agent, with a gate expression and an aggregate verdict. Case results are
one row per dataset item, holding the scores that were uploaded to Langfuse
plus the trace id they hang on — so the platform UI can deep-link from a row
straight into Langfuse.
"""

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from src.app.db.database import Base
from src.app.db.models.base import TimestampMixin, UUIDMixin


class EvalBatch(Base, UUIDMixin, TimestampMixin):
    """One dataset × agent evaluation batch."""

    __tablename__ = "eval_batches"
    __table_args__ = {"comment": "Eval batches (dataset runs against an agent)"}

    dataset: Mapped[str] = mapped_column(String(300), nullable=False)
    run_name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    agent: Mapped[str] = mapped_column(String(120), nullable=False, comment="LangGraph 图名")
    release: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="running", nullable=False,
        comment="running | passed | failed | error")
    gate_expression: Mapped[str | None] = mapped_column(Text, nullable=True)
    gate_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    gate_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_cases: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    scored_cases: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_cases: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    averages: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="JSON: {score_name: avg}")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output: Mapped[str | None] = mapped_column(Text, nullable=True, comment="CLI 汇总输出")
    langfuse_host: Mapped[str | None] = mapped_column(String(300), nullable=True)

    def __repr__(self) -> str:
        return f"<EvalBatch({self.dataset} · {self.run_name} · {self.status})>"


class EvalCaseResult(Base, UUIDMixin, TimestampMixin):
    """One dataset item's outcome inside a batch."""

    __tablename__ = "eval_case_results"
    __table_args__ = {"comment": "Per-item eval outcomes with Langfuse trace ids"}

    batch_id: Mapped[str] = mapped_column(
        Uuid, ForeignKey("eval_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id: Mapped[str] = mapped_column(String(200), nullable=False)
    instruction: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="确定性 Langfuse traceId")
    thread_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ok", nullable=False,
                                        comment="ok | error")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scores: Mapped[str | None] = mapped_column(Text, nullable=True, comment="JSON list")
    tool_names: Mapped[str | None] = mapped_column(Text, nullable=True, comment="JSON list")
    evidence: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="JSON list of playwright artifacts")

    def __repr__(self) -> str:
        return f"<EvalCaseResult({self.item_id} · {self.status})>"
