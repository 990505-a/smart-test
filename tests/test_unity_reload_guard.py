""""永不触发 Unity 域重载"这条硬规则的护栏（src/app/agents/unity/tools.py）。

2026-09-22 补的两个洞，这里各钉一条用例：

1. ``unity_mcp_call`` 只拦了 ``manage_editor`` 的动作和 C# 片段 —— 直接点名
   ``refresh_unity``（插件的"刷新 + 请求重编译"工具）能溜过去，参数里写
   ``compile="request"`` 就是一次实打实的域重载。现在按**工具名**拦。
2. ``manage_editor`` 还有 ``deploy_package`` / ``restore_package`` 两个动作，走的
   是包部署路径（内部 ``AssetDatabase.Refresh(ForceUpdate)`` + 重编译），同样要拦。

另外验一下 ``_accepts_state_action``：coplay 的 ``manage_editor`` 把 action 限成了
不含"取状态"的枚举，平台不该拿 ivan 方言的 ``get_state`` 去调它（桥日志里这种无效
调用积了 170 条）。
"""

from __future__ import annotations

import asyncio
import json

import pytest

from src.app.agents.unity import tools as unity_tools
from src.app.services import unity_bridge, unity_service


def _call(tool: str, arguments: dict) -> dict:
    """照模型看到的签名调用：`arguments` 是 **JSON 字符串**。"""
    return asyncio.run(unity_tools.unity_mcp_call.ainvoke(
        {"tool": tool, "arguments": json.dumps(arguments)}))


@pytest.fixture
def _spy(monkeypatch):
    """调用真桥上就记一笔 —— 护栏用例要求这里是空的。"""
    seen: list[tuple[str, dict]] = []

    async def _fake(tool: str, arguments: dict) -> dict:
        seen.append((tool, arguments))
        return {"success": True}

    monkeypatch.setattr(unity_service, "mcp_call", _fake)
    return seen


@pytest.mark.parametrize("tool, arguments", [
    # 刷新 + 请求重编译 = 域重载（插件的 refresh_unity）
    ("refresh_unity", {"mode": "force", "compile": "request"}),
    ("refresh_unity", {"mode": "if_dirty"}),          # 不带 compile 也不放行
    ("assets-refresh", {}),                            # ivan 方言的同一个动作
    ("manage_script", {"action": "create", "name": "Foo"}),  # 改 C# 会重编译
    ("manage_editor", {"action": "deploy_package"}),   # 包部署内部就刷新资产
    ("manage_editor", {"action": "restore_package"}),
    ("Manage_Editor", {"action": "Play"}),             # 大写/大小写混写同样拦
])
def test_reload_triggering_calls_are_refused(tool, arguments, _spy):
    out = _call(tool, arguments)

    assert out["success"] is False
    assert "域重载" in out["error"]
    assert _spy == [], "护栏必须在真正调桥之前拦下"


def test_harmless_call_still_passes_through(_spy):
    out = _call("find_gameobjects", {"search_term": "Button"})

    assert out == {"success": True}
    assert _spy == [("find_gameobjects", {"search_term": "Button"})]


@pytest.mark.parametrize("text", [
    '{"compile": "request"}',
    '{"compile":"request"}',
    '{"options": {"refresh": "immediate"}}',
    '{"refresh":   "sync"}',
])
def test_compact_fragment_match(text):
    """JSON 带不带空格都得认出来（之前只匹配有空格/无空格的一种写法）。"""
    assert unity_tools._reload_trigger_hit(text) is not None


def test_unrelated_arguments_are_not_flagged():
    assert unity_tools._reload_trigger_hit('{"search_term": "Play Button"}') is None


def test_accepts_state_action_skips_coplay_manage_editor():
    """coplay 的 manage_editor 枚举里没有取状态的值 → 不该去调它。"""
    coplay_manage_editor = {
        "inputSchema": {"properties": {"action": {"enum": [
            "telemetry_status", "play", "pause", "stop", "set_active_tool",
            "add_tag", "add_layer", "undo", "redo",
        ]}}}
    }
    assert unity_bridge._accepts_state_action(coplay_manage_editor) is False


@pytest.mark.parametrize("schema", [
    {},                                                    # 没有 schema：可以试
    {"inputSchema": {}},
    {"inputSchema": {"properties": {}}},
    {"inputSchema": {"properties": {"action": {"type": "string"}}}},   # 自由格式
    {"inputSchema": {"properties": {"action": {"enum": ["get_state"]}}}},
    {"inputSchema": {"properties": {"operation": {"enum": ["state", "play"]}}}},
])
def test_accepts_state_action_allows_state_capable_tools(schema):
    assert unity_bridge._accepts_state_action(schema) is True


# ---------------------------------------------------------------------------
# 桥自己会"刷新并请求重编译"的那批工具（preflight(refresh_if_dirty=True)）
# ---------------------------------------------------------------------------

class _FakeClient:
    """够用的假客户端：记录被代发的工具调用。"""

    def __init__(self) -> None:
        self.sent: list[tuple[str, dict]] = []

    def _run(self, fn):
        return None

    def call(self, tool, args, *, timeout=None):  # noqa: ANN001
        raise AssertionError("真的发出去了")


def _client_with_transport() -> unity_bridge.McpClient:
    client = unity_bridge.McpClient.__new__(unity_bridge.McpClient)
    client._gate = __import__("threading").Lock()
    client._t = type("T", (), {"rpc": staticmethod(lambda *a, **k: {"result": {}})})()
    client._run = lambda fn: {"result": {"ok": True}}  # type: ignore[method-assign]
    return client


@pytest.fixture
def _gate(monkeypatch):
    """把"闸门看到的那一眼现场"直接钉死（真读要连 Unity，单测里没有）。

    ``known=False`` 模拟**读不到**（编辑器忙/掉线）—— 这是 2026-09-23 事故的根因之一：
    以前读不到会 fail-open 放行，现在必须拒绝。
    """
    def _set(*, dirty: bool = False, playing: bool = False, known: bool = True):
        state = None if not known else {
            "dirty": dirty, "playing": playing, "knows_dirty": True}
        monkeypatch.setattr(unity_bridge, "_gate_state", lambda client: state)
    return _set


@pytest.mark.parametrize("tool", sorted(unity_bridge._PREFLIGHT_GATED_TOOLS))
def test_dirty_project_refuses_preflight_gated_tools(tool, _gate):
    """脏工程下，带 preflight 的工具一个都不能代发 —— 桥会借机重编译。"""
    _gate(dirty=True)
    client = _client_with_transport()

    with pytest.raises(unity_bridge.UnityBridgeError) as exc:
        client.call(tool, {})

    msg = str(exc.value)
    assert tool in msg and "域重载" in msg
    # 文案必须**可执行**：不能叫人去 Ctrl+R（那是白刷），要指到 unity_sync_assets
    assert "unity_sync_assets" in msg and "Ctrl+R" in msg
    assert "请先在 Unity 里手动刷新（Ctrl+R" not in msg


@pytest.mark.parametrize("tool", sorted(unity_bridge._PREFLIGHT_GATED_TOOLS))
def test_dirty_while_playing_is_refused_hard(tool, _gate):
    """脏 + Play 是最危险的组合（Play 中域重载会毁掉这一局、实测卡死编辑器）。"""
    _gate(dirty=True, playing=True)
    client = _client_with_transport()

    with pytest.raises(unity_bridge.UnityBridgeError) as exc:
        client.call(tool, {})

    msg = str(exc.value)
    assert tool in msg and "Play" in msg and "退出 Play" in msg


@pytest.mark.parametrize("tool", sorted(unity_bridge._PREFLIGHT_GATED_TOOLS))
def test_unreadable_state_fails_closed(tool, _gate):
    """读不到状态 → **拒绝**（2026-09-23：以前是 fail-open，那记 manage_scene 就是这么漏的）。"""
    _gate(known=False)
    client = _client_with_transport()

    with pytest.raises(unity_bridge.UnityBridgeError) as exc:
        client.call(tool, {})

    assert "读不到" in str(exc.value)


def test_clean_project_passes(_gate):
    _gate(dirty=False)
    client = _client_with_transport()

    assert client.call("find_gameobjects", {"search_term": "x"}) == {"ok": True}


def test_dirty_project_still_allows_harmless_tools(_gate):
    """脏只拦"会带 preflight"的那批；读控制台/截图这类照常。"""
    _gate(dirty=True)
    client = _client_with_transport()

    out = client.call("read_console", {"action": "get"})

    assert out == {"ok": True}


def test_dirty_flag_is_read_from_nested_state_payload():
    """各家状态形状不一样，脏标志要能在任意层级里挖出来。"""
    payload = {"data": {"assets": {"external_changes_dirty": True}}}

    assert unity_bridge._deep_find(payload, "external_changes_dirty") is True
    assert unity_bridge._deep_find({"data": {}}, "external_changes_dirty") is None


# ---------------------------------------------------------------------------
# 安全清理：unity_sync_assets（只刷新，不重编译；非 Play 才能做）
# ---------------------------------------------------------------------------

class _SyncClient:
    """记录代发出去的调用，返回一个合法的 tools/call 响应。"""

    def __init__(self) -> None:
        self.sent: list[tuple[str, dict]] = []

    def call(self, tool, args, *, timeout=None):  # noqa: ANN001
        self.sent.append((tool, args))
        return {"content": [{"type": "text", "text": "{\"ok\":true}"}]}


def _stub_sync(monkeypatch, states: list[dict | None]) -> _SyncClient:
    """``states`` 按顺序喂给连续的 _gate_state 调用（第一次读 + 清完再读）。"""
    client = _SyncClient()
    pending = list(states)

    def _fake_gate(_client):  # noqa: ANN001
        return pending.pop(0) if pending else states[-1]

    monkeypatch.setattr(unity_bridge, "_gate_state", _fake_gate)
    monkeypatch.setattr(unity_bridge, "_get_client", lambda: client)
    monkeypatch.setattr(unity_bridge, "_resolve", lambda op, *a, **k: (
        "refresh_unity",
        {"properties": {k: {} for k in ("mode", "scope", "compile", "wait_for_ready")}},
        "coplay"))
    return client


def test_sync_assets_refused_while_playing(monkeypatch):
    """Play 中不做刷新（刷新会打断这一局）—— 拒绝并说清楚。"""
    client = _stub_sync(monkeypatch, [{"dirty": True, "playing": True, "knows_dirty": True}])

    out = asyncio.run(unity_bridge.sync_assets())

    assert out["success"] is False and "Play" in out["error"]
    assert client.sent == [], "被拒时不该真的发出去"


def test_sync_assets_uses_compile_none(monkeypatch):
    """清理必须**不带** compile=request：带就是一次域重载，正是我们要避免的事。"""
    client = _stub_sync(monkeypatch, [
        {"dirty": True, "playing": False, "knows_dirty": True},
        {"dirty": False, "playing": False, "knows_dirty": True},
    ])

    out = asyncio.run(unity_bridge.sync_assets())

    tool, args = client.sent[0]
    assert tool == "refresh_unity"
    assert args["compile"] == "none"
    assert args["mode"] == "if_dirty"
    assert args["wait_for_ready"] is False     # 别让插件去 pump PlayerLoop（那会递归）
    assert out["success"] is True and out["dirty_after"] is False


def test_sync_assets_reads_state_before_and_after(monkeypatch):
    """清完必须**再读一次**：只报"我发过刷新了"等于没说（用户要的是清没清掉）。"""
    client = _stub_sync(monkeypatch, [
        {"dirty": True, "playing": False, "knows_dirty": True},
        {"dirty": True, "playing": False, "knows_dirty": True},
    ])

    out = asyncio.run(unity_bridge.sync_assets())

    assert out["success"] is False and out["dirty_after"] is True
    assert "重启 unity-mcp" in out["hint"]


def test_sync_assets_unreadable_state_does_not_fire(monkeypatch):
    client = _stub_sync(monkeypatch, [None])

    out = asyncio.run(unity_bridge.sync_assets())

    assert out["success"] is False and client.sent == []

