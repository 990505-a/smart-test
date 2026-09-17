"""Browser UI automation scripts (Web-UI 自动化模块).

Playwright CLI driven browser tests. A script is one spec file
(`*.spec.ts` by default) plus the declarative options the runner needs
(target URL, device emulation). Execution happens in the playwright-runner
sidecar, which owns the Node toolchain and the browsers.

与 Unity 自动化（unity_script.py，游戏内 Lua 控件）并列：前者驱动浏览器 DOM，
后者驱动游戏 UI 控件，都是「定位 → 操作 → 断言」。
"""

from sqlalchemy import ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from src.app.db.database import Base
from src.app.db.models.base import TimestampMixin, UUIDMixin


class WebUiScript(Base, UUIDMixin, TimestampMixin):
    """A Playwright spec file plus the options needed to run it."""

    __tablename__ = "web_ui_scripts"
    __table_args__ = {"comment": "Browser UI automation scripts (Playwright CLI)"}

    name: Mapped[str] = mapped_column(String(500), nullable=False)
    project_id: Mapped[str | None] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    module: Mapped[str | None] = mapped_column(String(200), nullable=True, comment="业务模块")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="playwright spec 源码")
    spec_file: Mapped[str] = mapped_column(
        String(300), default="tests/spec.spec.ts", nullable=False,
        comment="spec 在运行目录中的相对路径")
    target_url: Mapped[str | None] = mapped_column(
        String(1000), nullable=True, comment="被测站点入口，注入 config 的 baseURL")
    options: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="JSON：device/viewport/locale/trace 等 runner 选项")
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False,
                                        comment="draft | active | broken | archived")
    repair_history: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<WebUiScript(name={self.name}, v{self.version})>"


class WebUiScriptRun(Base, UUIDMixin, TimestampMixin):
    """One `playwright test` execution of a WebUiScript."""

    __tablename__ = "web_ui_script_runs"
    __table_args__ = {"comment": "Playwright test execution records"}

    script_id: Mapped[str] = mapped_column(
        Uuid, ForeignKey("web_ui_scripts.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False,
                                        comment="running | passed | failed | error | skipped")
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output: Mapped[str | None] = mapped_column(Text, nullable=True, comment="CLI stdout/stderr")
    report: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="JSON：playwright json reporter 的 stats/tests")
    artifacts: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="JSON list of {name,path,size}")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    triggered_by: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    repair_attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    runner_run_id: Mapped[str | None] = mapped_column(
        String(120), nullable=True, comment="runner 侧目录名，用于回取 artifacts")

    def __repr__(self) -> str:
        return f"<WebUiScriptRun(script={self.script_id}, {self.status})>"
