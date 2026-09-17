"""Unity UI automation scripts (Unity 自动化模块).

Playwright-style UI test scripts driving the game's Lua UI controls via the
vendored unity-ui-test skill (HTTP LuaRemoteServer on :16666).

本模块原名「UI 自动化」，2026-09 与新增的 Web-UI 自动化（浏览器 + Playwright
CLI）并列后改名 Unity 自动化。表名由 ``init_db()`` 从 ui_scripts /
ui_script_runs 就地 RENAME 迁移，旧库无需重建。
"""

from sqlalchemy import ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from src.app.db.database import Base
from src.app.db.models.base import TimestampMixin, UUIDMixin


class UnityScript(Base, UUIDMixin, TimestampMixin):
    """A Unity UI automation script (python, using the unity skill API)."""

    __tablename__ = "unity_scripts"
    __table_args__ = {"comment": "Unity UI automation scripts"}

    name: Mapped[str] = mapped_column(String(500), nullable=False)
    project_id: Mapped[str | None] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    module: Mapped[str | None] = mapped_column(String(200), nullable=True, comment="游戏模块")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="python 脚本内容")
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False,
                                        comment="draft | active | broken | archived")
    repair_history: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<UnityScript(name={self.name}, v{self.version})>"


class UnityScriptRun(Base, UUIDMixin, TimestampMixin):
    """One execution of a UnityScript against the Unity editor."""

    __tablename__ = "unity_script_runs"
    __table_args__ = {"comment": "Unity UI script execution records"}

    script_id: Mapped[str] = mapped_column(
        Uuid, ForeignKey("unity_scripts.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False,
                                        comment="running | passed | failed | error | skipped")
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    screenshots: Mapped[str | None] = mapped_column(Text, nullable=True,
                                                    comment="JSON list of screenshot paths")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    triggered_by: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)

    def __repr__(self) -> str:
        return f"<UnityScriptRun(script={self.script_id}, {self.status})>"
