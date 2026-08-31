"""Self-evolution (自进化) run records.

Each nightly (or manual) evolution run aggregates case-review annotations,
reflects on them with the LLM, and distills lessons back into module skills —
following the openclaw / hermes self-improvement loop.
"""

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.app.db.database import Base
from src.app.db.models.base import TimestampMixin, UUIDMixin


class EvolutionRun(Base, UUIDMixin, TimestampMixin):
    """One self-evolution cycle."""

    __tablename__ = "evolution_runs"
    __table_args__ = {"comment": "Self-evolution run history"}

    trigger: Mapped[str] = mapped_column(String(20), default="scheduled", nullable=False,
                                         comment="scheduled | manual")
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False,
                                        comment="running | success | failed | skipped")
    # Inputs
    annotations_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    good_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bad_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    modules_touched: Mapped[str | None] = mapped_column(Text, nullable=True,
                                                        comment="JSON list of module names")
    # Outputs
    lessons: Mapped[str | None] = mapped_column(Text, nullable=True,
                                                comment="LLM-distilled lessons (markdown)")
    skill_patches: Mapped[str | None] = mapped_column(Text, nullable=True,
                                                      comment="JSON: [{module, skill_path, action}]")
    regression_summary: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Self-regression replay summary")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String(50), nullable=True)

    def __repr__(self) -> str:
        return f"<EvolutionRun(id={self.id}, status={self.status})>"
