"""Unity 手动录制的单元测试。

三层：
1. **C# 片段的静态契约**：占位符全部替换、无 `{{` 泄漏、大括号配平、不含 C# 6+ 语法
   （mcp-for-unity 的 execute_code 用 CodeDom 编译，只认 C# 5——这些约束错了要到
   Unity 侧才炸，单测提前挡掉）。
2. **事件 → 脚本转换器**：点击/拖拽/文本/按键、去重、断言播种、RESET 生成。
3. **服务层编排**：录制存储读写、环境门（必须先在 Play）、域重载后心跳自愈重挂、
   停止时的事件取回与落盘。
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.app.db.database import Base
from src.app.services import unity_recorder, unity_service


# ---------------------------------------------------------------------------
# 1. C# 片段的静态契约
# ---------------------------------------------------------------------------

def _snippets() -> dict[str, str]:
    return {
        "start": unity_recorder.cs_record_ui_start("rec_x"),
        "stop": unity_recorder.cs_record_ui_stop(),
        "status": unity_recorder.cs_record_ui_status(),
        "fetch": unity_recorder.cs_record_ui_fetch(0, 100),
        "drag": unity_recorder.cs_drag("A/B", "C/D", 8),
        "key": unity_recorder.cs_key("escape"),
    }


class TestSnippetContract:
    def test_no_placeholders_left(self):
        for name, text in _snippets().items():
            assert "@@" not in text, f"{name} 还有未替换的占位符"

    def test_no_format_brace_leak(self):
        """占位符用 @@…@@ 而非 str.format：不该出现 {{ }} 转义残留。"""
        for name, text in _snippets().items():
            assert "{{" not in text and "}}" not in text, f"{name} 有大括号转义残留"

    def test_braces_balanced(self):
        for name, text in _snippets().items():
            assert text.count("{") == text.count("}"), f"{name} 大括号不配平（Unity 侧会编译失败）"

    def test_csharp5_only(self):
        """CodeDom 只认 C# 5：字符串插值 / 空条件 / lambda / nameof 都不能用。"""
        forbidden = ('$"', "?.", "=>", "nameof(")
        for name, text in _snippets().items():
            for token in forbidden:
                assert token not in text, f"{name} 用了 C# 6+ 语法: {token}"

    def test_start_snippet_is_idempotent_by_heartbeat(self):
        """重挂前先看心跳：活着就不重复挂（否则会有两份回调、事件翻倍）。"""
        text = unity_recorder.cs_record_ui_start("rec_x")
        assert "already" in text and "realtimeSinceStartup - __hb0 < 3f" in text

    def test_start_snippet_keeps_events_on_rearm(self):
        """重挂不能截断事件文件（域重载后继续录，已录的必须还在）。"""
        text = unity_recorder.cs_record_ui_start("rec_x")
        # 写空文件（截断）只允许发生在"新建"分支里
        head, _, tail = text.partition("} else {")
        assert "WriteAllText" not in head
        assert "WriteAllText" in tail

    def test_new_subdir_starts_a_fresh_session(self):
        """换了录制目录 = 新一场：不能继承旧文件（实测：僵尸钩子会让新录制读到旧事件）。"""
        text = unity_recorder.cs_record_ui_start("rec_x")
        assert "__same" in text
        assert "StartsWith(__dir.Replace" in text, "缺少同目录判定，重挂会沿用旧事件文件"

    def test_subdir_is_sanitized(self):
        text = unity_recorder.cs_record_ui_start("../../etc/passwd")
        assert "passwd" not in text.split("unity-auto-ui-rec")[-1].split('"')[0]
        assert ".." not in text

    def test_unsupported_key_rejected(self):
        with pytest.raises(ValueError):
            unity_recorder.cs_key("f13")

    def test_drag_targets_quoted_exactly_once(self):
        """模板与值各加一次引号 → `""X""`（实测：真机 CodeDom 报 'Unexpected symbol'）。"""
        text = unity_recorder.cs_drag("Bag/Item", "Bag/Slot")
        assert 'var __target = "Bag/Item";' in text
        assert 'var __target = "Bag/Slot";' in text
        assert '""' not in text, "出现双写引号：模板与 _cs_quote 各加了一次引号"

    def test_no_inner_name_shadows_outer_name(self):
        """C# 不允许子作用域重名（实测踩到：__emit 的参数 __line 与外层委托 __line 撞名）。

        静态扫一遍：**方法体顶层**声明过的名字，不能再出现在任何更深作用域里
        （delegate 参数也算深层声明）。真机 CodeDom 的报错形如
        "A local variable named `__x' cannot be declared in this scope ..."。
        """
        for name, text in _snippets().items():
            outer, inner = _split_scopes(text)
            clash = outer & inner
            assert not clash, f"{name} 存在跨作用域重名（Unity 侧会编译失败）: {sorted(clash)}"


def _split_scopes(text: str) -> tuple[set[str], set[str]]:
    """按大括号深度，把 ``__x`` 声明名分成「方法体顶层」与「更深层」两拨。

    只做启发式：认「类型 __x = / ;」与 ``delegate(... __x ...)`` 两种形态
    （这套片段里所有声明都是这两种写法）。foreach/for 的循环变量不参与
    —— 它们天然是块内作用域，且没在顶层重名过。
    """
    outer: set[str] = set()
    inner: set[str] = set()
    depth = 0
    for raw in text.splitlines():
        stripped = raw.strip()
        # 委托参数一律算**深层**：它属于委托体这个嵌套作用域（无论 delegate
        # 的声明行本身在第几层）——最初那个 bug 正是"委托参数撞了外层变量"。
        for params in re.findall(r"\bdelegate\s*\(([^)]*)\)", stripped):
            for part in params.split(","):
                part = part.strip()
                if part:
                    inner.add(part.split()[-1])
        m = re.match(r"^[A-Za-z_][\w\.<>,\[\]\s]*?\s+(__\w+)\s*(?:=|;|\))", stripped)
        if m:
            (outer if depth == 0 else inner).add(m.group(1))
        depth += stripped.count("{") - stripped.count("}")
    return outer, inner


# ---------------------------------------------------------------------------
# 2. 事件 → 脚本转换器
# ---------------------------------------------------------------------------

def _click(t: float, path: str, *, label: str = "", comp: str = "Button",
           panels: str = "MainHud|MainHud,TopBar") -> dict:
    return {"t": t, "type": "click", "path": path, "label": label,
            "comp": comp, "panels": panels, "kind": "ui"}


def _scene(t: float, path: str = "Assets/Maps/01.unity") -> dict:
    return {"t": t, "type": "scene", "name": "01", "path": path}


class TestConverter:
    def test_basic_click_flow(self):
        events = [
            _scene(0.0),
            _click(1.0, "MainHud/BottomBar/BagButton", label="背包"),
            _click(3.2, "BagWindow/CloseButton", label="关闭",
                   panels="MainHud|MainHud,TopBar,BagWindow"),
        ]
        script, stats = unity_recorder.convert_events_to_script(events, title="背包流程")

        assert stats["clicks"] == 2 and stats["steps"] == 2
        # 起跑线：场景 + 首个点击的顶层容器做标志物
        assert 'RESET = {"scene": "Assets/Maps/01.unity", "wait_for": "MainHud"}' in script
        # 首次使用路径 → 播种 expect_exists；点击后新面板 → 播种断言
        assert 'u.expect_exists("MainHud/BottomBar/BagButton", timeout=10)  # [自动播种]  # 背包' in script
        assert 'u.click("MainHud/BottomBar/BagButton")  # Button' in script
        assert 'u.expect_exists("BagWindow", timeout=10)  # [自动播种] 点击后新出现' in script
        # 播种三处：两次"首次使用该路径"的 expect_exists + 一次"点击后新出现 BagWindow"
        assert stats["assertions_seeded"] == 3
        # 生成的脚本必须是合法 Python
        compile(script, "<recording-script>", "exec")

    def test_duplicate_clicks_merged_and_empty_dropped(self):
        events = [
            _click(1.0, "Hud/Btn"),
            _click(1.08, "Hud/Btn"),           # 手抖重复：合并
            {"t": 1.5, "type": "click", "path": ""},   # 命中落空：丢弃
            _click(2.0, "Hud/Btn"),            # 间隔够远：算第二次点击
        ]
        steps, stats = unity_recorder.merge_events(events)
        assert stats["clicks"] == 2
        assert stats["merged_clicks"] == 1
        assert stats["dropped"] == 1

    def test_text_events_collapse_to_final_value(self):
        events = [
            {"t": 1.0, "type": "text", "path": "Login/Input", "text": "a"},
            {"t": 1.2, "type": "text", "path": "Login/Input", "text": "ab"},
            {"t": 1.5, "type": "text", "path": "Login/Input", "text": "abc"},
        ]
        script, stats = unity_recorder.convert_events_to_script(events)
        assert stats["texts"] == 1 and stats["merged_texts"] == 2
        assert 'u.set_text("Login/Input", "abc")' in script

    def test_drag_and_key(self):
        events = [
            {"t": 1.0, "type": "drag", "from": "Bag/Item", "to": "Bag/Slot"},
            {"t": 2.0, "type": "key", "key": "escape"},
        ]
        script, stats = unity_recorder.convert_events_to_script(events)
        assert stats["drags"] == 1 and stats["keys"] == 1
        assert 'u.drag("Bag/Item", "Bag/Slot")' in script
        assert 'u.key("escape")' in script
        compile(script, "<recording-script>", "exec")

    def test_gap_comment(self):
        events = [_click(1.0, "A"), _click(6.0, "B")]
        script, _ = unity_recorder.convert_events_to_script(events)
        assert "# （人工停顿 5.0s）" in script

    def test_empty_recording(self):
        script, stats = unity_recorder.convert_events_to_script([])
        assert stats["steps"] == 0
        assert "没有录到任何操作" in script
        compile(script, "<recording-script>", "exec")

    def test_quotes_in_text_are_escaped_safely(self):
        events = [{"t": 1.0, "type": "text", "path": 'A"B', "text": 'he said "hi"\n\\'}]
        script, _ = unity_recorder.convert_events_to_script(events)
        compile(script, "<recording-script>", "exec")
        assert "\\n" in script and '\\"' in script


# ---------------------------------------------------------------------------
# 3. 服务层：存储 / 环境门 / 心跳自愈 / 停止取回
# ---------------------------------------------------------------------------

@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """把 workspace 指到 tmp，并把"当前录制"的进程内状态清干净。"""
    monkeypatch.setattr(unity_service.settings, "workspace_dir", tmp_path / "workspace")
    monkeypatch.setattr(unity_service, "_ACTIVE_REC_ID", None, raising=False)
    return tmp_path / "workspace"


def _make_recording(workspace: Path, rec_id: str = "rec_test_0001", **meta) -> Path:
    rec_dir = workspace / "default" / "unity-auto" / "recordings" / rec_id
    rec_dir.mkdir(parents=True, exist_ok=True)
    base = {"id": rec_id, "name": "测试录制", "status": "recorded",
            "created_at": "2026-09-22T10:00:00+00:00", "events": 2, "steps": 1,
            "scene": "Assets/Maps/01.unity"}
    base.update(meta)
    (rec_dir / "meta.json").write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
    (rec_dir / "events.jsonl").write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in
                  [_scene(0.0), _click(1.0, "Hud/Btn")]) + "\n", encoding="utf-8")
    return rec_dir


class TestRecordingStore:
    def test_list_and_get(self, workspace):
        _make_recording(workspace)
        items = unity_service.list_recordings()
        assert len(items) == 1 and items[0]["id"] == "rec_test_0001"
        detail = unity_service.get_recording("rec_test_0001")
        assert len(detail["events"]) == 2
        assert detail["meta"]["scene"] == "Assets/Maps/01.unity"

    def test_invalid_id_rejected(self, workspace):
        for bad in ("../evil", "a/b", "", "x" * 65):
            with pytest.raises(ValueError):
                unity_service._recording_dir(bad)

    def test_delete(self, workspace):
        _make_recording(workspace)
        assert unity_service.delete_recording("rec_test_0001")["deleted"] is True
        assert unity_service.list_recordings() == []

    def test_delete_refuses_active(self, workspace):
        _make_recording(workspace, status="recording")
        with pytest.raises(RuntimeError):
            unity_service.delete_recording("rec_test_0001")

    def test_to_script_preview_writes_file(self, workspace):
        rec_dir = _make_recording(workspace)
        import asyncio
        result = asyncio.run(unity_service.recording_to_script(
            "rec_test_0001", name="背包流程", save=False))
        assert result["script_id"] is None
        assert (rec_dir / "script.py").exists()
        assert "u.click(\"Hud/Btn\")" in result["script"]


@pytest.mark.asyncio
class TestStartGuards:
    async def test_requires_play_mode(self, workspace, monkeypatch):
        monkeypatch.setattr(unity_service.unity_bridge, "status",
                            AsyncMock(return_value={"available": True,
                                                    "unity_connected": True,
                                                    "is_playing": False}))
        out = await unity_service.record_ui_start("")
        assert out["success"] is False
        assert "Play" in out["error"]

    async def test_requires_bridge(self, workspace, monkeypatch):
        monkeypatch.setattr(unity_service.unity_bridge, "status",
                            AsyncMock(return_value={"available": False, "error": "桥没起"}))
        out = await unity_service.record_ui_start("")
        assert out["success"] is False and "桥" in out["error"]

    async def test_happy_path_creates_meta(self, workspace, monkeypatch):
        monkeypatch.setattr(unity_service.unity_bridge, "status",
                            AsyncMock(return_value={"available": True,
                                                    "unity_connected": True,
                                                    "is_playing": True}))
        monkeypatch.setattr(unity_service.unity_bridge, "record_ui_start",
                            AsyncMock(return_value={"success": True,
                                                    "result": {"ok": True, "file": "/tmp/x.jsonl"}}))
        out = await unity_service.record_ui_start("背包流程")
        assert out["success"] is True
        meta = unity_service.get_recording(out["id"])["meta"]
        assert meta["status"] == "recording" and meta["name"] == "背包流程"
        # 已有录制在跑：第二次开始被拒
        again = await unity_service.record_ui_start("")
        assert again["success"] is False and "先停止" in again["error"]


@pytest.mark.asyncio
class TestStatusSelfHeal:
    async def test_rearms_when_heartbeat_stale(self, workspace, monkeypatch):
        """域重载把钩子清掉（心跳停）→ 状态查询应当用同一个 subdir 重挂。"""
        _make_recording(workspace, "rec_live_0001", status="recording")
        monkeypatch.setattr(unity_service, "_ACTIVE_REC_ID", "rec_live_0001", raising=False)
        monkeypatch.setattr(unity_service.unity_bridge, "record_ui_status",
                            AsyncMock(return_value={"success": True, "result": {
                                "ok": True, "on": True, "events": 3, "hb_age": 99.0}}))
        rearm = AsyncMock(return_value={"success": True, "result": {"ok": True}})
        monkeypatch.setattr(unity_service.unity_bridge, "record_ui_start", rearm)

        out = await unity_service.record_ui_status()
        assert out["rearmed"] is True and out["events"] == 3
        rearm.assert_awaited_once_with(name="rec_live_0001")

    async def test_heartbeat_zero_is_not_stale(self, workspace, monkeypatch):
        """心跳每帧刷新 → age 合法值就是 0.0：不能被 `or -1` 误判成"读不到"。"""
        _make_recording(workspace, "rec_live_0003", status="recording")
        monkeypatch.setattr(unity_service, "_ACTIVE_REC_ID", "rec_live_0003", raising=False)
        monkeypatch.setattr(unity_service.unity_bridge, "record_ui_status",
                            AsyncMock(return_value={"success": True, "result": {
                                "ok": True, "on": True, "events": 4, "hb_age": 0.0}}))
        rearm = AsyncMock()
        monkeypatch.setattr(unity_service.unity_bridge, "record_ui_start", rearm)

        out = await unity_service.record_ui_status()
        assert out["hb_age"] == 0.0 and out["rearmed"] is False
        rearm.assert_not_awaited()

    async def test_no_rearm_when_alive(self, workspace, monkeypatch):
        _make_recording(workspace, "rec_live_0002", status="recording")
        monkeypatch.setattr(unity_service, "_ACTIVE_REC_ID", "rec_live_0002", raising=False)
        monkeypatch.setattr(unity_service.unity_bridge, "record_ui_status",
                            AsyncMock(return_value={"success": True, "result": {
                                "ok": True, "on": True, "events": 5, "hb_age": 0.4}}))
        rearm = AsyncMock()
        monkeypatch.setattr(unity_service.unity_bridge, "record_ui_start", rearm)

        out = await unity_service.record_ui_status()
        assert out["rearmed"] is False
        rearm.assert_not_awaited()


@pytest.mark.asyncio
class TestStopFetch:
    async def test_stop_collects_chunks_and_writes_meta(self, workspace, monkeypatch):
        rec_dir = _make_recording(workspace, "rec_stop_0001", status="recording")
        monkeypatch.setattr(unity_service, "_ACTIVE_REC_ID", "rec_stop_0001", raising=False)
        monkeypatch.setattr(unity_service.unity_bridge, "record_ui_stop",
                            AsyncMock(return_value={"success": True,
                                                    "result": {"ok": True, "reason": ""}}))
        chunk1 = "\n".join(json.dumps(e, ensure_ascii=False) for e in
                           [_scene(0.0), _click(1.0, "Hud/Btn")]) + "\n"
        chunk2 = json.dumps(_click(2.0, "Bag/Close"), ensure_ascii=False) + "\n"
        calls = [
            {"success": True, "result": {"ok": True, "total": 3, "since": 0,
                                         "more": True, "text": chunk1}},
            {"success": True, "result": {"ok": True, "total": 3, "since": 2,
                                         "more": False, "text": chunk2}},
        ]
        monkeypatch.setattr(unity_service.unity_bridge, "record_ui_fetch",
                            AsyncMock(side_effect=calls))

        out = await unity_service.record_ui_stop()
        assert out["success"] is True and out["events"] == 3 and out["steps"] == 2
        assert out["meta"]["status"] == "recorded"
        assert out["meta"]["scene"] == "Assets/Maps/01.unity"
        assert (rec_dir / "events.jsonl").read_text(encoding="utf-8") == chunk1 + chunk2
        # 停止后不再是"进行中"
        assert unity_service._active_recording_id() is None


# ---------------------------------------------------------------------------
# 4. 入库契约：生成的脚本必须能被平台自己的解析器读懂（起跑线是重点）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestSavedScriptContract:
    @pytest_asyncio.fixture
    async def db_factory(self):
        engine = create_async_engine(
            "sqlite+aiosqlite://", poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        await engine.dispose()

    async def test_save_creates_draft_with_start_line(self, workspace, db_factory, monkeypatch):
        _make_recording(workspace)
        async with db_factory() as db:
            result = await unity_service.recording_to_script(
                "rec_test_0001", name="背包流程", save=True, db=db)
        assert result["script_id"]
        async with db_factory() as db:
            from uuid import UUID

            from sqlalchemy import select

            from src.app.db.models.unity_script import UnityScript
            row = (await db.execute(select(UnityScript).where(
                UnityScript.id == UUID(result["script_id"])))).scalars().one()
        # 没跑通过 → draft（与"智能体写用例"同一条契约）
        assert row.status == "draft"
        # 平台自己的起跑线解析器能读懂生成的 RESET
        plan = unity_service.start_line(row.content, str(row.id))
        assert plan.get("scene") == "Assets/Maps/01.unity"
        assert plan.get("wait_for") == "Hud"
        assert "起跑线（人工复位）" in row.content


# ---------------------------------------------------------------------------
# 5. 桥包装的信封契约（实测踩到：类方法返回 result 字典，服务层按 success 读）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestBridgeEnvelope:
    """模块级包装必须把 `Unity.record_ui_*` 的结果字典包成统一信封。

    真机踩到的坑：`Unity.record_ui_start` 返回 `{"ok":true,"file":…}`（内层
    result），而模块级函数按 `{"success":…,"result":…}` 被服务层读取 —— 少了
    归一化，**成功的注入会被报成"录制器注入失败"**，还留下 Unity 侧没人管的
    僵尸钩子。这里把契约钉死。
    """

    @pytest.fixture(autouse=True)
    def _patch_client(self, monkeypatch):
        from src.app.services import unity_bridge

        class _FakeUnity:
            def __init__(self, result):
                self._result = result

            def record_ui_start(self, **kwargs):
                return self._result

            def record_ui_status(self):
                return self._result

            def record_ui_stop(self):
                return self._result

            def record_ui_fetch(self, since=0, cap=300):
                return self._result

        holder = {"result": {}}
        monkeypatch.setattr(unity_bridge, "unity_on_cached_client",
                            lambda: _FakeUnity(holder["result"]))
        self.holder = holder
        return holder

    async def test_ok_result_wrapped_as_success(self):
        from src.app.services import unity_bridge

        self.holder["result"] = {"ok": True, "file": "C:/tmp/x.jsonl", "events": 3}
        out = await unity_bridge.record_ui_start(name="rec_x")
        assert out["success"] is True
        assert out["result"]["file"] == "C:/tmp/x.jsonl"

    async def test_failed_result_reported_with_error(self):
        from src.app.services import unity_bridge

        self.holder["result"] = {"ok": False, "error": "Compilation failed: boom"}
        out = await unity_bridge.record_ui_fetch(since=0)
        assert out["success"] is False
        assert "Compilation failed" in out["error"]

    async def test_all_four_wrappers_share_the_contract(self):
        from src.app.services import unity_bridge

        self.holder["result"] = {"ok": True, "on": True, "events": 1, "hb_age": 0.1}
        for call in (
            unity_bridge.record_ui_start(name="rec_x"),
            unity_bridge.record_ui_status(),
            unity_bridge.record_ui_stop(),
            unity_bridge.record_ui_fetch(),
        ):
            out = await call
            assert out["success"] is True, out
            assert isinstance(out.get("result"), dict)

    async def test_service_start_succeeds_on_raw_result(self, workspace, monkeypatch):
        """服务层 + 真包装形态的组合：注入成功时不能报失败（回归上面那个坑）。"""
        monkeypatch.setattr(unity_service.unity_bridge, "status",
                            AsyncMock(return_value={"available": True,
                                                    "unity_connected": True,
                                                    "is_playing": True}))
        monkeypatch.setattr(unity_service.unity_bridge, "record_ui_start",
                            AsyncMock(return_value={"success": True,
                                                    "result": {"ok": True, "file": "C:/t.jsonl"}}))
        out = await unity_service.record_ui_start("冒烟")
        assert out["success"] is True and out["meta"]["status"] == "recording"


# ---------------------------------------------------------------------------
# 4. 安全护栏（2026-09-23 事故之后的回归）
#
# 那次事故的链条：平台注入的 prelude 调了 `u.active_scene()`（= 桥里带 preflight 的
# `manage_scene`）→ 桥自己发 refresh_unity(compile="request") → Play Mode 里一次
# 域重载 → 编辑器卡死在 Reloading Domain → D3D11 设备丢失 → 整机断电。
# 下面每条对应链条上的一环，任何一环回退都必须红。
# ---------------------------------------------------------------------------

class TestReloadSafetyGuards:
    def test_prelude_never_calls_gated_active_scene(self):
        """prelude 里**不许**出现 `u.active_scene()`（那是被闸的 manage_scene）。

        只看代码行：注释里为了讲清"为什么不用它"会提到这个名字。
        """
        code = "\n".join(line for line in unity_service._PRELUDE.splitlines()
                         if not line.lstrip().startswith("#"))

        assert "u.active_scene(" not in code, \
            "起跑线快照必须走 active_scene_path()（execute_code），不能用被闸的 active_scene()"
        assert "u.active_scene_path()" in code

    def test_prelude_uses_five_fps_recording(self):
        """录像固定 5fps（用户口径）：默认值写死在 prelude 里。"""
        assert 'UNITY_RECORD_FPS", "5"' in unity_service._PRELUDE

    def test_record_start_defaults_follow_the_run_budget(self):
        """fps 固定 5；帧数/秒数**不写死**，跟着执行预算推导。

        写死过的后果很具体：预算从 7 分钟放到 30 分钟，而录像还在第 5 分钟自己
        退订 —— 人只会看到"录像少了后半段"，联想不到是两处常量没对齐。
        """
        import inspect

        from src.app.services import unity_bridge

        sig = inspect.signature(unity_bridge.Unity.record_start)
        assert sig.parameters["fps"].default == 5.0
        assert sig.parameters["max_frames"].default is None    # None = 按预算推导
        assert sig.parameters["max_seconds"].default is None
        assert unity_bridge.DEFAULT_RECORD_FPS == 5.0

    def test_record_budget_follows_settings(self):
        """预算可配（.env 的 UNITY_RUN_TIMEOUT_S），三处常量必须一起动。"""
        from src.app.core.config import settings
        from src.app.services import unity_bridge

        original = settings.unity_run_timeout_s
        try:
            settings.unity_run_timeout_s = 1800
            frames, seconds = unity_bridge.record_budget(5.0)
            assert (frames, seconds) == (9000, 1800)
            assert unity_service.run_timeout_s() == 1800.0
            assert unity_service.run_stale_after_s() == 1980.0     # 预算 + 180
            assert int(unity_service.run_timeout_s()) == seconds    # 录像是同一份预算

            settings.unity_run_timeout_s = 600
            assert unity_bridge.record_budget(5.0) == (3000, 600)
            assert unity_service.run_stale_after_s() == 780.0
        finally:
            settings.unity_run_timeout_s = original

    def test_stale_threshold_is_not_hardcoded(self):
        """僵死阈值必须比预算宽：窄了会把**正在跑**的记录标成僵死、还允许被删。"""
        from src.app.core.config import settings

        original = settings.unity_run_timeout_s
        try:
            settings.unity_run_timeout_s = 1800
            assert unity_service.run_stale_after_s() > unity_service.run_timeout_s() + 60
        finally:
            settings.unity_run_timeout_s = original

    def test_frame_hook_has_wall_clock_and_play_guards(self):
        """帧钩子必须自带三道保险 + 退出 Play 就收工。"""
        from src.app.services import unity_bridge

        code = unity_bridge.cs_record_start("rec_x", 5.0, 9000, max_seconds=1800)

        assert "unity_auto_rec_deadline" in code          # 墙上时钟上限
        assert "到时间上限" in code
        assert "unity_auto_rec_was_playing" in code       # 挂钩子时在 Play？
        assert "Play 已结束" in code                      # 退出 Play 自动退订
        assert "0.2f" in code.replace(" ", "")            # 5fps → 0.2s 间隔

    def test_frame_hook_gap_matches_five_fps(self):
        from src.app.services import unity_bridge

        code = unity_bridge.cs_record_start("rec_x", 5.0, 9000)
        m = re.search(r'SetFloat\("[^"]*gap[^"]*", ([0-9.]+)f\)', code)
        assert m and abs(float(m.group(1)) - 0.2) < 1e-6

    def test_interrupt_salvages_the_recorder(self, tmp_path, monkeypatch):
        """用户中断（CancelledError）也要补收尾：不补，编辑器里的钩子会一直截图。

        超时分支原本就有 salvage，取消分支以前没有 —— 那条缺口就是"我明明中断了，
        Unity 还在被驱动"的来源之一。
        """
        import asyncio

        seen: list[Path] = []

        async def _salvage(workdir):
            seen.append(Path(workdir))
            return ""

        async def _boom(*args, **kwargs):
            raise asyncio.CancelledError()

        monkeypatch.setattr(unity_service, "_salvage_recording", _salvage)
        monkeypatch.setattr(unity_service, "run_subprocess", _boom)

        with pytest.raises(asyncio.CancelledError):
            asyncio.run(unity_service.run_unity_script(
                "55555555-5555-5555-5555-555555555555", "中断用例", "print(1)",
                workdir=tmp_path))

        assert seen == [tmp_path]
        assert str(tmp_path) not in unity_service._ACTIVE_RUNS   # 登记要清干净

    def test_stop_all_cancels_runs_and_disarms(self, tmp_path, monkeypatch):
        import asyncio

        disarmed: list[str] = []

        async def _disarm():
            disarmed.append("yes")
            return {"frames": {"ok": True}, "ui": {"ok": True}}

        async def _runner():
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                raise

        monkeypatch.setattr(unity_service.unity_bridge, "disarm_all_recorders", _disarm)

        async def _main():
            task = asyncio.create_task(_runner())
            unity_service._ACTIVE_RUNS[str(tmp_path)] = task
            await asyncio.sleep(0)          # 让任务真的跑起来
            out = await unity_service.stop_all_runs()
            return out, task

        out, task = asyncio.run(_main())

        assert out["cancelled_runs"] == [str(tmp_path)]
        assert task.cancelled() and disarmed == ["yes"]
        assert unity_service._ACTIVE_RUNS == {}

    def test_bridge_snippets_are_csharp5(self):
        """桥侧新加的片段同样只许 C# 5（CodeDom 编译，语法错了要到 Unity 才炸）。"""
        from src.app.services import unity_bridge

        texts = {
            "record_start": unity_bridge.cs_record_start("rec_x", 10.0, 3000,
                                                         max_seconds=300),
            "active_scene": unity_bridge._CS_ACTIVE_SCENE,
            "capture_probe_arm": unity_bridge._CS_CAPTURE_PROBE_ARM,
            "capture_probe_read": unity_bridge._CS_CAPTURE_PROBE_READ,
            "shot_file": unity_bridge._CS_SCREENSHOT_FILE,
            "shot_texture": unity_bridge._CS_SCREENSHOT,
        }
        for name, text in texts.items():
            for token in ('$"', "?.", "=>", "nameof("):
                assert token not in text, f"{name} 用了 C# 6+ 语法: {token}"
            assert "{{" not in text and "}}" not in text, f"{name} 有大括号转义残留"
            assert text.count("{") == text.count("}"), f"{name} 大括号不配平"

    def test_active_scene_snippet_reads_without_touching_assets(self):
        """读场景路径的片段必须**只读**：不许出现任何刷新/重编译调用。"""
        from src.app.services import unity_bridge

        code = unity_bridge._CS_ACTIVE_SCENE.lower()

        assert "getactivescene" in code
        for forbidden in ("assetdatabase", "requestscriptcompilation", "refresh",
                          "editorapplication.isplaying", "savetext"):
            assert forbidden.lower() not in code, f"只读片段里出现了 {forbidden}"
