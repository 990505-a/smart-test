"""Web-UI 脚本写入口 + agent 工具测试。

锁住这次收敛的关键性质：
- 默认值（设备 / 状态 / spec 路径）只由 settings 与常量决定，不再散落硬编码；
- 新建/更新走同一个 ``save_script``，version 只在内容真变了才 +1；
- 对话页能读回库里的源码（``webui_get_script``），因此"探索 → 入库 → 改 → 覆盖"
  是一条闭环，不会每次都多出一份重复用例。
"""

from __future__ import annotations

import json
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import src.app.db.database as db_module
from src.app.agents.webui import tools as agent_tools
from src.app.core.config import settings
from src.app.db.database import Base
from src.app.db.models.web_ui_script import WebUiScript
from src.app.services import playwright_service as ps


@pytest_asyncio.fixture
async def db_factory(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(db_module, "async_session_factory", factory)
    yield factory
    await engine.dispose()


# ---------------------------------------------------------------------------
# options 构造：默认值的唯一来源
# ---------------------------------------------------------------------------

class TestBuildScriptOptions:
    def test_default_device_comes_from_settings(self, monkeypatch):
        monkeypatch.setattr(settings, "web_ui_default_device", "Pixel 5")
        assert ps.build_script_options() == {"device": "Pixel 5"}

    def test_desktop_omits_device_entirely(self):
        # 不是 device="" —— 是根本没有 device 键，runner 才按不做设备模拟处理
        assert "device" not in ps.build_script_options(desktop=True)

    def test_explicit_device_wins(self):
        assert ps.build_script_options(device="iPhone SE")["device"] == "iPhone SE"

    def test_browsers_and_video(self):
        opts = ps.build_script_options(browsers=["chromium", "webkit"], video="on")
        assert opts["browsers"] == ["chromium", "webkit"]
        assert opts["video"] == "on"

    def test_base_is_merged_not_replaced(self):
        opts = ps.build_script_options(base={"locale": "zh-CN"})
        assert opts["locale"] == "zh-CN" and "device" in opts

    def test_no_option_is_hardcoded_iphone(self, monkeypatch):
        """改配置就该跟着变——过去这里写死 "iPhone 13"。"""
        monkeypatch.setattr(settings, "web_ui_default_device", "Galaxy S9+")
        opts = ps.build_script_options()
        assert "iPhone 13" not in json.dumps(opts)


# ---------------------------------------------------------------------------
# save_script：新建 / 更新
# ---------------------------------------------------------------------------

class TestSaveScriptCreate:
    @pytest.mark.asyncio
    async def test_create_defaults_to_draft_with_configured_device(self, db_factory):
        async with db_factory() as db:
            row = await ps.save_script(db, name="登录页", content="test('a',()=>{})")
        assert row.status == ps.DEFAULT_SCRIPT_STATUS == "draft"
        assert row.spec_file == ps.DEFAULT_SPEC_FILE
        assert json.loads(row.options)["device"] == settings.web_ui_default_device
        assert row.version == 1

    @pytest.mark.asyncio
    async def test_create_fills_target_url_from_settings(self, db_factory, monkeypatch):
        monkeypatch.setattr(settings, "web_ui_default_target_url", "https://example.test")
        async with db_factory() as db:
            row = await ps.save_script(db, name="x", content="c")
        assert row.target_url == "https://example.test"

    @pytest.mark.asyncio
    async def test_create_requires_content(self, db_factory):
        async with db_factory() as db:
            with pytest.raises(ValueError):
                await ps.save_script(db, name="空的")

    @pytest.mark.asyncio
    async def test_explicit_options_win_over_device(self, db_factory):
        """页面表单路径：直接给 options 就不按 device 重算。"""
        async with db_factory() as db:
            row = await ps.save_script(
                db, name="x", content="c", options={"device": "iPad Mini", "locale": "en"})
        assert json.loads(row.options) == {"device": "iPad Mini", "locale": "en"}


class TestSaveScriptUpdate:
    @pytest.mark.asyncio
    async def test_update_by_script_id_does_not_create_a_second_row(self, db_factory):
        async with db_factory() as db:
            first = await ps.save_script(db, name="A", content="v1")
            updated = await ps.save_script(db, script_id=str(first.id), content="v2")
            rows = list((await db.execute(select(WebUiScript))).scalars().all())
        assert len(rows) == 1
        assert str(updated.id) == str(first.id)
        assert updated.content == "v2"

    @pytest.mark.asyncio
    async def test_version_bumps_only_when_content_changes(self, db_factory):
        async with db_factory() as db:
            row = await ps.save_script(db, name="A", content="v1")
            same = await ps.save_script(db, script_id=str(row.id), content="v1")
            assert same.version == 1
            changed = await ps.save_script(db, script_id=str(row.id), content="v2")
            assert changed.version == 2
            # 只改标题（content 没传）不该动版本
            renamed = await ps.save_script(db, script_id=str(row.id), name="B")
            assert renamed.version == 2 and renamed.name == "B"

    @pytest.mark.asyncio
    async def test_title_only_save_preserves_page_configured_options(self, db_factory):
        """页面表单配好的设备/浏览器矩阵不能被一次"只改标题"抹掉。"""
        async with db_factory() as db:
            row = await ps.save_script(
                db, name="A", content="c",
                options={"device": "iPad Mini", "browsers": ["webkit"]})
            await ps.save_script(db, script_id=str(row.id), name="B")
            assert json.loads(row.options) == {"device": "iPad Mini", "browsers": ["webkit"]}

    @pytest.mark.asyncio
    async def test_device_arg_does_overwrite_options(self, db_factory):
        async with db_factory() as db:
            row = await ps.save_script(db, name="A", content="c",
                                       options={"device": "iPad Mini"})
            await ps.save_script(db, script_id=str(row.id), device="Pixel 5")
            assert json.loads(row.options)["device"] == "Pixel 5"

    @pytest.mark.asyncio
    async def test_unknown_script_id_raises_lookup_error(self, db_factory):
        async with db_factory() as db:
            with pytest.raises(LookupError):
                await ps.save_script(db, script_id=str(uuid.uuid4()), content="x")


class TestGetScript:
    @pytest.mark.asyncio
    async def test_returns_content(self, db_factory):
        async with db_factory() as db:
            row = await ps.save_script(db, name="A", content="THE SPEC SOURCE")
            found = await ps.get_script(db, str(row.id))
        assert found is not None and found.content == "THE SPEC SOURCE"

    @pytest.mark.asyncio
    async def test_missing_returns_none(self, db_factory):
        async with db_factory() as db:
            assert await ps.get_script(db, str(uuid.uuid4())) is None


# ---------------------------------------------------------------------------
# agent 工具
# ---------------------------------------------------------------------------

class TestSaveScriptTool:
    @pytest.mark.asyncio
    async def test_create_is_active_because_verified(self, db_factory):
        out = await agent_tools.webui_save_script.ainvoke(
            {"name": "登录", "content": "spec"})
        assert out["success"] is True and out["updated"] is False
        async with db_factory() as db:
            row = (await db.execute(select(WebUiScript))).scalars().first()
        # 工具契约是"验证通过才入库"，所以显式 active；draft 是页面表单的默认
        assert row.status == "active"

    @pytest.mark.asyncio
    async def test_update_via_script_id_reports_updated(self, db_factory):
        created = await agent_tools.webui_save_script.ainvoke(
            {"name": "登录", "content": "v1"})
        updated = await agent_tools.webui_save_script.ainvoke(
            {"name": "登录", "content": "v2", "script_id": created["script_id"]})
        assert updated["updated"] is True
        assert updated["version"] == 2
        async with db_factory() as db:
            rows = list((await db.execute(select(WebUiScript))).scalars().all())
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_unknown_id_degrades_without_raising(self, db_factory):
        out = await agent_tools.webui_save_script.ainvoke(
            {"name": "x", "content": "y", "script_id": str(uuid.uuid4())})
        assert out["success"] is False and "不存在" in out["error"]


class TestGetScriptTool:
    @pytest.mark.asyncio
    async def test_round_trip_source(self, db_factory):
        created = await agent_tools.webui_save_script.ainvoke(
            {"name": "登录", "content": "round-tripped source"})
        got = await agent_tools.webui_get_script.ainvoke(
            {"script_id": created["script_id"]})
        assert got["success"] is True
        assert got["content"] == "round-tripped source"
        assert got["version"] == 1 and "repair_count" in got

    @pytest.mark.asyncio
    async def test_unknown_id_is_an_error_not_an_exception(self, db_factory):
        out = await agent_tools.webui_get_script.ainvoke({"script_id": str(uuid.uuid4())})
        assert out["success"] is False and "不存在" in out["error"]


class TestScreenshotTool:
    @pytest.mark.asyncio
    async def test_default_uses_configured_device(self, monkeypatch):
        seen: dict = {}

        async def _fake(url, **kwargs):
            seen.update(kwargs)
            return {"ok": True}

        monkeypatch.setattr(ps, "screenshot", _fake)
        monkeypatch.setattr(settings, "web_ui_default_device", "Pixel 5")
        await agent_tools.webui_screenshot.ainvoke({"url": "https://x.test"})
        assert seen["device"] == "Pixel 5"

    @pytest.mark.asyncio
    async def test_desktop_sends_no_device(self, monkeypatch):
        seen: dict = {}

        async def _fake(url, **kwargs):
            seen.update(kwargs)
            return {"ok": True}

        monkeypatch.setattr(ps, "screenshot", _fake)
        await agent_tools.webui_screenshot.ainvoke(
            {"url": "https://x.test", "desktop": True})
        # 空串 = runner 收到 device="" 会被当成设备名 —— 必须省略这个键
        assert seen["device"] is None

    def test_docstring_names_the_real_field(self):
        """执行器返回驼峰 dataUri；文档写 data_uri 会让 agent 取错 key。"""
        doc = agent_tools.webui_screenshot.description
        assert "dataUri" in doc


class TestRepairBudgetConsistency:
    def test_prompt_budget_matches_settings(self, monkeypatch):
        """重跑预算不再硬编码，而是跟着 WEB_UI_MAX_REPAIR 走。

        提示词现在由能力清单统一构建（``capabilities.build_system_prompt``）——
        旧的 per-mode agent 模块已变成薄壳，不再持有自己的提示词。
        """
        from src.app.agents.capabilities import CAPABILITY_BY_KEY, build_system_prompt

        monkeypatch.setattr(settings, "web_ui_max_repair", 5)
        prompt = build_system_prompt((CAPABILITY_BY_KEY["webui"],))
        assert "最多 6 次执行" in prompt
        assert "5 轮修正" in prompt

    def test_cli_tool_points_at_the_dedicated_tools(self):
        doc = agent_tools.webui_cli.description
        assert "webui_screenshot" in doc and "webui_run_spec" in doc
