"""Unity 自动化桥 —— 一条通往 Unity MCP 服务器的**通用**通道。

历史：这里原来是 LuaRemoteServer（游戏内 Lua 桥 :16666），点击、读文本、造数据
全靠对方游戏侧提供的 Lua 框架，换一款游戏（甚至一款没有 Lua 层的 Unity 游戏）
整套作废。现在换成**标准 MCP**：任何 Unity MCP 服务器（CoplayDev/unity-mcp、
IvanMurzak/Unity-MCP …）都能接，平台只依赖三类通用原语 ——

1. 场景/对象查询与组件反射（谁在场景里、这个对象的组件与字段是什么）
2. 编辑器控制（Play / Pause / Stop / 刷新资产）
3. 任意 C# 执行（``execute_code`` / ``script-execute``）—— 通用的逃逸口

而"这个游戏怎么登入、按钮叫什么、怎么造前置数据"属于**业务知识**，沉淀在用例
脚本与记忆里，不写死在工具里。这与 Playwright 面对一个新网站是同构的。

一个实现，两处使用者：

- 平台工具与探针：``status`` / ``call`` / ``screenshot`` … （async，内部 to_thread）
- **沉淀下来的用例脚本**：``Unity`` 同步客户端（脚本 subprocess 里直接 import，
  见 ``unity_service.run_unity_script`` 的 prelude）

协议层只用标准库（urllib + json）：MCP streamable HTTP 的 JSON-RPC 2.0
（initialize / tools/list / tools/call / resources/read）。**显式绕过系统代理** ——
与 ``core/http.py::local_client`` 同一个理由：macOS 上死掉的本地服务会被系统代理
变成 HTTP 502，看着像"服务返回了错误"而不是"服务没起"。

服务器方言（工具名的差异）不写死：先按服务器自报的名字猜方言，再用**服务器自己
广播的 inputSchema** 过滤/改名参数，认不出来的参数直接丢掉。真实的入参差异由
``unity_mcp_tools`` 暴露给模型自查，``unity_mcp_call`` 直接透传 —— 永远留一条
不需要改平台代码的路。
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import json
import os
import queue
import re
import shlex
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from src.app.core.breaker import Guard
from src.app.core.config import settings

_PROTOCOL_VERSION = "2025-06-18"
_CLIENT_INFO = {"name": "smart-test-platform", "version": "1.0"}
_DEFAULT_TIMEOUT = 60.0
_TOOLS_CACHE_TTL = 60.0

# C# 片段把结果写进 Unity Console，平台从返回文本里抠这一行（见 _parse_marker）。
# 用日志而不是返回值：各家的 execute_code 约定不同（有的包成方法体、有的要完整类），
# 但"语句 + Debug.Log"在两种约定下都成立。
_MARKER = "UNITY_BRIDGE:"


class UnityBridgeError(RuntimeError):
    """桥不可用或调用失败。工具层捕获它并转成 {"success": False, ...}。"""


# ===========================================================================
# 传输层：JSON-RPC 2.0 over streamable HTTP / stdio
# ===========================================================================

def _parse_sse(body: str) -> list[dict]:
    """从 text/event-stream 响应里取出 data: 行承载的 JSON-RPC 消息。

    逐行解析（不是按空行分块），并且先归一化换行：实测这台服务器用 ``\r\n``，
    而且一次响应里会有**多个事件**（先一条 notifications/message 日志，再才是结果）。
    按 ``\n\n`` 分块会把两个事件的 data 行粘成一个 JSON → 整条响应被当成"无响应"。
    """
    out: list[dict] = []
    for raw_line in body.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line.startswith("data:"):
            continue
        chunk = line[5:].strip()
        if not chunk:
            continue
        try:
            out.append(json.loads(chunk))
        except json.JSONDecodeError:
            continue
    return out


class _HttpTransport:
    """streamable HTTP：一个 POST 一次请求，session id 走 Mcp-Session-Id 头。"""

    def __init__(self, url: str, timeout: float) -> None:
        self.url = url
        self.timeout = timeout
        self.session_id: str | None = None
        # ProxyHandler({}) = 不走系统代理（见模块 docstring）
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def rpc(self, method: str, params: dict | None = None, *,
            notify: bool = False, timeout: float | None = None) -> dict | None:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        if not notify:
            payload["id"] = 1
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        req = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
        try:
            with self._opener.open(req, timeout=timeout or self.timeout) as resp:
                sid = resp.headers.get("Mcp-Session-Id")
                if sid:
                    self.session_id = sid
                raw = resp.read().decode("utf-8", errors="replace")
                ctype = (resp.headers.get("Content-Type") or "").lower()
                status = resp.status
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:400]
            except Exception:  # noqa: BLE001
                pass
            if exc.code == 404 and self.session_id:
                # 会话过期：丢掉 session，让上层重建一次（MCP 规范允许服务端随时回收）
                self.session_id = None
                raise UnityBridgeError(f"会话已过期（HTTP 404）{detail}") from exc
            raise UnityBridgeError(
                f"MCP HTTP {exc.code}: {detail or exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise UnityBridgeError(f"无法连接 Unity MCP 服务器 {self.url}: {exc.reason}") from exc
        except TimeoutError as exc:
            raise UnityBridgeError(f"Unity MCP 请求超时（{timeout or self.timeout}s）") from exc

        if not raw.strip():
            return None
        if "text/event-stream" in ctype:
            for msg in _parse_sse(raw):
                if notify or msg.get("id") == payload.get("id"):
                    return msg
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise UnityBridgeError(
                f"MCP 返回的不是 JSON（HTTP {status}）: {raw[:200]}") from exc

    def close(self) -> None:
        return None


class _StdioTransport:
    """stdio：常驻一个子进程，逐行收发 JSON-RPC。

    读取放在后台线程 + 队列里（Windows 的 select 不支持管道，线程方案跨平台）。
    默认传输是 HTTP；stdio 用于"服务器只能在本地以命令方式拉起"的场合。
    """

    def __init__(self, command: str, timeout: float) -> None:
        self.command = command
        self.timeout = timeout
        self.session_id: str | None = None
        self._proc: subprocess.Popen | None = None
        self._lines: queue.Queue[str | None] = queue.Queue()
        self._lock = threading.Lock()

    def _spawn(self) -> None:
        argv = shlex.split(self.command)
        if not argv:
            raise UnityBridgeError("UNITY_MCP_COMMAND 为空，stdio 模式无法拉起服务器")
        try:
            self._proc = subprocess.Popen(
                argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1)
        except OSError as exc:
            raise UnityBridgeError(f"stdio 启动失败（{self.command}）: {exc}") from exc
        threading.Thread(target=self._pump, args=(self._proc,), daemon=True).start()

    def _pump(self, proc: subprocess.Popen) -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            self._lines.put(line)
        self._lines.put(None)

    def rpc(self, method: str, params: dict | None = None, *,
            notify: bool = False, timeout: float | None = None) -> dict | None:
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._spawn()
            assert self._proc is not None and self._proc.stdin is not None
            payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
            if params is not None:
                payload["params"] = params
            if not notify:
                payload["id"] = 1
            try:
                self._proc.stdin.write(json.dumps(payload) + "\n")
                self._proc.stdin.flush()
            except (OSError, ValueError) as exc:
                raise UnityBridgeError(f"stdio 写入失败: {exc}") from exc
            if notify:
                return None
            deadline = time.monotonic() + (timeout or self.timeout)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise UnityBridgeError(f"Unity MCP stdio 响应超时（{timeout or self.timeout}s）")
                try:
                    line = self._lines.get(timeout=remaining)
                except queue.Empty:
                    raise UnityBridgeError("Unity MCP stdio 响应超时") from None
                if line is None:
                    self._proc = None
                    raise UnityBridgeError("Unity MCP stdio 进程已退出")
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue  # 服务器往 stdout 打日志时的噪声行
                if msg.get("id") == payload.get("id"):
                    return msg

    def close(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()


# ===========================================================================
# MCP 客户端：握手 / 工具清单 / 调用 / 读资源
# ===========================================================================

def _detect_flavor(server_name: str) -> str:
    name = (server_name or "").lower()
    if "mcp-for-unity" in name or "mcpforunity" in name or "coplay" in name:
        return "coplay"
    if "gamedev" in name or "ivan" in name:
        return "ivan"
    return "generic"


class McpClient:
    """一个 Unity MCP 服务器的会话（懒初始化 + 工具清单缓存）。

    **同一时刻只允许一个请求在飞**（``self._gate``）：这台服务器（mcp-for-unity）
    一次只服务一条请求 —— 并发发过去，它把第一条正常回完，其余的**永远不会回**，
    客户端就卡死在读响应体上（实测用 faulthandler 抓过栈：线程停在
    ``http/client.py::_read_next_chunk_size``）。表现是"界面上一堆工具卡片一直转圈"。

    什么时候会并发：模型一步里同时发多个工具调用（实测：write_todos +
    两个 unity_find_objects），平台用 ``asyncio.to_thread`` 各起一条线程，
    于是撞在同一台服务器上。串行化代价几乎为零（Unity 那边本来就是一个主线程
    顺序执行），换来的是不会再有"点了没反应"。
    """

    def __init__(self, transport, *, flavor_hint: str = "auto") -> None:
        self._t = transport
        self.server_info: dict = {}
        self.protocol: str = ""
        self.flavor: str = flavor_hint if flavor_hint != "auto" else "generic"
        self._ready = False
        self._tools: list[dict] | None = None
        self._tools_at = 0.0
        # 可重入：同一个线程里嵌套调用（工具内部再查一次）不该把自己锁死。
        self._gate = threading.RLock()

    # ---- 握手 -------------------------------------------------------------
    def _handshake(self) -> None:
        with self._gate:
            resp = self._t.rpc("initialize", {
                "protocolVersion": _PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": _CLIENT_INFO,
            })
            if resp is None:
                raise UnityBridgeError("initialize 无响应")
            if "error" in resp:
                raise UnityBridgeError(f"initialize 失败: {resp['error']}")
            result = resp.get("result") or {}
            self.server_info = result.get("serverInfo") or {}
            self.protocol = result.get("protocolVersion") or ""
            if self.flavor == "generic":
                self.flavor = _detect_flavor(self.server_info.get("name", ""))
            self._t.rpc("notifications/initialized", {}, notify=True)
            self._ready = True

    def _ensure(self) -> None:
        if not self._ready:
            self._handshake()

    def ensure_ready(self) -> None:
        """幂等握手。**需要读 flavor / 资源模板的地方必须先调它** ——
        否则冷客户端上 flavor 还是兜底的 "generic"，资源模板取不到，
        会静默退到错误的工具路径（实测踩过：object_info 因此读不到组件）。"""
        self._ensure()

    def reset(self) -> None:
        """会话失效后重建（HTTP 404 / stdio 进程退出）。"""
        self._ready = False
        self._tools = None
        try:
            self._t.close()
        except Exception:  # noqa: BLE001
            pass
        self._t.session_id = None

    def _run(self, fn):
        """带「会话过期自愈」的调用：HTTP 404 丢会话时重建再试一次。

        为什么必须在客户端这一层：``_rpc()`` 只包住了显式走它的路径，资源读和
        直接 ``call`` 不走 —— 实测踩过：平台长驻进程里 Unity 明明连着，实例清单
        和编辑器状态却一直读空（工具列表正常，因为它走 _rpc 自愈了），界面上表现
        成"桥正常但 Unity 未连接"。404 意味着服务器根本没收到这次请求，重放安全。
        """
        last: Exception | None = None
        for attempt in (1, 2):
            self._ensure()
            try:
                return fn()
            except UnityBridgeError as exc:
                last = exc
                if attempt == 2 or "会话已过期" not in str(exc):
                    raise
                self.reset()
        raise last if last else UnityBridgeError("未知错误")

    # ---- 工具 -------------------------------------------------------------
    def tools(self, *, refresh: bool = False) -> list[dict]:
        with self._gate:            # 清单缓存也是共享状态：并发进来会打架
            self._ensure()
            fresh = (self._tools is not None
                     and (time.monotonic() - self._tools_at) < _TOOLS_CACHE_TTL)
            if self._tools is not None and fresh and not refresh:
                return self._tools
            resp = self._run(lambda: self._t.rpc("tools/list", {}))
            if resp is None or "error" in resp:
                raise UnityBridgeError(f"tools/list 失败: {(resp or {}).get('error')}")
            self._tools = ((resp.get("result") or {}).get("tools") or [])
            self._tools_at = time.monotonic()
            return self._tools

    def find_tool(self, names: tuple[str, ...]) -> dict | None:
        """按候选名（按优先级）在服务器广播的工具清单里挑第一个存在的。"""
        by_name = {t.get("name"): t for t in self.tools()}
        for n in names:
            if n in by_name:
                return by_name[n]
        return None

    def call(self, tool: str, args: dict, *, timeout: float | None = None) -> dict:
        with self._gate:
            resp = self._run(
                lambda: self._t.rpc("tools/call", {"name": tool, "arguments": args},
                                    timeout=timeout))
            if resp is None:
                raise UnityBridgeError(f"工具 {tool} 无响应")
            if "error" in resp:
                raise UnityBridgeError(f"工具 {tool} 调用失败: {resp['error']}")
            return resp.get("result") or {}

    def read_resource(self, uri: str, *, timeout: float | None = None) -> dict:
        with self._gate:
            resp = self._run(
                lambda: self._t.rpc("resources/read", {"uri": uri}, timeout=timeout))
            if resp is None:
                raise UnityBridgeError(f"资源 {uri} 无响应")
            if "error" in resp:
                raise UnityBridgeError(f"资源 {uri} 读取失败: {resp['error']}")
            return resp.get("result") or {}


# ---- 客户端缓存（settings 改了自动重建） -------------------------------------

_client: McpClient | None = None
_client_key: tuple | None = None
_client_lock = threading.Lock()

_bridge_guard = Guard("Unity 桥")


def _make_transport() -> tuple[Any, tuple]:
    transport = (settings.unity_mcp_transport or "http").strip().lower()
    if transport == "stdio":
        command = (settings.unity_mcp_command or "").strip()
        if not command:
            command = ("uvx --from mcpforunityserver==10.2.0 mcp-for-unity "
                   "--transport stdio")
        return _StdioTransport(command, _DEFAULT_TIMEOUT), ("stdio", command)
    return _HttpTransport(settings.unity_mcp_url, _DEFAULT_TIMEOUT), ("http", settings.unity_mcp_url)


def _get_client() -> McpClient:
    global _client, _client_key
    with _client_lock:
        t, key = _make_transport()
        if _client is None or _client_key != key:
            if _client is not None:
                _client.reset()
            _client = McpClient(t, flavor_hint=(settings.unity_mcp_server or "auto").strip().lower())
            _client_key = key
        return _client


def _rpc(fn, *args, **kwargs):
    """跑一次需要握手的操作；握手/传输失败记熔断，会话过期自动重来一次。"""
    last: Exception | None = None
    for attempt in (1, 2):
        client = _get_client()
        try:
            result = fn(client, *args, **kwargs)
            _bridge_guard.ok()
            return result
        except UnityBridgeError as exc:
            last = exc
            expired = "会话已过期" in str(exc) or "进程已退出" in str(exc)
            _bridge_guard.fail()
            if expired and attempt == 1:
                client.reset()
                continue
            raise
    raise last if last else UnityBridgeError("未知错误")


# ===========================================================================
# 方言：工具名候选 + 参数别名（用服务器广播的 inputSchema 过滤）
# ===========================================================================

# op -> [(方言, 工具名), ...]，按优先级。auto 检测到的方言排最前，其余兜底。
_OP_TOOLS: dict[str, list[tuple[str, str]]] = {
    "editor_action": [("coplay", "manage_editor"), ("ivan", "editor-application-set-state")],
    "editor_state": [("ivan", "editor-application-get-state"), ("coplay", "manage_editor")],
    "refresh": [("coplay", "refresh_unity"), ("ivan", "assets-refresh")],
    "find_objects": [("coplay", "find_gameobjects"), ("ivan", "gameobject-find")],
    "object_info": [("coplay", "manage_components"), ("ivan", "gameobject-component-get")],
    "console": [("coplay", "read_console"), ("ivan", "console-get-logs")],
    "screenshot": [("coplay", "manage_camera"), ("ivan", "screenshot-game-view")],
    "exec_csharp": [("coplay", "execute_code"), ("ivan", "script-execute")],
    "run_tests": [("coplay", "run_tests"), ("ivan", "tests-run")],
    "test_job": [("coplay", "get_test_job")],
    "scene": [("coplay", "manage_scene"), ("ivan", "scene-list-opened")],
}

# 平台侧的逻辑参数名 -> 各服务器可能用的名字（按 schema 里实际存在的挑第一个）
_ALIASES: dict[str, tuple[str, ...]] = {
    "action": ("action", "operation", "command"),
    "target": ("target", "object", "object_path", "hierarchy_path", "path", "name_or_path"),
    "name": ("name", "search_term", "keyword", "object_name", "name_contains"),
    "path": ("path", "hierarchy_path", "object_path"),
    "component": ("component", "component_type", "type"),
    "tag": ("tag",),
    "limit": ("limit", "page_size", "max_results", "count", "max", "max_count"),
    "find_inactive": ("search_inactive", "include_inactive", "find_inactive"),
    "search_method": ("search_method", "method"),
    "depth": ("depth", "max_depth"),
    "filter_text": ("filter_text", "filter", "search_text", "text_filter", "level"),
    "types": ("types", "log_types"),
    "code": ("code", "source", "script", "csharp", "source_code"),
    "text": ("text", "value", "content"),
    "capture_source": ("capture_source", "source", "view", "camera_source"),
    "include_image": ("include_image", "return_image", "as_image", "include_screenshot"),
    "max_resolution": ("max_resolution", "resolution", "max_size"),
    "job_id": ("job_id", "jobId", "id", "test_job_id"),
    "mode": ("mode", "test_mode", "platform", "test_platform"),
    "test_filter": ("test_filter", "filter", "testFilter", "test_name"),
    "state": ("state", "status", "target_state"),
    "group": ("group", "tool_group"),
}

_IVAN_STATE = {"play": "Playing", "pause": "Paused", "stop": "Stopped", "refresh": "Playing"}

# 平台的逻辑查询 -> coplay 的 search_method 枚举（实测自 mcp-for-unity-server 3.4.7：
# find_gameobjects 只接受 search_term + search_method，别的查询维度都靠这两个表达）
_SEARCH_METHOD = {"name": "by_name", "path": "by_path",
                  "component": "by_component", "tag": "by_tag"}

# 这个方言的对象数据只在资源里（工具只负责"按 id 取 id"）——实测其
# manage_components 的 action 只接受 add/remove/set_property，读数据要读资源。
_RESOURCE_TEMPLATES: dict[str, dict[str, str]] = {
    "coplay": {
        "editor_state": "mcpforunity://editor/state",
        "instances": "mcpforunity://instances",
        "gameobject": "mcpforunity://scene/gameobject/{id}",
        "components": "mcpforunity://scene/gameobject/{id}/components",
    },
}


def _pick_key(props: set[str], logical: str) -> str | None:
    for alias in _ALIASES.get(logical, (logical,)):
        if alias in props:
            return alias
    return _ALIASES.get(logical, (logical,))[0] if not props else None


def _adapt_args(builder: dict[str, Any], schema: dict | None) -> dict:
    """把平台侧逻辑参数映射成该服务器 schema 认得的名字，认不出的丢掉。

    schema 没有声明 properties（自由格式）时原样透传 —— 宁可让服务器自己报错，
    也不要静默丢参数。
    """
    props = set(((schema or {}).get("properties") or {}).keys())
    if not props:
        return {k: v for k, v in builder.items() if v not in (None, "", [])}
    out: dict[str, Any] = {}
    for logical, value in builder.items():
        if value in (None, "", []):
            continue
        key = _pick_key(props, logical)
        if key and key in props:
            out[key] = value
    return out


def _resolve(op: str, client: McpClient | None = None,
             call=None) -> tuple[str, dict, str]:
    """挑出这个操作该用的工具 + 它的 schema；找不到就报错带上可用清单。"""
    client = client or _get_client()
    call = call or _rpc
    candidates = sorted(_OP_TOOLS[op], key=lambda c: 0 if c[0] == client.flavor else 1)
    hit = _first_present(client, candidates)
    if hit is not None:
        return hit
    # 工具可能默认关在"工具组"里（实测 mcp-for-unity-server：execute_code 在
    # scripting_ext、run_tests 在 testing，默认 enabled=false）→ 按需激活一次再找。
    if _activate_group_for(client, [n for _, n in candidates], call):
        hit = _first_present(client, candidates)
        if hit is not None:
            return hit
    available = ", ".join(t.get("name", "?") for t in client.tools())
    raise UnityBridgeError(
        f"这台 Unity MCP 服务器没有 {op} 对应的工具（试过 {[n for _, n in candidates]}）。"
        f"用 unity_mcp_tools 看服务器实际提供什么，再用 unity_mcp_call 直接调用。"
        f"当前可用：{available}")


def _first_present(client: McpClient,
                   candidates: list[tuple[str, str]]) -> tuple[str, dict, str] | None:
    for flavor, name in candidates:
        tool = client.find_tool((name,))
        if tool is not None:
            return name, (tool.get("inputSchema") or {}), flavor
    return None


def _activate_group_for(client: McpClient, tool_names: list[str], call=None) -> bool:
    """把"包含这些工具的组"激活（服务器支持工具组时）。成功过一次就够。"""
    manage = client.find_tool(("manage_tools", "manage_tool_groups"))
    if manage is None:
        return False
    call = call or _rpc
    try:
        listed = unwrap(call(lambda c: c.call("manage_tools",
                                              {"action": "list_groups"}, timeout=30.0)))
        payload = listed.get("data")
        if not isinstance(payload, dict):
            text = (listed.get("text") or "").strip()
            payload = json.loads(text) if text.startswith("{") else {}
        # 层级不固定：有的实现直接给 {"groups": [...]}，有的再套一层 {"data": {...}}
        if isinstance(payload.get("data"), dict) and "groups" not in payload:
            payload = payload["data"]
        groups = payload.get("groups") or []
        for group in groups:
            if group.get("enabled"):
                continue
            if set(group.get("tools") or ()) & set(tool_names):
                call(lambda c: c.call("manage_tools",
                                      {"action": "activate", "group": group.get("name")},
                                      timeout=30.0))
                client.tools(refresh=True)
                return True
    except (UnityBridgeError, json.JSONDecodeError):
        return False
    return False


# ===========================================================================
# 结果解包：MCP content blocks -> dict / 截图落盘 / Debug.Log 标记
# ===========================================================================

#: 用例执行时 runner 会把「本次运行目录」放进这个环境变量：不带文件名的
#: ``u.screenshot()`` 也要落进那一次运行的产物目录，否则截了一张到公共目录，
#: 前端按"这次执行"取产物就永远少一张（Playwright 那边没这个问题，它所有产物
#: 天然都在运行目录里）。
_SHOT_DIR_ENV = "UNITY_SHOT_DIR"
#: 步骤轨迹（JSONL）落盘位置，同样由 runner 注入。
_TRACE_FILE_ENV = "UNITY_TRACE_FILE"
#: 起跑线快照的落盘位置（本次运行的"候选起跑线"，跑通才被平台提升为正式的那份）。
_START_STATE_ENV = "UNITY_START_STATE_FILE"


def _shots_dir() -> Path:
    env = os.environ.get(_SHOT_DIR_ENV, "").strip()
    d = Path(env) if env else (settings.workspace_dir / "default" / "unity-auto" / "screenshots")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_image(data_b64: str, mime: str = "image/png", path: str | None = None) -> str:
    import base64

    target = _resolve_shot_path(path) or (_shots_dir() / f"shot_{time.strftime('%Y%m%d_%H%M%S')}.png")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(base64.b64decode(data_b64))
    return str(target)


def _resolve_shot_path(path: str | None) -> Path | None:
    """把调用方给的保存路径变成**绝对路径**。

    相对路径按 ``_shots_dir()`` 算，不是按进程 cwd —— 实测踩过：智能体调
    ``unity_screenshot(save_path="00_current_state.png")``，文件落在了平台进程的
    工作目录（仓库根），它随后在 workspace 里 glob 找不到，白折腾一轮。
    而用例脚本那边 ``_shots_dir()`` 就是它自己的运行目录（runner 注入了
    ``UNITY_SHOT_DIR``），相对路径的语义不变。
    """
    if not path:
        return None
    target = Path(path)
    return target if target.is_absolute() else (_shots_dir() / target)


def _parse_marker(text: str) -> dict | None:
    """从 C# 片段经 Debug.Log 打回的文本里抠出结构化结果。"""
    for line in (text or "").splitlines():
        idx = line.find(_MARKER)
        if idx < 0:
            continue
        try:
            return json.loads(line[idx + len(_MARKER):].strip())
        except json.JSONDecodeError:
            continue
    return None


def _failure_reason(data: dict) -> str:
    """失败原因在不同实现里放的字段不一样（error / hint / data.reason）。"""
    inner = data.get("data")
    for candidate in (data.get("error"), data.get("hint"),
                      inner.get("reason") if isinstance(inner, dict) else None):
        if candidate:
            return str(candidate)
    return "工具报告失败（success=false）"


def unwrap(raw: dict, *, save_image: bool = True) -> dict:
    """把 tools/call 的 result 拆成 {success, text, data, images, error}。"""
    blocks = raw.get("content") or []
    texts: list[str] = []
    images: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            texts.append(block.get("text", ""))
        elif block.get("type") == "image" and save_image and block.get("data"):
            try:
                images.append(_save_image(block["data"], block.get("mimeType", "image/png")))
            except Exception as exc:  # noqa: BLE001
                texts.append(f"[截图保存失败: {exc}]")
        elif block.get("type") == "resource":
            res = block.get("resource") or {}
            texts.append(str(res.get("text") or res.get("uri") or ""))
    text = "\n".join(t for t in texts if t)
    data: Any = None
    if len(texts) == 1 and text.strip().startswith(("{", "[")):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
    if data is None and raw.get("structuredContent"):
        data = raw["structuredContent"]
    if raw.get("isError"):
        return {"success": False, "error": text or "工具返回 isError", "images": images}
    # 实测坑：这台服务器的工具失败是 **200 + 正文 {"success": false}**，不是 MCP 的
    # isError。不认这一层，`click` 这种会"报成功但正文写着 session 不可用" ——
    # 模型会把"点了个寂寞"当成通过。
    if isinstance(data, dict) and data.get("success") is False:
        return {"success": False, "error": _failure_reason(data),
                "data": data, "text": text, "images": images}
    return {"success": True, "text": text, "data": data, "images": images}


# ===========================================================================
# 通用 C# 片段（点不了、读不到时的兜底；也是对"任意 Unity 游戏"通用的部分）
# ===========================================================================

def _cs_str(value: str) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


_CS_FIND = r"""
var __target = {target};
var __want = __target.Trim();
UnityEngine.GameObject __go = null;
// 两趟：先只认**当前可见**的对象，再放宽到全部。
// 真游戏里同名对象很常见（一个 SaveButton 在每个面板里各一份，只有一个是开着的），
// 直接取第一个大概率点到没激活的那份 —— 点下去要么没反应，要么在游戏代码里 NRE。
for (int __pass = 0; __pass < 2 && __go == null; __pass++) {{
  bool __active = (__pass == 0);
  foreach (var __g in UnityEngine.Object.FindObjectsOfType<UnityEngine.GameObject>(true)) {{
    if (__active && !__g.activeInHierarchy) continue;
    if (__g.name.Trim() == __want) {{ __go = __g; break; }}
  }}
  if (__go != null) break;
  foreach (var __g in UnityEngine.Object.FindObjectsOfType<UnityEngine.GameObject>(true)) {{
    if (__active && !__g.activeInHierarchy) continue;
    var __p = __g.name; var __t = __g.transform.parent;
    while (__t != null) {{ __p = __t.name + "/" + __p; __t = __t.parent; }}
    if (__p.Trim() == __want) {{ __go = __g; break; }}
  }}
  if (__go != null) break;
  // 部分路径（如 "Window/Button"）也算命中 —— 写全路径很啰嗦，实测模型与用例都爱写半截
  foreach (var __g in UnityEngine.Object.FindObjectsOfType<UnityEngine.GameObject>(true)) {{
    if (__active && !__g.activeInHierarchy) continue;
    var __p2 = __g.name; var __t2 = __g.transform.parent;
    while (__t2 != null) {{ __p2 = __t2.name + "/" + __p2; __t2 = __t2.parent; }}
    if (__p2.Trim().EndsWith("/" + __want)) {{ __go = __g; break; }}
  }}
  if (__go == null) {{
    // 最后按**可见文本**找（真中文游戏：对象名是英文/拼音，界面上写的是"返回游戏"）。
    // 用反射读 text 属性，避免依赖 TMPro 是否装了；找到文本后从自己往上找可点对象。
    foreach (var __t in UnityEngine.Object.FindObjectsOfType<UnityEngine.Transform>(true)) {{
      if (__active && !__t.gameObject.activeInHierarchy) continue;
      string __lab = "";
      foreach (var __c in __t.GetComponents<UnityEngine.Component>()) {{
        if (__c == null) continue;
        var __p3 = __c.GetType().GetProperty("text");
        if (__p3 == null || __p3.PropertyType != typeof(string) || !__p3.CanRead) continue;
        var __v = __p3.GetValue(__c, null) as string;
        if (!string.IsNullOrEmpty(__v)) __lab += __v.Trim();
      }}
      if (__lab != __want) continue;
      var __node = __t;
      for (int __hop = 0; __hop < 4 && __node != null; __hop++) {{
        if (__node.GetComponent<UnityEngine.UI.Button>() != null
            || UnityEngine.EventSystems.ExecuteEvents.GetEventHandler<UnityEngine.EventSystems.IPointerClickHandler>(__node.gameObject) != null) {{
          __go = __node.gameObject; break;
        }}
        __node = __node.parent;
      }}
      if (__go != null) break;
    }}
  }}
}}
"""
_PRESENT_PROBE = r"""
// probe-only: 只回"在不在"，不做别的
string __json;
if (__go == null) { __json = "{\"ok\":false,\"error\":\"object not found: " + __want + "\"}"; }
else {
  var __p = __go.name; var __t4 = __go.transform.parent;
  while (__t4 != null) { __p = __t4.name + "/" + __p; __t4 = __t4.parent; }
  __json = "{\"ok\":true,\"name\":\"" + __go.name.Replace("\"", "'")
        + "\",\"path\":\"" + __p.Replace("\"", "'")
        + "\",\"active\":" + (__go.activeInHierarchy ? "true" : "false") + "}";
}
return __json;
"""


def cs_present(target: str) -> str:
    """对象在不在（宽松匹配：名字两端空白不算差异，半截路径也算命中）。"""
    return _CS_FIND.format(target=_cs_str(target)) + _PRESENT_PROBE


def cs_click(target: str) -> str:
    """点一个 UGUI 控件：先 Button.onClick，再 ExecuteEvents（通用，不依赖游戏代码）。

    契约（实测 mcp-for-unity-server 的 execute_code）：片段是**方法体**，必须 return；
    默认 CodeDom 编译器，所以只用 C# 5 以内的语法（别用字符串插值 / `?.` / lambda）。
    """
    return _CS_FIND.format(target=_cs_str(target)) + r"""
string __json;
if (__go == null) { __json = "{\"ok\":false,\"error\":\"object not found: " + __target + "\"}"; }
else {
  var __btn = __go.GetComponent<UnityEngine.UI.Button>();
  if (__btn != null) {
    if (!__btn.interactable) { __json = "{\"ok\":false,\"error\":\"button not interactable: " + __target + "\"}"; }
    else { __btn.onClick.Invoke(); __json = "{\"ok\":true,\"via\":\"Button.onClick\",\"path\":\"" + __target + "\"}"; }
  } else {
    // 不是 Button 的控件（真游戏里很常见：自定义列表项、图标、卡牌）——
    // 发**完整指针序列** down → up → click，并带上对象中心的真实坐标。
    // 只发 pointerClick 的话，很多实现（如 UIWidgets 的 ListView）选不中：
    // 它在 pointerDown/Up 里做选中，click 只是顺带。
    var __es = UnityEngine.EventSystems.EventSystem.current;
    if (__es == null) { __json = "{\"ok\":false,\"error\":\"no EventSystem in scene\"}"; }
    else {
      var __ped = new UnityEngine.EventSystems.PointerEventData(__es);
      __ped.button = UnityEngine.EventSystems.PointerEventData.InputButton.Left;
      __ped.clickCount = 1;
      var __rt = __go.GetComponent<UnityEngine.RectTransform>();
      if (__rt != null) {
        var __corners = new UnityEngine.Vector3[4];
        __rt.GetWorldCorners(__corners);
        __ped.position = new UnityEngine.Vector2((__corners[0].x + __corners[2].x) / 2f,
                                                 (__corners[0].y + __corners[2].y) / 2f);
        __ped.pressPosition = __ped.position;
      }
      UnityEngine.EventSystems.ExecuteEvents.ExecuteHierarchy(__go, __ped,
          UnityEngine.EventSystems.ExecuteEvents.pointerDownHandler);
      UnityEngine.EventSystems.ExecuteEvents.ExecuteHierarchy(__go, __ped,
          UnityEngine.EventSystems.ExecuteEvents.pointerUpHandler);
      UnityEngine.EventSystems.ExecuteEvents.ExecuteHierarchy(__go, __ped,
          UnityEngine.EventSystems.ExecuteEvents.pointerClickHandler);
      __json = "{\"ok\":true,\"via\":\"pointer-sequence\",\"path\":\"" + __target + "\"}";
    }
  }
}
return __json;
"""


def cs_set_text(target: str, text: str) -> str:
    """写文本：用反射找组件上可写的 text 属性 —— 不依赖 TMPro 是否安装。"""
    return _CS_FIND.format(target=_cs_str(target)) + rf"""
var __text = {_cs_str(text)};
string __json;
if (__go == null) {{ __json = "{{\"ok\":false,\"error\":\"object not found: " + __target + "\"}}"; }}
else {{
  var __hit = 0;
  foreach (var __c in __go.GetComponents<UnityEngine.Component>()) {{
    if (__c == null) continue;
    var __p = __c.GetType().GetProperty("text", typeof(string));
    if (__p != null && __p.CanWrite) {{ __p.SetValue(__c, __text); __hit++; }}
  }}
  __json = "{{\"ok\":" + (__hit > 0 ? "true" : "false") + ",\"written\":" + __hit + ",\"path\":\"" + __target + "\"}}";
}}
return __json;
"""


def cs_text(target: str) -> str:
    """读对象**及其子孙**的文本（只回文本，比 describe 轻）。

    为什么需要它：uGUI 的 Button 自己不带文字，标签挂在子对象上（``.../PlayButton/Text``）。
    真游戏里最常见的断言就是"按钮上写着 NOWA GRA"，只读自己的组件永远断言不到。
    Text / TextMeshPro / InputField 都有 text 或 value 属性，这里按属性名收，不认具体类型。
    """
    return _CS_FIND.format(target=_cs_str(target)) + r"""
string __json;
if (__go == null) { __json = "{\"ok\":false,\"error\":\"object not found: " + __target + "\"}"; }
else {
  var __sb = new System.Text.StringBuilder();
  var __p = __go.name; var __t3 = __go.transform.parent;
  while (__t3 != null) { __p = __t3.name + "/" + __p; __t3 = __t3.parent; }
  __sb.Append("{\"ok\":true,\"path\":\"" + __p.Replace("\"", "'") + "\",\"parts\":[");
  var __first = true;
  foreach (var __c in __go.GetComponentsInChildren<UnityEngine.Component>(true)) {
    if (__c == null) continue;
    foreach (var __pr in __c.GetType().GetProperties()) {
      if (__pr.GetIndexParameters().Length > 0 || !__pr.CanRead) continue;
      if (__pr.PropertyType != typeof(string)) continue;
      var __n = __pr.Name;
      if (__n != "text" && __n != "value") continue;
      string __s = null;
      try { __s = (string)__pr.GetValue(__c); } catch (System.Exception) { continue; }
      if (string.IsNullOrEmpty(__s)) continue;
      if (!__first) __sb.Append(",");
      __first = false;
      __sb.Append("\"" + __s.Replace("\\", "/").Replace("\"", "'").Replace("\n", " ").Replace("\r", " ") + "\"");
    }
  }
  __sb.Append("]}");
  __json = __sb.ToString();
}
return __json;
"""


def cs_describe(target: str) -> str:
    """读对象：名字/路径/激活/组件清单 + 各组件的 text/value 属性。"""
    return _CS_FIND.format(target=_cs_str(target)) + r"""
string __json;
if (__go == null) { __json = "{\"ok\":false,\"error\":\"object not found: " + __target + "\"}"; }
else {
  var __sb = new System.Text.StringBuilder();
  var __path = __go.name; var __t2 = __go.transform.parent;
  while (__t2 != null) { __path = __t2.name + "/" + __path; __t2 = __t2.parent; }
  __sb.Append("{\"ok\":true,\"name\":\"" + __go.name + "\",\"path\":\"" + __path + "\"");
  __sb.Append(",\"active\":" + (__go.activeInHierarchy ? "true" : "false"));
  __sb.Append(",\"components\":[");
  var __first = true;
  foreach (var __c in __go.GetComponents<UnityEngine.Component>()) {
    if (__c == null) continue;
    if (!__first) __sb.Append(",");
    __first = false;
    __sb.Append("{\"type\":\"" + __c.GetType().Name + "\"");
    foreach (var __p in __c.GetType().GetProperties()) {
      if (__p.GetIndexParameters().Length > 0 || !__p.CanRead) continue;
      var __n = __p.Name;
      if (__n != "text" && __n != "value" && __n != "isOn" && __n != "interactable") continue;
      object __v = null;
      try { __v = __p.GetValue(__c); } catch (System.Exception) { continue; }
      if (__v == null) continue;
      __sb.Append(",\"" + __n + "\":\"" + __v.ToString().Replace("\"", "'").Replace("\n", " ") + "\"");
    }
    __sb.Append("}");
  }
  __sb.Append("]}");
  __json = __sb.ToString();
}
return __json;
"""


# --- 看全貌：层级树 + 按可见文本搜 ------------------------------------------
#
# 为什么要有这两个：真游戏里"猜对象名"是最贵的一步。实测一段探索流程里，模型连着
# 猜了 TalkUI / UI / UIRoot / Talk 四个名字（每次一轮 MCP 往返），最后自己手写 C#
# 遍历场景才看见结构 —— 中文游戏更是如此：对象名是英文/拼音，界面上写的是中文。
# 两个原语各解决一半：
#   - ``cs_tree``：一次把（子）树的**路径/可见性/组件/文本**倒出来，不用猜、不用翻页；
#   - ``cs_find_text``：按界面上那句话反查对象（"这句话写在哪、点哪个能点"）。
# 服务器自带 ``manage_scene get_hierarchy`` 只给对象名与组件名、按页翻，且没有文本，
# 对"中文界面找入口"帮助有限 —— 所以这两个走 C# 一次成型。

_CS_TREE = r"""
// tree-only: 一次把（子）树连文本倒出来；广度优先，截断时先保住上层全貌
int __maxDepth = __DEPTH__;
int __maxNodes = __MAXNODES__;
string __rootWant = "__ROOT__".Trim();
System.Func<string, string> __esc = delegate(string __s) {
  return __s.Replace("\\", "/").Replace("\"", "'").Replace("\r", " ")
             .Replace("\n", "\\n").Replace("\t", "\\t");
};
var __queue = new System.Collections.Generic.Queue<UnityEngine.Transform>();
var __depths = new System.Collections.Generic.Queue<int>();
if (__rootWant.Length == 0) {
  foreach (var __scene in UnityEngine.SceneManagement.SceneManager.GetAllScenes()) {
    if (!__scene.isLoaded) continue;
    foreach (var __r in __scene.GetRootGameObjects()) { __queue.Enqueue(__r.transform); __depths.Enqueue(0); }
  }
} else {
  // root 认名字、也认路径（含半截路径），与点击/查找链一致；两趟：先只看可见的
  UnityEngine.GameObject __rg = null;
  for (int __pass = 0; __pass < 2 && __rg == null; __pass++) {
    bool __onlyActive = (__pass == 0);
    foreach (var __g in UnityEngine.Object.FindObjectsOfType<UnityEngine.GameObject>(true)) {
      if (__onlyActive && !__g.activeInHierarchy) continue;
      if (__g.name.Trim() == __rootWant) { __rg = __g; break; }
    }
    if (__rg != null) break;
    foreach (var __g2 in UnityEngine.Object.FindObjectsOfType<UnityEngine.GameObject>(true)) {
      if (__onlyActive && !__g2.activeInHierarchy) continue;
      var __gp = __g2.name; var __gt = __g2.transform.parent;
      while (__gt != null) { __gp = __gt.name + "/" + __gp; __gt = __gt.parent; }
      __gp = __gp.Trim();
      if (__gp == __rootWant || __gp.EndsWith("/" + __rootWant)) { __rg = __g2; break; }
    }
  }
  if (__rg == null) return "{\"ok\":false,\"error\":\"object not found: " + __esc(__rootWant) + "\"}";
  __queue.Enqueue(__rg.transform); __depths.Enqueue(0);
}
var __sb = new System.Text.StringBuilder();
int __n = 0; bool __cut = false;
while (__queue.Count > 0) {
  var __t = __queue.Dequeue();
  int __d = __depths.Dequeue();   // 相对**起点**的层数：给了 root 就从 root 往下数
  if (__n >= __maxNodes) { __cut = true; break; }
  string __path = __t.name; var __p = __t.parent;
  while (__p != null) { __path = __p.name + "/" + __path; __p = __p.parent; }
  string __txt = "";
  foreach (var __c in __t.GetComponents<UnityEngine.Component>()) {
    if (__c == null) continue;
    var __pi = __c.GetType().GetProperty("text");
    if (__pi == null || __pi.PropertyType != typeof(string) || !__pi.CanRead) continue;
    var __v = __pi.GetValue(__c, null) as string;
    if (!string.IsNullOrEmpty(__v)) __txt += " " + __v.Replace("\n", " ").Trim();
    if (__txt.Length > 70) break;
  }
  var __comps = new System.Collections.Generic.List<string>();
  foreach (var __c2 in __t.GetComponents<UnityEngine.Component>()) {
    if (__c2 == null) continue;
    var __nm = __c2.GetType().Name;
    if (__nm == "Transform" || __nm == "RectTransform") continue;
    __comps.Add(__nm);
    if (__comps.Count >= 4) break;
  }
  __sb.Append(__esc(__path.Trim())).Append("\t")
      .Append(__t.gameObject.activeInHierarchy ? "1" : "0").Append("\t")
      .Append(__esc(string.Join(",", __comps.ToArray()))).Append("\t")
      .Append(__esc(__txt.Trim().Length > 70 ? __txt.Trim().Substring(0, 70) : __txt.Trim()))
      .Append("\n");
  __n++;
  if (__d >= __maxDepth) continue;
  for (int __i = 0; __i < __t.childCount; __i++) {
    __queue.Enqueue(__t.GetChild(__i)); __depths.Enqueue(__d + 1);
  }
}
return "{\"ok\":true,\"nodes\":" + __n + ",\"truncated\":" + (__cut ? "true" : "false")
     + ",\"lines\":\"" + __esc(__sb.ToString()) + "\"}";
"""


def cs_tree(root: str = "", depth: int = 3, max_nodes: int = 80) -> str:
    """看（子）树的路径/可见性/组件/文本 —— 探索界面的第一步。"""
    return (_CS_TREE.replace("__DEPTH__", str(max(0, int(depth))))
            .replace("__MAXNODES__", str(max(1, int(max_nodes))))
            .replace("__ROOT__", str(root or "").replace('"', "'")))


_CS_FIND_TEXT = r"""
// findtext-only: 按**可见文本**找对象（返回写这句话的对象、以及往上最近的可点祖先）
string __needle = "__NEEDLE__";
string __rootWant = "__ROOT__".Trim();
int __limit = __LIMIT__;
System.Func<string, string> __esc2 = delegate(string __s) {
  return __s.Replace("\\", "/").Replace("\"", "'").Replace("\r", " ")
             .Replace("\n", "\\n").Replace("\t", "\\t");
};
var __hits = new System.Collections.Generic.List<string>();
int __seen = 0;
foreach (var __t in UnityEngine.Object.FindObjectsOfType<UnityEngine.Transform>(true)) {
  if (__hits.Count >= __limit) break;
  if (__rootWant.Length > 0) {
    var __n0 = __t; bool __in = false; int __hop = 0;
    while (__n0 != null && __hop < 64) {
      if (__n0.name.Trim() == __rootWant) { __in = true; break; }
      __n0 = __n0.parent; __hop++;
    }
    if (!__in) continue;
  }
  string __txt = "";
  foreach (var __c in __t.GetComponents<UnityEngine.Component>()) {
    if (__c == null) continue;
    var __pi = __c.GetType().GetProperty("text");
    if (__pi == null || __pi.PropertyType != typeof(string) || !__pi.CanRead) continue;
    var __v = __pi.GetValue(__c, null) as string;
    if (!string.IsNullOrEmpty(__v)) __txt += " " + __v.Replace("\n", " ").Trim();
  }
  __seen++;
  if (__txt.Length == 0 || __txt.IndexOf(__needle, System.StringComparison.OrdinalIgnoreCase) < 0) continue;
  string __path = __t.name; var __p = __t.parent;
  while (__p != null) { __path = __p.name + "/" + __path; __p = __p.parent; }
  string __clickPath = "";
  var __node2 = __t;
  for (int __hop2 = 0; __hop2 < 4 && __node2 != null; __hop2++) {
    if (__node2.GetComponent<UnityEngine.UI.Button>() != null
        || UnityEngine.EventSystems.ExecuteEvents.GetEventHandler<UnityEngine.EventSystems.IPointerClickHandler>(__node2.gameObject) != null) {
      var __cp = __node2.name; var __pp = __node2.parent;
      while (__pp != null) { __cp = __pp.name + "/" + __cp; __pp = __pp.parent; }
      __clickPath = __cp.Trim(); break;
    }
    __node2 = __node2.parent;
  }
  __hits.Add(__esc2(__path.Trim()) + "\t" + (__t.gameObject.activeInHierarchy ? "1" : "0") + "\t"
             + __esc2(__clickPath) + "\t" + __esc2(__txt.Trim()));
}
return "{\"ok\":true,\"scanned\":" + __seen + ",\"hits\":" + __hits.Count + ",\"lines\":\""
     + __esc2(string.Join("\n", __hits.ToArray())) + "\"}";
"""


def cs_find_text(needle: str, root: str = "", limit: int = 20) -> str:
    """按界面上显示的文字反查对象（含"往上哪个祖先能点"）。"""
    return (_CS_FIND_TEXT.replace("__NEEDLE__", str(needle).replace('"', "'"))
            .replace("__ROOT__", str(root or "").replace('"', "'"))
            .replace("__LIMIT__", str(max(1, int(limit)))))


def _lines_payload(out: dict, *, limit: int = 400) -> dict:
    """把 ``{"lines": "a\\tb\\n..."}`` 解成行数组（两个新原语共用一套解析）。"""
    result = out.get("result")
    if not isinstance(result, dict) or result.get("ok") is not True:
        return {"success": False,
                "error": (result or {}).get("error") or out.get("error") or "调用失败"}
    lines = (result.get("lines") or "").split("\n")
    rows = [line.split("\t") for line in lines if line.strip()]
    return {"success": True, "rows": rows[:limit], "total": len(rows),
            "nodes": result.get("nodes"), "hits": result.get("hits"),
            "scanned": result.get("scanned"), "truncated": bool(result.get("truncated"))}


def _render_table(rows: list[list[str]], header: str) -> str:
    """给模型看的紧凑文本：每行 ``路径  可见  组件/可点  文本``。"""
    body = []
    for row in rows:
        cells = [c for c in row]
        while len(cells) < 4:
            cells.append("")
        path, active, extra, text = cells[0], cells[1], cells[2], cells[3]
        mark = "显示" if active == "1" else "隐藏"
        tail = f'"{text}"' if text else ""
        body.append(f"{path}  [{mark}]  {extra}  {tail}".rstrip())
    return header + "\n" + "\n".join(body) if body else header


# --- 录像：编辑器侧逐帧落盘 + 平台侧 ffmpeg 合成 ------------------------------
#
# 为什么这么绕：Playwright 自带 video 录制，Unity 没有等价的公开 API（Recorder
# 包要改工程、要渲染管线配合）。但"编辑器里能看到 Game View"这件事给了另一条路：
# 用 EditorApplication.update 起一个每拍采一帧的钩子，帧落成 jpg，跑完由平台用
# ffmpeg 合成 mp4。
#
# 三个刻意的选择：
# - **回调而不是协程**：host GameObject 会在换场景时被销毁，协程跟着断；而
#   EditorApplication.update 挂在编辑器上，进出 Play Mode、换场景都不受影响。
# - **状态放 SessionState**：MCP 每次 execute_code 都是**新编译的一份代码**，
#   start 里定义的委托没法被后面的 stop 引用；开关与计数必须落在编辑器会话级的
#   共享存储里，回调自己看见 false 就退订。
# - **帧写临时缓存目录**：不往用户的 Unity 工程里塞文件（Library/Temp 之外的东西
#   会被版本管理看见）。目录路径由 C# 回传，平台直接读盘（编辑器与本机同机时）。

_REC_DIR_KEY = "unity_auto_rec_dir"
_REC_ON_KEY = "unity_auto_rec_on"
_REC_N_KEY = "unity_auto_rec_n"
_REC_GAP_KEY = "unity_auto_rec_gap"
_REC_MAX_KEY = "unity_auto_rec_max"


def cs_record_start(subdir: str, fps: float, max_frames: int) -> str:
    gap = round(1.0 / max(0.5, min(60.0, fps)), 4)
    return r"""
var __dir = System.IO.Path.Combine(UnityEngine.Application.temporaryCachePath,
                                   "unity-auto-rec", "{subdir}");
System.IO.Directory.CreateDirectory(__dir);
UnityEditor.SessionState.SetString("{dir_key}", __dir);
UnityEditor.SessionState.SetBool("{on_key}", true);
UnityEditor.SessionState.SetInt("{n_key}", 0);
UnityEditor.SessionState.SetFloat("{gap_key}", {gap}f);
UnityEditor.SessionState.SetInt("{max_key}", {max_frames});
double __last = 0.0;
// 必须声明成 CallbackFunction 而不是 System.Action：EditorApplication.update 是
// **命名委托类型**，C# 不允许用 Action 去 += / -=（实测报
// "Operator `-=' cannot be applied to operands of type CallbackFunction and System.Action"）。
UnityEditor.EditorApplication.CallbackFunction __cb = null;
__cb = delegate {{
  if (!UnityEditor.SessionState.GetBool("{on_key}", false)) {{
    UnityEditor.EditorApplication.update -= __cb;
    return;
  }}
  double __now = (double)UnityEngine.Time.realtimeSinceStartup;
  if (__now - __last < (double)UnityEditor.SessionState.GetFloat("{gap_key}", {gap}f)) return;
  __last = __now;
  int __n = UnityEditor.SessionState.GetInt("{n_key}", 0);
  if (__n >= UnityEditor.SessionState.GetInt("{max_key}", {max_frames})) {{
    UnityEditor.SessionState.SetBool("{on_key}", false);
    UnityEditor.EditorApplication.update -= __cb;
    return;
  }}
  try {{
    var __tex = UnityEngine.ScreenCapture.CaptureScreenshotAsTexture();
    byte[] __jpg = UnityEngine.ImageConversion.EncodeToJPG(__tex, 75);
    UnityEngine.Object.DestroyImmediate(__tex);
    System.IO.File.WriteAllBytes(System.IO.Path.Combine(
        UnityEditor.SessionState.GetString("{dir_key}", __dir),
        string.Format("f_{{0:D5}}.jpg", __n)), __jpg);
    UnityEditor.SessionState.SetInt("{n_key}", __n + 1);
  }} catch (System.Exception) {{ }}
}};
UnityEditor.EditorApplication.update += __cb;
return "{{\"ok\":true,\"dir\":\"" + __dir.Replace("\\", "/") + "\",\"gap\":" + {gap} + "}}";
""".format(subdir=subdir.replace('"', ""), dir_key=_REC_DIR_KEY, on_key=_REC_ON_KEY,
           n_key=_REC_N_KEY, gap_key=_REC_GAP_KEY, max_key=_REC_MAX_KEY,
           gap=gap, max_frames=int(max_frames))


def cs_record_stop() -> str:
    return r"""
UnityEditor.SessionState.SetBool("{on_key}", false);
string __dir = UnityEditor.SessionState.GetString("{dir_key}", "");
int __n = UnityEditor.SessionState.GetInt("{n_key}", 0);
System.Threading.Thread.Sleep(150);
return "{{\"ok\":true,\"dir\":\"" + __dir.Replace("\\", "/") + "\",\"frames\":" + __n + "}}";
""".format(on_key=_REC_ON_KEY, dir_key=_REC_DIR_KEY, n_key=_REC_N_KEY)


# --- 软复位：Play Mode 里重载当前场景 ---------------------------------------
# 硬复位（退 Play → 重进 Play）最彻底但要等一整套冷启动；只想把**地图/界面**拉回
# 起点时，重载场景就够了。两处坑：场景不在 Build Settings 里（buildIndex<0）时只能
# 按名字加载；`Application.isPlaying` 为假时调用没有任何意义 —— 都要明确回报，
# 不能"静默什么都没做"让上层以为复位成功了。
_CS_RELOAD_SCENE = r"""
// reload-scene: 重载当前场景（soft 复位）
if (!UnityEngine.Application.isPlaying) {
  return "{\"ok\":false,\"error\":\"不在 Play Mode（软复位只在游戏跑起来时有意义）\"}";
}
var __sc = UnityEngine.SceneManagement.SceneManager.GetActiveScene();
if (!__sc.isLoaded) {
  return "{\"ok\":false,\"error\":\"当前没有已加载的场景\"}";
}
if (__sc.buildIndex >= 0) {
  UnityEngine.SceneManagement.SceneManager.LoadScene(
      __sc.buildIndex, UnityEngine.SceneManagement.LoadSceneMode.Single);
} else {
  UnityEngine.SceneManagement.SceneManager.LoadScene(
      __sc.name, UnityEngine.SceneManagement.LoadSceneMode.Single);
}
return "{\"ok\":true,\"scene\":\"" + __sc.name.Replace("\\", "/").Replace("\"", "'") + "\"}";
"""


def _frames_in(folder: Path) -> list[Path]:
    try:
        return sorted(p for p in folder.iterdir()
                      if p.suffix.lower() == ".jpg" and p.name.startswith("f_"))
    except OSError:
        return []


#: 平台自己造成的 Console 噪声 —— 报错的是**我们的截图/录像**，不是被测对象。
#: Unity 进 Play 的头几帧还没有"上一帧"可截，`CaptureScreenshotAsTexture` 会打这条
#: Error（日志由 Unity 内部打，调用方 catch 不到）。留着它的后果很具体：用例里
#: "无新增报错"这类断言会把平台噪声当成游戏的新报错（实测：jynew 冒烟用例偶发红）。
_PLATFORM_NOISE = ("CaptureScreenshotAsTexture() failed",)


def _drop_platform_noise(rows: list) -> list:
    """滤掉平台自己产生的 Console 行（只滤这几条精确指纹，不做模糊匹配）。"""
    return [r for r in rows
            if not any(marker in str(r) for marker in _PLATFORM_NOISE)]


def stitch_video(frames: list[Path], out_path: Path, fps: float) -> dict:
    """把帧序列合成 mp4（H.264/yuv420p：浏览器 ``<video>`` 能直接放）。

    失败**不抛异常** —— 录像只是存证，合成不出来不该把一条已经跑出结论的用例
    改判成失败。返回 ``{"ok": False, "error": …}``，由调用方决定怎么说。
    """
    exe = shutil.which("ffmpeg")
    if not exe:
        return {"ok": False, "error": "本机没有 ffmpeg，装一个（brew install ffmpeg）才能合成录像"}
    if not frames:
        return {"ok": False, "error": "没有采到任何帧"}
    # 帧名是 f_00000.jpg 这种定宽序号，用 %05d 让 ffmpeg 自己按序读。
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [exe, "-y", "-loglevel", "error", "-framerate", f"{max(1.0, fps):.3f}",
           "-start_number", "0", "-i", str(frames[0].parent / "f_%05d.jpg"),
           # 宽高各砍到偶数：Game View 可以是任意尺寸（实测 1737x1065），而
           # h264 的 yuv420p 要求宽高都是偶数 —— 不砍就整段合不出来，报错还很难懂
           # （`Could not open encoder before EOF`，退出码 187）。砍掉半列像素
           # 肉眼看不出，录像没了才是真损失。
           "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out_path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=300.0)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": f"ffmpeg 执行失败：{exc}"}
    if proc.returncode != 0 or not out_path.is_file():
        tail = (proc.stderr or b"").decode("utf-8", errors="replace")[-500:]
        # 别留一个 0 字节的 mp4 冒充产物：产物列表里出现 run.mp4 就会被人点开，
        # 打开是坏文件比"这次没有录像"更糟。
        try:
            if out_path.is_file() and out_path.stat().st_size == 0:
                out_path.unlink()
        except OSError:
            pass
        return {"ok": False, "error": f"ffmpeg 退出码 {proc.returncode}：{tail}"}
    return {"ok": True, "path": str(out_path), "size": out_path.stat().st_size}


# ===========================================================================
# 平台侧操作层（async）
# ===========================================================================

#: 环境类失败的特征（会话不在 / 连不上 / 超时）——与"对象不存在"要分开报
_ENV_FAILURE_MARKERS = ("session", "no_unity_session", "无法连接", "超时", "not available",
                        "timeout", "connection")


def _env_or_not_found(exc: Exception) -> str:
    """把失败分成"环境问题"与"真没找到"，让上层能给出对的结论。"""
    text = str(exc)
    if any(marker in text.lower() for marker in _ENV_FAILURE_MARKERS):
        return f"环境问题（不是用例失败）：{text}"
    return text


def _hint_for_error(err: str) -> str:
    if "无法连接" in err or "超时" in err:
        return ("Unity MCP 桥没连上：在启动器启动 unity-mcp（:5016，需要 uv）；"
                "Unity 工程里装 MCP for Unity 包并指向本机 5016")
    return ""


async def status() -> dict:
    """桥 + 服务器 + 编辑器状态。任何失败都返回 available=False，不抛。"""
    def _do() -> dict:
        client = _get_client()
        rpc_client = _rpc(lambda c: c.tools())
        instances = _instances_sync(client)
        editor = _editor_state_sync(client)
        return {
            "available": True,
            "transport": (settings.unity_mcp_transport or "http"),
            "endpoint": settings.unity_mcp_url if (settings.unity_mcp_transport or "http") != "stdio"
                        else settings.unity_mcp_command,
            "server": {"name": client.server_info.get("name", ""),
                       "version": client.server_info.get("version", ""),
                       "protocol": client.protocol},
            "flavor": client.flavor,
            "tool_count": len(rpc_client),
            "editor": editor,
            "instances": instances,
            "is_playing": (editor or {}).get("isPlaying"),
            # 连上没有以实例清单为准（编辑器状态在编辑器忙/重编译时可能读不到）
            "unity_connected": bool(instances) or editor is not None,
        }

    if (reason := _bridge_guard.blocked()) is not None:
        return {"available": False, "error": reason, "hint": ""}
    try:
        return await asyncio.to_thread(_do)
    except UnityBridgeError as exc:
        return {"available": False, "error": str(exc), "hint": _hint_for_error(str(exc))}
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "error": f"{type(exc).__name__}: {exc}", "hint": ""}


_DEAD_SESSION_HINTS = ("session not available", "no unity session", "会话已过期",
                       "进程已退出", "session not found")


def _is_dead_session(reason: str) -> bool:
    """这个失败是不是「当前这条会话看不到 Unity」，而不是「Unity 真没连」。

    两者文案一模一样，没法百分百区分；但代价不对等：多试一次的成本是一次握手，
    漏判的成本是整个平台一直显示"未连接"（连开两个游戏工程时实测到了）。
    """
    low = (reason or "").lower()
    return any(hint in low for hint in _DEAD_SESSION_HINTS)


def _resource_body(client: McpClient, uri: str, timeout: float) -> dict:
    res = client.read_resource(uri, timeout=timeout)
    payload: dict | None = None
    for block in (res.get("contents") or []):
        if isinstance(block, dict) and block.get("text"):
            try:
                payload = json.loads(block["text"])
            except json.JSONDecodeError:
                payload = {"success": True, "text": block["text"]}
            break
    if payload is None:
        raise UnityBridgeError(f"资源 {uri} 没有内容")
    return payload


def _read_resource_sync(client: McpClient, uri: str, timeout: float = 20.0) -> dict:
    """读一个 MCP 资源并解出正文 JSON。

    实测要点：资源"读不到"不一定报错 —— mcp-for-unity-server 在 Unity 没连上时返回
    200 + 正文 ``{"success": false, "error": "Unity session not available"}``，
    所以必须看正文字段，不能只看有没有抛异常。

    实测坑（连着换第二个游戏工程时撞到的）：MCP 会话会被绑到它第一次看到的那个 Unity
    实例，那个编辑器退出后，**同一条会话**读实例清单永远回 "Unity session not available"，
    新会话却一切正常 —— 表现是"桥和 Unity 都好着，平台一直说未连接"。所以会话级失败先
    重建会话再读一次，别把死会话的结论当成"Unity 没连"。
    """
    for attempt in (1, 2):
        payload = _resource_body(client, uri, timeout)
        if payload.get("success") is not False:
            return payload
        reason = payload.get("error") or f"资源 {uri} 读取失败"
        if attempt == 1 and _is_dead_session(reason):
            client.reset()
            client.ensure_ready()
            continue
        raise UnityBridgeError(reason)
    raise UnityBridgeError(f"资源 {uri} 读取失败")


def _state_from_payload(payload: dict) -> dict | None:
    """从状态资源/工具返回里挑出播放状态（层级与命名各实现不一，递归找）。

    实测 shape（schema ``unity-mcp/editor_state@2``）：
    ``data.editor.play_mode.{is_playing,is_paused}`` —— 蛇形命名且嵌在 editor 下；
    别的实现可能是 ``data.isPlaying``。两种都认，否则会得出"Unity 没连上"的错误结论
    （实测踩过：资源明明返回了状态，却因为找不到 isPlaying 被判成未连接）。
    """
    nodes: list[dict] = []

    def _collect(node: object) -> None:
        if isinstance(node, dict):
            nodes.append(node)
            for value in node.values():
                if isinstance(value, (dict, list)):
                    _collect(value)
        elif isinstance(node, list):
            for item in node:
                _collect(item)

    _collect(payload)
    for node in nodes:
        play = node.get("play_mode")
        if isinstance(play, dict):
            playing = play.get("is_playing", play.get("isPlaying"))
            if playing is not None:
                return {"isPlaying": bool(playing),
                        "isPaused": bool(play.get("is_paused", play.get("isPaused")) or False)}
        if "isPlaying" in node or "is_playing" in node:
            return {"isPlaying": bool(node.get("isPlaying", node.get("is_playing"))),
                    "isPaused": bool(node.get("isPaused", node.get("is_paused")) or False)}
    return None


def _instances_sync(client: McpClient) -> list[dict]:
    """连到这个桥上的 Unity 实例（实测资源：instance_count + instances[]）。

    比"读编辑器状态"更直接地回答"Unity 连上没有"，也是多实例时选目标 instance 的依据。
    """
    client.ensure_ready()  # 冷客户端上 flavor 还是 "generic"，资源模板取不到会静默返回空
    uri = (_RESOURCE_TEMPLATES.get(client.flavor) or {}).get("instances")
    if not uri:
        return []

    def _read() -> list[dict]:
        payload = _read_resource_sync(client, uri, timeout=15.0)
        data: object = payload.get("instances")
        if data is None and isinstance(payload.get("data"), (dict, list)):
            inner = payload["data"]
            data = inner.get("instances") if isinstance(inner, dict) else inner
        return [i for i in data if isinstance(i, dict)] if isinstance(data, list) else []

    try:
        found = _read()
        if found:
            return found
        # 空清单也可能是"这条会话绑在已经退出的那个实例上"，而它**不报错**（成功 + 空数组）。
        # 换个会话再读一次：多一次握手的代价，换"换工程后第一次探活就说没连"这个假故障。
        client.reset()
        client.ensure_ready()
        return _read()
    except UnityBridgeError:
        return []


def _editor_state_sync(client: McpClient) -> dict | None:
    """编辑器状态：先资源（实测该服务器只有资源给状态），再退回各家自己的工具。"""
    client.ensure_ready()
    uri = (_RESOURCE_TEMPLATES.get(client.flavor) or {}).get("editor_state")
    if uri:
        try:
            state = _state_from_payload(_read_resource_sync(client, uri, timeout=15.0))
            if state is not None:
                return state
        except UnityBridgeError:
            pass
    for flavor, name in sorted(_OP_TOOLS["editor_state"],
                               key=lambda c: 0 if c[0] == client.flavor else 1):
        tool = client.find_tool((name,))
        if tool is None:
            continue
        args = _adapt_args({"action": "get_state"}, tool.get("inputSchema"))
        try:
            out = unwrap(client.call(name, args, timeout=15.0), save_image=False)
        except UnityBridgeError:
            continue
        if not out.get("success"):
            continue
        state = _state_from_payload(out)
        if state is not None:
            return state
    return None


async def editor_action(action: str) -> dict:
    """play / pause / stop / state / refresh。"""
    def _do() -> dict:
        client = _get_client()
        if action == "state":
            return {"success": True, "editor": _editor_state_sync(client)}
        if action == "refresh":
            name, schema, _flavor = _resolve("refresh")
            return unwrap(_rpc(lambda c: c.call(name, _adapt_args({}, schema))))
        if action not in ("play", "pause", "stop"):
            return {"success": False, "error": f"未知动作 {action}（play/pause/stop/state/refresh）"}
        name, schema, flavor = _resolve("editor_action")
        args = {"action": action}
        if flavor == "ivan":
            args = {"state": _IVAN_STATE.get(action, action)}
        out = unwrap(_rpc(lambda c: c.call(name, _adapt_args(args, schema))))
        if out.get("success") and "error" in (out.get("text") or "").lower():
            # 有些实现把失败写在文本里而不是 isError
            return out
        return out

    return await _guard_call(_do)


async def _guard_call(fn):
    if (reason := _bridge_guard.blocked()) is not None:
        return {"success": False, "error": reason}
    try:
        return await asyncio.to_thread(fn)
    except UnityBridgeError as exc:
        return {"success": False, "error": str(exc), "hint": _hint_for_error(str(exc))}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}


def _id_of(node: object) -> int | None:
    if not isinstance(node, dict):
        return None
    for key in ("instance_id", "instanceID", "instanceId", "id"):
        value = node.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def _extract_objects(payload: object) -> list[dict]:
    """从查询结果里抠出 [{id, name}]（实测该工具只回 instance id，详情在资源里）。"""
    found: list[dict] = []
    seen: set[int] = set()

    def _walk(node: object) -> None:
        if isinstance(node, dict):
            gid = _id_of(node)
            if gid is not None and gid not in seen:
                seen.add(gid)
                name = node.get("name") or node.get("gameobject") or node.get("path")
                found.append({"id": gid, "name": name} if name else {"id": gid})
            for key, value in node.items():
                # 实测：find_gameobjects 回 {"data": {"instanceIDs": [123, 456]}}（裸整数数组）
                if key in ("instanceIDs", "instance_ids") and isinstance(value, list):
                    for item in value:
                        if isinstance(item, int) and not isinstance(item, bool) and item not in seen:
                            seen.add(item)
                            found.append({"id": item})
                    continue
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(payload)
    return found


def _find_objects_sync(client: McpClient, call, *, name: str = "", path: str = "",
                       component: str = "", tag: str = "", limit: int = 50,
                       find_inactive: bool = True, enrich: int | None = None,
                       _name_fallback: bool = True) -> dict:
    """查对象：把平台的四种查法折算成 search_term + search_method，再补详情。

    实测该服务器 `find_gameobjects` 只接受 search_term + search_method
    （by_name/by_tag/by_layer/by_component/by_path/by_id）并**只返回 instance id**；
    对象数据要按 id 读资源。所以这里拿回 id 后顺手读对象的详情 —— 一次查询一次
    资源请求，返回集由调用方的 ``limit`` 决定。

    实测坑（真游戏上撞到的）：以前默认只补前 10 个，真游戏一次查回 40 个 Text 时，
    后 30 行是 ``name=None`` 的空壳 —— 看上去像坏了，其实是没取详情。现在默认全补，
    并把 ``object_count`` / ``detailed`` 一起给出去，截断与否一眼可见。
    ``enrich=0`` 仍然表示"只要 id"（``_instance_id`` 走这条）。
    """
    client.ensure_ready()
    tool, schema, _flavor = _resolve("find_objects")
    method = next((_SEARCH_METHOD[key] for key, value in
                   (("name", name), ("path", path), ("component", component), ("tag", tag))
                   if value), "")
    term = name or path or component or tag
    # 不传 include_inactive：实测（jynew）传 true 会让**整个查询返回空**，而服务器
    # 默认行为本来就包含未激活对象（关掉的 BagUIPanel(Clone) 用默认能查到）。
    # 参数保留是为了 API 稳定，实际以服务器默认为准。
    args = _adapt_args({"name": term, "search_method": method or None, "limit": limit},
                       schema)
    out = unwrap(call(lambda c: c.call(tool, args)))
    out["tool"] = tool
    if not out.get("success"):
        return out
    objects = _extract_objects(out.get("data") if out.get("data") is not None else out.get("text"))
    if not objects and _name_fallback and name:
        # 实测坑（大型中文工程 jynew）：服务器的 by_name 对**运行时实例化的对象**
        # （界面上全是 MainUIPanel(Clone) 这种克隆）一个都查不到，by_path 却查得到。
        # 名字查空就按路径再查一次，否则"按名字查界面对象"在真游戏里会静默返回空。
        return _find_objects_sync(client, call, name="", path=name, component=component,
                                  tag=tag, limit=limit, find_inactive=find_inactive,
                                  enrich=enrich, _name_fallback=False)
    out["objects"] = objects
    out["object_count"] = len(objects)
    summary = [o for o in objects if o.get("name")]
    detail_cap = len(objects) if enrich is None else max(0, enrich)
    detailed = 0
    if objects and not summary:      # 只有 id：补详情
        template = (_RESOURCE_TEMPLATES.get(client.flavor) or {}).get("gameobject")
        if template:
            for item in objects[:detail_cap]:
                try:
                    detail = _read_resource_sync(client, template.format(id=item["id"]))
                    data = detail.get("data") if isinstance(detail.get("data"), dict) else detail
                    if isinstance(data, dict):
                        item.update({k: v for k, v in data.items()
                                     if k in ("name", "path", "active", "activeInHierarchy",
                                              "tag", "layer", "componentTypes", "components")})
                    detailed += 1
                except UnityBridgeError:
                    continue
    out["detailed"] = detailed if not summary else len(objects)
    return out


async def find_objects(*, name: str = "", path: str = "", component: str = "",
                       tag: str = "", limit: int = 50, find_inactive: bool = True) -> dict:
    """查场景里的对象（通用对象模型的第一步）。"""
    return await _guard_call(lambda: _find_objects_sync(
        _get_client(), _rpc, name=name, path=path, component=component, tag=tag,
        limit=limit, find_inactive=find_inactive))


def _instance_id(client: McpClient, call, target: str) -> int | None:
    """把"名字/路径"折算成 instance id（纯数字直接用；名字查不到再按路径查）。"""
    if target.strip().isdigit():
        return int(target.strip())
    for kwargs in ({"name": target}, {"path": target}):
        try:
            out = _find_objects_sync(client, call, enrich=0, **kwargs)
        except UnityBridgeError:
            return None
        objects = out.get("objects") or []
        if objects:
            return objects[0]["id"]
    return None


def _object_info_sync(client: McpClient, call, target: str, component: str = "") -> dict:
    """读对象详情：优先资源（实测是唯一正路），再试服务器的检查工具，最后 C# 反射。"""
    client.ensure_ready()
    templates = _RESOURCE_TEMPLATES.get(client.flavor) or {}
    if templates.get("components"):
        gid = _instance_id(client, call, target)
        if gid is not None:
            for key in ("components", "gameobject"):
                try:
                    payload = _read_resource_sync(client, templates[key].format(id=gid))
                    payload["source"] = f"resource:{key}"
                    payload["instance_id"] = gid
                    return {"success": True, "data": payload.get("data") or payload,
                            "text": json.dumps(payload, ensure_ascii=False),
                            "tool": templates[key].format(id=gid), "instance_id": gid}
                except UnityBridgeError:
                    continue
    try:
        tool, schema, _flavor = _resolve("object_info")
        args = _adapt_args({"target": target, "name": target, "component": component}, schema)
        out = unwrap(call(lambda c: c.call(tool, args)))
        out["tool"] = tool
        if out.get("success"):
            return out
    except UnityBridgeError:
        pass
    return _exec_csharp_sync(cs_describe(target), call=call)


async def object_info(target: str, component: str = "") -> dict:
    """读一个对象的组件/字段；服务器没有检查工具时退回通用 C# 反射。"""
    return await _guard_call(lambda: _object_info_sync(_get_client(), _rpc, target, component))


def _exec_csharp_sync(code: str, timeout: float = 60.0, *, call=None,
                      client: McpClient | None = None) -> dict:
    client = client or _get_client()
    tool, schema, _flavor = _resolve("exec_csharp", client, call or _rpc)
    args = _adapt_args({"action": "execute", "code": code}, schema)
    out = unwrap((call or _rpc)(lambda c: c.call(tool, args, timeout=timeout)))
    out["tool"] = tool
    if not out.get("success"):
        return out
    # 实测契约：片段是方法体，`return` 的值经 data.result 回来（对象会被序列化成 JSON）。
    # Debug.Log("UNITY_BRIDGE:...") 仍然认，给"用日志回传"的用户代码留路。
    data = out.get("data")
    result = None
    if isinstance(data, dict):
        # 有的实现会把工具自己的返回再套一层（外层是平台统一结构、内层才是工具结果）
        for node in (data, data.get("data")):
            if isinstance(node, dict) and "result" in node:
                result = node["result"]
                break
    elif data is not None:
        result = data
    if isinstance(result, str):
        text = result.strip()
        if text.startswith(("{", "[")):
            try:
                result = json.loads(text)
            except json.JSONDecodeError:
                pass
    if result is None:
        result = _parse_marker(out.get("text") or "")
    if result is None and isinstance(data, dict):
        result = data          # 没有 result 字段：把工具的返回原样给出去
    if isinstance(result, dict):
        out["result"] = result
        if result.get("ok") is False:
            out["success"] = False
            out["error"] = result.get("error") or "C# 片段报告失败"
    elif result is not None:
        out["result"] = result
    return out


async def exec_csharp(code: str, timeout: float = 60.0) -> dict:
    """在编辑器里执行任意 C# 语句（通用逃逸口）。"""
    return await _guard_call(lambda: _exec_csharp_sync(code, timeout))


async def hierarchy(root: str = "", depth: int = 3, max_nodes: int = 80) -> dict:
    """看（子）树的结构：路径 / 可见性 / 组件 / 文本，一次调用看全貌。

    ``root`` 给名字或路径就只看那棵子树（探索某个面板时用），不给就看整个场景。
    广度优先：节点数被上限截断时，先保住上层结构（深度优先容易一头扎进某个分支，
    截断后反而看不见别的区域）。
    """
    out = await _guard_call(lambda: _exec_csharp_sync(cs_tree(root, depth, max_nodes)))
    parsed = _lines_payload(out)
    if not parsed.get("success"):
        return parsed
    rows = parsed["rows"]
    head = (f"# 场景层级（{parsed['nodes']} 个节点"
            + ("，已截断" if parsed.get("truncated") else "") + "）"
            + "\n# 列：路径 | 可见性 | 组件 | 文本")
    return {"success": True, "nodes": parsed["nodes"], "truncated": parsed["truncated"],
            "count": parsed["total"], "rows": rows,
            "text": _render_table(rows, head)}


async def find_by_text(text: str, root: str = "", limit: int = 20) -> dict:
    """按**界面上显示的文字**反查对象（中文游戏里对象名是拼音/英文，文字才是线索）。

    返回每处命中：写这句话的对象、它现在是否可见、以及**往上最近的可点祖先**
    （uGUI 的按钮标签常挂在子节点上，返回祖先路径省得再猜）。
    """
    out = await _guard_call(lambda: _exec_csharp_sync(cs_find_text(text, root, limit)))
    parsed = _lines_payload(out)
    if not parsed.get("success"):
        return parsed
    rows = parsed["rows"]
    head = (f"# 文本包含 {text!r} 的对象：{parsed['hits']} 处"
            f"（扫了 {parsed['scanned']} 个对象）"
            + "\n# 列：对象路径 | 可见性 | 可点祖先（空=没有点击处理器） | 文本")
    return {"success": True, "hits": parsed["hits"], "scanned": parsed["scanned"],
            "count": parsed["total"], "rows": rows,
            "text": _render_table(rows, head)}


async def subtree_text(target: str) -> dict:
    """读对象**及其全部子孙**的文本（问"这个面板/列表现在显示什么"）。"""
    out = await _guard_call(lambda: _exec_csharp_sync(cs_text(target)))
    result = out.get("result")
    if not isinstance(result, dict) or result.get("ok") is not True:
        return {"success": False,
                "error": (result or {}).get("error") or out.get("error") or "读取失败"}
    parts = [str(p).strip() for p in (result.get("parts") or []) if str(p).strip()]
    return {"success": True, "path": result.get("path"), "parts": parts,
            "text": " ".join(parts), "count": len(parts)}


async def click(target: str) -> dict:
    """点一个 UGUI 控件：Button.onClick → ExecuteEvents（不依赖游戏侧代码）。"""
    out = await _guard_call(lambda: _exec_csharp_sync(cs_click(target)))
    out["action"] = "click"
    out["target"] = target
    return out


async def set_text(target: str, text: str) -> dict:
    """给控件写文本（反射找可写 text 属性，TMPro/UI 都行）。"""
    out = await _guard_call(lambda: _exec_csharp_sync(cs_set_text(target, text)))
    out["action"] = "set_text"
    out["target"] = target
    return out


async def wait_for(target: str, timeout_s: float = 10.0, state: str = "present") -> dict:
    """等对象出现/消失（轮询统一走服务器自己的查询工具）。"""
    deadline = time.monotonic() + max(1.0, timeout_s)
    last: dict = {}
    while True:
        last = await find_objects(name=target)
        if not last.get("success"):
            return last
        text = json.dumps(last.get("data") or last.get("text") or "", ensure_ascii=False)
        found = target in text and '"error"' not in text
        if (state == "present" and found) or (state == "absent" and not found):
            return {"success": True, "target": target, "state": state,
                    "waited_s": round(max(0.0, timeout_s - (deadline - time.monotonic())), 2)}
        if time.monotonic() >= deadline:
            return {"success": False, "error": f"等待超时（{timeout_s}s）：{target} 未{ '出现' if state == 'present' else '消失'}",
                    "target": target, "state": state}
        await asyncio.sleep(0.5)


_LOG_TYPES = ("error", "warning", "log")


def _norm_log_types(types: str | list | None) -> list[str]:
    """把 types 归一成该服务器认的取值：**必须是 list**。

    实测（两个坑叠在一起，真游戏上一调就炸）：
    - 服务器只收 list，传字符串会被直接拒："types must be a list, got str"；
    - 取值只认 error/warning/log/all，Unity 习惯写的 "exception"/"assert" 判非法。
    所以这里统一返回 list，并把不认识的取值丢掉；一个都不剩（或含 "all"）就给 ["all"]。
    """
    raw = [types] if isinstance(types, str) else list(types or [])
    parts: list[str] = []
    for chunk in raw:
        parts.extend(x.strip().lower() for x in str(chunk).split(",") if x.strip())
    if not parts or "all" in parts:
        return ["all"]
    return [p for p in parts if p in _LOG_TYPES] or ["all"]


def _console_sync(client: McpClient, call, action: str = "get", filter_text: str = "",
                  limit: int = 50, types: str = "all") -> dict:
    """读 Console。

    实测：这台服务器的 `types` **默认只给 error/warning**，Debug.Log 一条都不回 ——
    平台默认传 "all"（探索时日志和报错一样重要）。
    """
    tool, schema, _flavor = _resolve("console")
    args = _adapt_args({"action": action, "filter_text": filter_text, "limit": limit,
                        "types": _norm_log_types(types)}, schema)
    # 该服务器的 read_console 明说"为了最大兼容性，count 请用带引号的字符串传"
    props = (schema.get("properties") or {})
    for key in ("count", "limit"):
        if key in args and key in props:
            args[key] = str(args[key])
    out = unwrap(call(lambda c: c.call(tool, args))).copy()
    out["tool"] = tool
    # 平台的截图/录像 API 会在 Unity 里留下自己的报错行（见 _PLATFORM_NOISE）——
    # 从这里统一滤掉，工具层与用例层读到的都是"被测对象自己的报错"。
    data = out.get("data")
    cleaned = False
    if isinstance(data, dict):
        if isinstance(data.get("items"), list):
            data["items"] = _drop_platform_noise(data["items"])
            cleaned = True
        elif isinstance(data.get("data"), dict) and isinstance(data["data"].get("items"), list):
            data["data"]["items"] = _drop_platform_noise(data["data"]["items"])
            cleaned = True
    if cleaned and isinstance(out.get("text"), str):
        # text 是原始响应的字符串（整段 JSON 一行）——按行删会把整段删掉，
        # 所以把清洗过的 data 重新序列化回去，让两个视图说的是同一件事。
        out["text"] = json.dumps(data, ensure_ascii=False)
    return out


async def console(action: str = "get", filter_text: str = "", limit: int = 50,
                  types: str = "all") -> dict:
    """读 Unity Console（探索时最值钱的一条：报错优先于猜测）。

    ``types`` 默认 ``"all"``（error,warning,log）—— 服务器自己的默认会漏掉 Debug.Log。
    """
    return await _guard_call(
        lambda: _console_sync(_get_client(), _rpc, action, filter_text, limit, types))


async def screenshot(save_path: str | None = None) -> dict:
    """截 Game View（含 Screen Space - Overlay 的 UI）；图片落盘（平台各处都要文件路径）。"""
    return await _guard_call(lambda: _screenshot_sync(save_path))


_CS_SCREENSHOT = r"""
string __name = "bridge_shot_" + System.DateTime.Now.ToString("yyyyMMdd_HHmmss_fff") + ".png";
string __path = System.IO.Path.Combine(UnityEngine.Application.temporaryCachePath, __name);
var __tex = UnityEngine.ScreenCapture.CaptureScreenshotAsTexture();
if (__tex == null) return "ERROR: CaptureScreenshotAsTexture 返回 null";
byte[] __bytes = UnityEngine.ImageConversion.EncodeToPNG(__tex);
int __w = __tex.width; int __h = __tex.height;
UnityEngine.Object.Destroy(__tex);
System.IO.File.WriteAllBytes(__path, __bytes);
return __path + "|" + __w + "x" + __h;
"""


def _capture_overlay(save_path: str | None, *, client=None, call=None) -> dict | None:
    """用 ScreenCapture 截 Game View（**含 Overlay 的 UI**）。

    为什么要绕开服务器自带的截图工具：那条路是"渲染某个相机"，而
    Screen Space - Overlay 的 Canvas 不进任何相机的渲染 —— 实测 Trash Dash 的
    START 按钮在屏幕坐标上、没被剔除，相机路径的图里却一个 UI 都没有。
    这里截的是游戏视图本身，Overlay / 相机 / 世界空间三种 Canvas 都在；
    编辑器临时目录读不到（比如桥在另一台机器）时返回 None，由调用方退回服务器工具。
    """
    out = _exec_csharp_sync(_CS_SCREENSHOT, client=client, call=call)
    result = str(out.get("result") or "")
    if not out.get("success") or result.startswith("ERROR") or "|" not in result:
        return None
    src, _, size = result.partition("|")
    src_path = Path(src)
    if not src_path.exists():
        return None
    target = _resolve_shot_path(save_path) or (_shots_dir() / src_path.name)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src_path, target)
    try:
        src_path.unlink()
    except OSError:
        pass
    return {"success": True, "path": str(target), "tool": "screencapture", "size": size}


def _screenshot_sync(save_path: str | None, *, client=None, call=None) -> dict:
    # 首选 ScreenCapture（含 Overlay UI）；它失败才退回服务器工具（纯相机视角）
    overlay = _capture_overlay(save_path, client=client, call=call)
    if overlay is not None:
        return overlay
    tool, schema, flavor = _resolve("screenshot")
    # include_image 默认 false（实测该服务器还把内联图压到 640px）——要图就得明说，
    # 并把长边放宽，否则界面上小字看不清。
    args: dict[str, Any] = {"include_image": True, "max_resolution": 1568}
    if flavor == "coplay":
        args.update({"action": "screenshot", "capture_source": "game_view"})
    args = _adapt_args(args, schema)
    raw = (call or _rpc)(lambda c: c.call(tool, args, timeout=90.0))
    if raw.get("isError"):
        return unwrap(raw)
    blocks = [b for b in (raw.get("content") or []) if isinstance(b, dict)]
    for block in blocks:
        if block.get("type") == "image" and block.get("data"):
            path = _save_image(block["data"], block.get("mimeType", "image/png"), save_path)
            return {"success": True, "path": path, "tool": tool}
    out = unwrap(raw, save_image=False)
    if not out.get("success"):
        return out   # 工具自己报的失败（如 "Unity session not available"）原样上抛
    # 没有图片块：有些服务器只回文件名/路径
    text = (out.get("text") or "").strip()
    m = re.search(r"[^\s\"']+\.png", text)
    if m:
        return {"success": True, "path": m.group(0), "tool": tool, "text": text}
    return {"success": False, "error": "服务器没有返回图片内容（可能要开 include_image）",
            "text": text, "tool": tool}


async def run_tests(mode: str = "PlayMode", filter_text: str = "", timeout_s: float = 300.0) -> dict:
    """跑 Unity Test Framework 的测试；CoplayDev 是异步 job，这里轮询到结束。"""
    def _do() -> dict:
        tool, schema, _flavor = _resolve("run_tests")
        args = _adapt_args({"mode": mode, "test_filter": filter_text, "filter_text": filter_text}, schema)
        out = unwrap(_rpc(lambda c: c.call(tool, args, timeout=60.0)))
        out["tool"] = tool
        if not out.get("success"):
            return out
        blob = json.dumps(out.get("data") or out.get("text") or "", ensure_ascii=False)
        m = re.search(r'"?job_?id"?\s*[:=]\s*"?([A-Za-z0-9\-]+)', blob, re.IGNORECASE)
        if not m:
            return out  # 同步实现的服务器：结果就在这次返回里
        job = m.group(1)
        deadline = time.monotonic() + max(10.0, timeout_s)
        while time.monotonic() < deadline:
            time.sleep(2.0)
            jt, js, _ = _resolve("test_job")
            jout = unwrap(_rpc(lambda c: c.call(jt, _adapt_args({"job_id": job}, js), timeout=30.0)))
            jdata = jout.get("data")
            status = json.dumps(jdata or jout.get("text") or "", ensure_ascii=False).lower()
            if any(k in status for k in ('"completed"', '"done"', '"finished"', '"passed"', '"failed"')):
                jout["job_id"] = job
                return jout
        return {"success": False, "error": f"测试任务 {job} 在 {timeout_s}s 内没有结束", "job_id": job}

    if (reason := _bridge_guard.blocked()) is not None:
        return {"success": False, "error": reason}
    try:
        return await asyncio.to_thread(_do)
    except UnityBridgeError as exc:
        return {"success": False, "error": str(exc), "hint": _hint_for_error(str(exc))}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}


async def tools(refresh: bool = False) -> dict:
    """列出服务器提供的全部工具（含入参 schema）—— 认路用。"""
    def _do() -> dict:
        client = _get_client()
        items = client.tools(refresh=refresh)
        return {"success": True, "count": len(items), "server": client.server_info,
                "flavor": client.flavor,
                "tools": [{"name": t.get("name"), "description": (t.get("description") or "")[:300],
                           "schema": t.get("inputSchema") or {}} for t in items]}

    return await _guard_call(_do)


async def call(tool: str, args: dict | None = None, timeout: float = 60.0) -> dict:
    """原样调用服务器上的任意工具（不经过方言适配的逃生口）。"""
    def _do() -> dict:
        out = unwrap(_rpc(lambda c: c.call(tool, args or {}, timeout=timeout)))
        out["tool"] = tool
        return out

    return await _guard_call(_do)


def _same_scene(want: str, path: str) -> bool:
    """两个"场景标识"是不是同一个：全路径相等，或去掉路径/扩展名后同名。

    用例里写 ``RESET = {"scene": "01_moqiaoshanzhuang"}``、状态里记的是
    ``Assets/Mods/SAMPLE/Maps/GameMaps/01_moqiaoshanzhuang.unity`` —— 得认成同一个，
    否则每次复位都去重开一遍场景（脏场景的保存对话框会卡住编辑器）。
    """
    a = str(want or "").strip().replace("\\", "/")
    b = str(path or "").strip().replace("\\", "/")
    if not a or not b:
        return False
    if a == b or a.lower() == b.lower():
        return True
    stem = lambda s: s.rsplit("/", 1)[-1].rsplit(".", 1)[0].strip().lower()   # noqa: E731
    return stem(a) == stem(b)


def _wait_until(pred, timeout_s: float, what: str, interval: float = 0.5) -> None:
    """轮询到 pred() 为真；超时抛 UnityBridgeError（说清在等什么）。"""
    deadline = time.monotonic() + max(1.0, timeout_s)
    while time.monotonic() < deadline:
        if pred():
            return
        time.sleep(interval)
    raise UnityBridgeError(f"等待超时（{timeout_s}s）：{what}")


def unity_on_cached_client() -> Unity:
    """把模块级缓存的那条会话包成一个同步 ``Unity``（给平台侧的工具用）。

    为什么不直接 ``Unity()``：那会**再开一条 MCP 会话**，而 mcp-for-unity 一次只服务
    一条请求 —— 两条会话并发打过去就是当初"工具卡片一直转圈"那场事故的成因
    （见 ``McpClient._gate``）。复用缓存会话，串行化才真正成立。
    """
    u = Unity.__new__(Unity)          # 绕开 __init__：不新建会话
    u._bind(_get_client(), call=_rpc)
    return u


async def reset(scene: str = "", wait_for: str = "", timeout: float = 120.0,
                mode: str = "hard", play: bool = True) -> dict:
    """把游戏复位到「用例起跑线」（语义见 ``Unity.reset``）。"""
    def _do() -> dict:
        out = unity_on_cached_client().reset(scene=scene, wait_for=wait_for,
                                             timeout=timeout, mode=mode, play=play)
        out["success"] = True
        return out

    return await _guard_call(_do)


# ===========================================================================
# 脚本侧：沉淀下来的用例直接用的同步客户端
# ===========================================================================

class Unity:
    """用例脚本里的 Unity 客户端（同步）。

    生成/保存的脚本里 prelude 会注入 ``u = Unity()``：:

        u.play(); u.wait_for("LoginWindow")
        u.click("LoginWindow/StartButton")
        u.expect_text("LoginWindow/Title", "登录")
        u.screenshot("login.png")

    失败一律抛 ``UnityBridgeError``（脚本用 assert 或异常即测试失败），
    这样平台侧的执行记录能靠退出码区分 passed / failed。
    """

    def __init__(self, url: str | None = None, *, transport: str | None = None,
                 command: str | None = None, timeout: float = _DEFAULT_TIMEOUT) -> None:
        t = (transport or settings.unity_mcp_transport or "http").strip().lower()
        if url is None and t == "stdio":
            cmd = command or (settings.unity_mcp_command or "").strip() or \
                "uvx --from mcpforunityserver==10.2.0 mcp-for-unity --transport stdio"
            client = McpClient(_StdioTransport(cmd, timeout),
                               flavor_hint=(settings.unity_mcp_server or "auto").strip().lower())
        else:
            client = McpClient(_HttpTransport(url or settings.unity_mcp_url, timeout),
                               flavor_hint=(settings.unity_mcp_server or "auto").strip().lower())
        self._bind(client, timeout)

    def _bind(self, client: McpClient, timeout: float = _DEFAULT_TIMEOUT,
              call=None) -> None:
        """接上一条会话。字段清单只有这一份 —— 平台侧的工具调用也要包一个 ``Unity``
        （见 ``unity_on_cached_client``），用 ``__new__`` 绕开 ``__init__`` 时不会漏字段。
        """
        self.timeout = timeout
        self._client = client
        # 平台侧复用**缓存**的那条会话，并走带重试的 ``_rpc``（会话过期自动重来）；
        # 脚本子进程里自建会话，直连即可。
        self._call = call or (lambda fn: fn(self._client))
        # ---- 存证：步骤轨迹 / 录像 ----
        # 轨迹默认跟着 runner 注入的环境变量走（用例脚本一行都不用写就有轨迹）；
        # 交互式探索时没人注入，就什么都不记（别在别人的家目录里乱写文件）。
        env_trace = os.environ.get(_TRACE_FILE_ENV, "").strip()
        self._trace_file: Path | None = Path(env_trace) if env_trace else None
        self._steps: list[dict] = []
        self._trace_depth = 0
        self._t0 = time.monotonic()
        self._recording: dict | None = None
        #: 起跑线快照一次就够（见 _snapshot_start_line）
        self._start_line_done = False

    # ---- 步骤轨迹 ---------------------------------------------------------
    def trace_to(self, path: str | Path) -> None:
        """把之后的每一步动作记进 JSONL（失败时这份轨迹就是"走到哪一步挂的"）。"""
        self._trace_file = Path(path)
        self._trace_file.parent.mkdir(parents=True, exist_ok=True)

    def steps(self) -> list[dict]:
        return list(self._steps)

    def _record_step(self, action: str, args: tuple, kwargs: dict,
                     error: str | None, ms: float) -> None:
        target = ""
        if args and isinstance(args[0], str):
            target = args[0]
        else:
            # 关键字调用也要能看出"这一步作用在什么上"：轨迹与运行详情里
            # "reset"/"hierarchy"/"find_by_text" 只写动作名等于没写
            # （复位那一步的 target 就是起跑场景，一眼能看出回到哪儿了）。
            for key in ("target", "scene", "wait_for", "path", "root", "text",
                        "name", "save_path"):
                value = kwargs.get(key)
                if isinstance(value, str) and value:
                    target = value
                    break
        step = {"i": len(self._steps) + 1, "t": round(time.monotonic() - self._t0, 2),
                "action": action, "target": target, "ms": int(ms), "ok": error is None}
        if error:
            step["error"] = error[:2000]
        self._steps.append(step)
        if self._trace_file is None:
            return
        try:
            with self._trace_file.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(step, ensure_ascii=False) + "\n")
        except OSError:
            # 写不进就别每步都炸一次：存证写不下来，不该把用例改判成失败。
            self._trace_file = None

    # ---- 底层 -------------------------------------------------------------
    def status(self) -> dict:
        """与模块级 ``status()`` 同构（脚本 prelude 靠它区分"桥没起"和"Unity 没连"）。"""
        editor = self._client_status_editor()
        instances = _instances_sync(self._client)
        return {"available": True, "server": self._client.server_info,
                "flavor": self._client.flavor,
                "tool_count": len(self._client.tools()), "editor": editor,
                "instances": instances,
                "is_playing": (editor or {}).get("isPlaying"),
                "unity_connected": bool(instances) or editor is not None}

    def _client_status_editor(self) -> dict | None:
        return _editor_state_sync(self._client)

    def tools(self) -> list[dict]:
        return self._client.tools()

    def call(self, tool: str, args: dict | None = None, timeout: float | None = None) -> dict:
        out = unwrap(self._client.call(tool, args or {}, timeout=timeout or self.timeout))
        self._raise(out)
        return out

    def _resolve(self, op: str) -> tuple[str, dict, str]:
        return _resolve(op, self._client, self._call)

    @staticmethod
    def _raise(out: dict) -> dict:
        if not out.get("success"):
            raise UnityBridgeError(out.get("error") or "调用失败")
        return out

    # ---- 编辑器 -----------------------------------------------------------
    def editor_state(self) -> dict | None:
        return _editor_state_sync(self._client)

    def is_playing(self) -> bool:
        return bool((self.editor_state() or {}).get("isPlaying"))

    def play(self, wait_s: float = 15.0) -> dict:
        name, schema, flavor = self._resolve("editor_action")
        args = {"state": _IVAN_STATE["play"]} if flavor == "ivan" else {"action": "play"}
        out = self._raise(unwrap(self._client.call(name, _adapt_args(args, schema))))
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline:
            if self.is_playing():
                return out
            time.sleep(0.5)
        return out

    def stop(self) -> dict:
        name, schema, flavor = self._resolve("editor_action")
        args = {"state": _IVAN_STATE["stop"]} if flavor == "ivan" else {"action": "stop"}
        return self._raise(unwrap(self._client.call(name, _adapt_args(args, schema))))

    def pause(self) -> dict:
        name, schema, flavor = self._resolve("editor_action")
        args = {"state": _IVAN_STATE["pause"]} if flavor == "ivan" else {"action": "pause"}
        return self._raise(unwrap(self._client.call(name, _adapt_args(args, schema))))

    # ---- 复位（回到用例起跑线） -------------------------------------------
    def active_scene(self) -> dict:
        """当前打开的场景（编辑模式下的 active scene）：``{name, path, is_dirty}``。

        认不出来就给空 dict —— 复位里的"起跑场景"是**锦上添花**（没有就只重启
        Play），不该因为某个方言不提供场景元信息就让整个复位不可用。
        """
        try:
            name, schema, flavor = self._resolve("scene")
            if flavor == "ivan":       # ivan 方言的 scene 工具只列已打开场景
                return {}
            out = unwrap(self._client.call(
                name, _adapt_args({"action": "get_active"}, schema)))
        except (UnityBridgeError, KeyError, TypeError):
            return {}
        data = out.get("data")
        # 实测 shape（coplay 3.4.7）：{"success":true,"message":…,"data":{name,path,…}}
        info = data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), dict) else data
        if not isinstance(info, dict):
            return {}
        return {"name": info.get("name"), "path": info.get("path"),
                "is_dirty": bool(info.get("isDirty"))}

    def load_scene(self, path: str) -> dict:
        """在**编辑模式**下打开场景。Play 中不能开场景（Unity 会拦），先 ``stop()``。"""
        name, schema, _flavor = self._resolve("scene")
        out = self._raise(unwrap(self._client.call(
            name, _adapt_args({"action": "load", "path": path}, schema))))
        return out

    def reset(self, scene: str = "", wait_for: str = "", timeout: float = 120.0,
              mode: str = "hard", play: bool = True) -> dict:
        """把游戏复位到「用例起跑线」—— 用例之间的状态隔离靠它。

        **hard（默认）**：退出 Play →（需要时）打开起跑场景 → 重新 Play → 等标志物。
        这是唯一真能"回到起点"的做法：场景对象、DontDestroyOnLoad 的常驻单例、静态
        缓存、网络会话全部重来（重新进 Play 会重载脚本域）。代价是走一遍冷启动。

        **soft**：保持 Play Mode，重载当前场景（``SceneManager.LoadScene``）—— 快，
        但静态状态与跨场景常驻对象不清，只适合"地图/界面状态回起点"。给 ``scene``
        且与当前场景不同时会报错：换场景必须走 hard（编辑模式才能开场景）。

        ``scene`` 接受场景路径或名字，与当前打开的一致就**不重复打开**（避免脏场景
        的保存提示框把编辑器卡在模态上）；``wait_for`` 给起跑线标志物（如 HUD 上的
        「系统」按钮），复位完成的判定就是它回来了 —— 别用 sleep 猜。
        """
        mode = (mode or "hard").strip().lower()
        if mode not in ("hard", "soft"):
            raise UnityBridgeError(f"未知复位方式 {mode!r}（hard / soft）")
        if mode == "soft" and scene and not _same_scene(scene, self.active_scene().get("path") or ""):
            raise UnityBridgeError(
                f"软复位不能换场景（要 {scene}，当前是 {self.active_scene().get('path')}）"
                "—— 换场景请用 mode='hard'")

        t0 = time.monotonic()
        current = self.active_scene()
        if mode == "hard":
            if self.is_playing():
                self.stop()
                _wait_until(lambda: not self.is_playing(), 30.0,
                            "退出 Play Mode（Unity 卡在编译/保存对话框时不会停）")
            want = (scene or "").strip()
            if want and not _same_scene(want, current.get("path") or ""):
                self.load_scene(want)
                after = self.active_scene()
                if after.get("path") and not _same_scene(want, after.get("path") or ""):
                    raise UnityBridgeError(
                        f"起跑场景没打开：想要 {want}，实际是 {after.get('path')}")
            if play and not self.is_playing():
                self.play(wait_s=max(15.0, min(timeout, 60.0)))
                if not self.is_playing():
                    raise UnityBridgeError("Play 没起来（Unity 侧可能在编译或弹窗）")
        else:
            if not self.is_playing():
                raise UnityBridgeError("软复位要求已经在 Play Mode —— 冷启动请用 mode='hard'")
            out = self.exec_csharp(_CS_RELOAD_SCENE, timeout=max(30.0, timeout))
            result = out.get("result")
            if not (isinstance(result, dict) and result.get("ok")):
                raise UnityBridgeError(
                    f"重载场景失败：{(result or {}).get('error') or out.get('error')}")

        if wait_for:
            self.wait_for(wait_for, timeout=timeout, state="present")
        scene_now = self.active_scene()
        return {"ok": True, "mode": mode, "scene": scene_now.get("path") or scene,
                "anchor": wait_for, "seconds": round(time.monotonic() - t0, 1),
                "playing": self.is_playing()}

    # ---- 对象 -------------------------------------------------------------
    def find_objects(self, *, name: str = "", path: str = "", component: str = "",
                     tag: str = "", limit: int = 50, find_inactive: bool = True) -> dict:
        """查对象，返回补全后的对象列表（name/path/active/…）。

        注意：服务器原始返回**只有 instance id**，所以这里给的是平台补过详情的
        ``objects``；原始返回放在 ``raw`` 里备查。
        """
        out = self._raise(_find_objects_sync(self._client, self._call, name=name, path=path,
                                             component=component, tag=tag, limit=limit,
                                             find_inactive=find_inactive))
        return {"objects": out.get("objects") or [], "raw": out.get("data"),
                "count": out.get("object_count"), "detailed": out.get("detailed")}

    def exists(self, target: str) -> bool:
        """对象在不在（bool）。名字查不到就按层级路径查（服务器的 by_path 收半截路径）。

        区分两类失败：**"没找到"**返回 False；**"桥/会话不可用"直接抛错** ——
        否则等待类断言会把自己的环境问题说成"对象未出现"，把人往错方向带
        （实测踩过：Unity 没连上时 `expect_exists` 报"X 未出现"）。
        """
        try:
            for kwargs in ({"name": target}, {"path": target}):
                found = self.find_objects(**kwargs).get("objects") or []
                blob = json.dumps(found, ensure_ascii=False)
                if target.strip() in blob:
                    return True
            # 服务器的 by_name 是精确匹配，名字带空白就查不到（真游戏里撞到过
            # "Button Settings "）；C# 探测这层比对是 Trim 过的，兜住这一类。
            # 注意用底层调用：探测回 ok:false 是"确实没有"，必须返回 False ——
            # 走会抛错的那层会让 expect_absent 把"没找到"当异常抛出去。
            probe = _exec_csharp_sync(cs_present(target), call=self._call, client=self._client)
            payload = probe.get("result")
            if isinstance(payload, dict):
                return bool(payload.get("ok"))
            if probe.get("success") is False:
                raise UnityBridgeError(probe.get("error") or "对象探测失败")
            return False
        except UnityBridgeError as exc:
            raise UnityBridgeError(_env_or_not_found(exc)) from exc

    def is_visible(self, target: str) -> bool:
        """对象当前**显示着**吗（activeInHierarchy）—— 界面开关的断言用这个。

        和 ``exists()`` 的分工：``exists()`` 只回答"在不在场景里"，关掉的界面面板
        仍然"在"；而真游戏里关面板就是把对象停用，所以"关了没"必须看这个。
        """
        objects = self.find_objects(name=target, limit=5).get("objects") or []
        return any(o.get("activeInHierarchy") for o in objects)

    def object(self, target: str, component: str = "") -> dict:
        out = self._raise(_object_info_sync(self._client, self._call, target, component))
        return out.get("data") or {"text": out.get("text")}

    def object_text(self, target: str) -> str:
        """对象（含子孙）上的文本 —— 断言按钮标签这类最常用的用例。

        实测：uGUI 的 Button 自己不带文字，标签在子对象 ``.../PlayButton/Text`` 上，
        只读对象自己的组件会让 ``expect_text("PlayButton", "NOWA GRA")`` 永假。
        自己读不到文本时用 C# 在子孙里收（Text/TMP/InputField 都收得到）。
        """
        data = self.object(target)
        parts: list[str] = []

        def _walk(node: Any) -> None:
            if isinstance(node, dict):
                for k, v in node.items():
                    # 只认**字符串**。以前把数字也收："value" 到处都有 ——
                    # GraphicRaycaster 的 LayerMask 就是 ``{"value": 1023799}``，
                    # 于是一块面板的"文本"读出来是 ``1023799 1023799``（实测：jynew 的
                    # 系统菜单），断言永远不成立、还看不出为什么。数字如果要断言，
                    # 渲染出来的那份文本（Text/TMP）本来就在这棵树里。
                    if k in ("text", "value") and isinstance(v, str):
                        parts.append(v)
                    else:
                        _walk(v)
            elif isinstance(node, list):
                for item in node:
                    _walk(item)

        _walk(data)
        own = " ".join(parts).strip()
        if own:
            return own
        out = self._exec_csharp(cs_text(target))
        payload = out.get("result")
        if isinstance(payload, dict) and payload.get("ok"):
            return " ".join(str(p) for p in (payload.get("parts") or [])).strip()
        return ""

    # ---- 操作 -------------------------------------------------------------
    def _exec_csharp(self, code: str, timeout: float | None = None) -> dict:
        """与平台侧共用同一套解析（返回值/marker/失败判定只写一遍，免得两边漂移）。"""
        return _exec_csharp_sync(code, timeout or self.timeout,
                                 call=self._call, client=self._client)

    def exec_csharp(self, code: str, timeout: float | None = None) -> dict:
        return self._raise(self._exec_csharp(code, timeout))

    def subtree_text(self, target: str) -> str:
        """对象**及其全部子孙**的文本 —— 问"这个面板/列表里现在有什么"用这个。

        和 ``object_text`` 的分工：``object_text`` 先看对象自己，自己有 text/value 就用
        （取单个控件的标签）；而容器身上常挂着无关的 text/value（实测 jynew 的
        ``SystemUIPanel`` 自己回的是 "1023799" 这种 id），拿它当"面板内容"就错了。
        """
        payload = _exec_csharp_sync(cs_text(target), call=self._call, client=self._client)
        result = payload.get("result")
        if isinstance(result, dict) and result.get("ok"):
            return " ".join(str(p) for p in (result.get("parts") or [])).strip()
        raise UnityBridgeError(f"读不到 {target} 的子树文本：{payload.get('error') or '对象不存在'}")

    def hierarchy(self, root: str = "", depth: int = 3, max_nodes: int = 80) -> dict:
        """看（子）树结构：路径/可见性/组件/文本 —— 探索界面的第一步，别猜名字。"""
        out = self._exec_csharp(cs_tree(root, depth, max_nodes))
        parsed = _lines_payload(out)
        if not parsed.get("success"):
            raise UnityBridgeError(parsed.get("error") or "读不到场景层级")
        return {"nodes": parsed["nodes"], "truncated": parsed["truncated"],
                "rows": parsed["rows"],
                "text": _render_table(parsed["rows"], "# 路径 | 可见性 | 组件 | 文本")}

    def find_by_text(self, text: str, root: str = "", limit: int = 20) -> dict:
        """按界面上的文字反查对象（返回命中的对象与往上最近的可点祖先）。"""
        out = self._exec_csharp(cs_find_text(text, root, limit))
        parsed = _lines_payload(out)
        if not parsed.get("success"):
            raise UnityBridgeError(parsed.get("error") or "文本搜索失败")
        return {"hits": parsed["hits"], "scanned": parsed["scanned"], "rows": parsed["rows"],
                "text": _render_table(parsed["rows"], "# 对象路径 | 可见性 | 可点祖先 | 文本")}

    def click(self, target: str) -> dict:
        """点一个 UGUI 控件；点不到会抛错（含"对象不存在/无点击处理器"的区分）。"""
        out = self._exec_csharp(cs_click(target))
        if not out.get("success"):
            raise UnityBridgeError(f"点击失败 {target}: {out.get('error')}")
        return out.get("result") or {}

    def set_text(self, target: str, text: str) -> dict:
        out = self._exec_csharp(cs_set_text(target, text))
        if not out.get("success"):
            raise UnityBridgeError(f"写文本失败 {target}: {out.get('error')}")
        return out.get("result") or {}

    def console(self, *, action: str = "get", filter_text: str = "", limit: int = 50,
                types: str = "all") -> dict:
        out = self._raise(
            _console_sync(self._client, self._call, action, filter_text, limit, types))
        return out.get("data") or {"text": out.get("text")}

    def errors(self, limit: int = 20, types: str = "error") -> list:
        """Console 里的报错（探索时的第一手证据）。

        只按**类型**过滤，不按文案过滤 —— Unity 的报错文案里常常没有 "error" 这个词，
        按文案过滤会把真报错漏掉。要看 warning 一起就传 ``types="error,warning"``。
        （平台自己那条截图噪声在 ``_console_sync`` 里已经滤掉了，这里拿到的都是游戏报错。）
        """
        data = self.console(filter_text="", limit=limit, types=types)
        for key in ("errors", "logs", "messages", "entries", "items", "data"):
            value = data.get(key) if isinstance(data, dict) else None
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                # 实测嵌套：data = {"cursor":…, "items": [...]} —— 只认 data 这一层会永远拿不到
                for inner in ("errors", "logs", "messages", "entries", "items"):
                    if isinstance(value.get(inner), list):
                        return value[inner]
        return []

    def screenshot(self, save_path: str | None = None) -> str:
        """截 Game View（含 Screen Space - Overlay 的 UI），返回落盘路径。

        和平台侧共用同一份实现（``_screenshot_sync``）—— 这里以前另写了一份，结果
        平台修好了、用例脚本还走老路子（两份实现迟早漂移，exec_csharp 也踩过同样的坑）。
        """
        out = self._raise(_screenshot_sync(save_path, client=self._client, call=self._call))
        return out.get("path") or ""

    def run_tests(self, *, mode: str = "PlayMode", filter_text: str = "",
                  timeout_s: float = 300.0) -> dict:
        tool, schema, _ = self._resolve("run_tests")
        args = _adapt_args({"mode": mode, "test_filter": filter_text, "filter_text": filter_text}, schema)
        out = self._raise(unwrap(self._client.call(tool, args, timeout=60.0)))
        blob = json.dumps(out.get("data") or out.get("text") or "", ensure_ascii=False)
        m = re.search(r'"?job_?id"?\s*[:=]\s*"?([A-Za-z0-9\-]+)', blob, re.IGNORECASE)
        if not m:
            return out.get("data") or {"text": out.get("text")}
        job = m.group(1)
        deadline = time.monotonic() + max(10.0, timeout_s)
        while time.monotonic() < deadline:
            time.sleep(2.0)
            jt, js, _ = self._resolve("test_job")
            jout = unwrap(self._client.call(jt, _adapt_args({"job_id": job}, js), timeout=30.0))
            status = json.dumps(jout.get("data") or jout.get("text") or "", ensure_ascii=False).lower()
            if any(k in status for k in ('"completed"', '"done"', '"finished"', '"passed"', '"failed"')):
                return jout.get("data") or {"text": jout.get("text")}
        raise UnityBridgeError(f"测试任务 {job} 在 {timeout_s}s 内没有结束")

    # ---- 断言（Playwright 式期望） ----------------------------------------
    def wait_for(self, target: str, timeout: float = 10.0, state: str = "present") -> None:
        """等对象：present 在场景里 / absent 不在场景里 / hidden 在但当前不显示。"""
        deadline = time.monotonic() + max(1.0, timeout)
        while True:
            if state == "hidden":
                done = not self.is_visible(target)
            else:
                found = self.exists(target)   # 环境问题会在这里立刻抛错，不等满超时
                done = found if state == "present" else not found
            if done:
                self._snapshot_start_line(target, state)
                return
            if time.monotonic() >= deadline:
                verb = {"present": "出现", "absent": "消失", "hidden": "被隐藏"}.get(state, state)
                raise AssertionError(f"等待超时（{timeout}s）：{target} 未{verb}{self._timeout_hint(target, state)}")
            time.sleep(0.4)

    def _snapshot_start_line(self, target: str, state: str) -> None:
        """"等到起跑线标志物"的这一瞬，记下现场（起跑场景 + 标志物）。

        为什么在这里记而不是只在 prelude 里记一次：prelude 那次是在**用例动作之前**，
        对"用例自己 `u.play()`"的写法是空的 —— 那一刻还没进 Play，什么都记不到。
        实测踩到：智能体写的《群侠传》新手流程用例全程由用例自己 play，跑通后起跑线
        仍然是空的，于是下一轮不会复位。

        只在**用例的第一个动作就是等待**时记（`self._steps` 为空）：那才是"等就绪"，
        否则等的是用例中途的某个面板，记下来的是半路状态 —— 比不记更糟。
        """
        if self._start_line_done or self._steps or state != "present":
            return
        path = os.environ.get(_START_STATE_ENV, "").strip()
        if not path:
            return
        self._start_line_done = True
        try:
            if not self.is_playing():
                return
            scene = self.active_scene().get("path") or ""
            if not scene:
                return
            Path(path).write_text(json.dumps(
                {"scene": scene, "play": True, "mode": "hard", "timeout": 180,
                 "wait_for": target}, ensure_ascii=False), encoding="utf-8")
        except Exception:   # noqa: BLE001 —— 记不下起跑线不该影响用例本身
            pass

    def _timeout_hint(self, target: str, state: str) -> str:
        """等超时时补一句"多半是怎么回事" —— 真游戏里踩得最多的一条是搞混了两种"关"。

        `absent`（对象不在场景里）与 `hidden`（在，但被停用）是两件事：uGUI 的面板
        关闭十有八九是 ``SetActive(false)`` —— 对象还在，只是不显示。用 absent 等它
        永远等不到，而报错只说"未消失"，人会去怀疑游戏没关掉（实测：jynew 的系统菜单）。
        """
        if state not in ("absent", "hidden"):
            return ""
        try:
            visible = self.is_visible(target)
        except UnityBridgeError:
            return ""
        if state == "absent" and not visible:
            return (" —— 它还在场景里，只是**不显示了**：关面板请用 "
                    "state=\"hidden\"（或 u.expect_hidden）")
        if state == "hidden" and visible:
            return " —— 它还在显示；想等对象整个消失用 state=\"absent\""
        return ""

    def expect_exists(self, target: str, timeout: float = 10.0) -> None:
        self.wait_for(target, timeout=timeout, state="present")

    def expect_absent(self, target: str, timeout: float = 10.0) -> None:
        self.wait_for(target, timeout=timeout, state="absent")

    def expect_hidden(self, target: str, timeout: float = 10.0) -> None:
        """等它**被隐藏**（关面板）：对象还在场景里但不再显示。"""
        self.wait_for(target, timeout=timeout, state="hidden")

    def expect_text(self, target: str, contains: str, timeout: float = 10.0) -> None:
        deadline = time.monotonic() + max(1.0, timeout)
        last = ""
        while True:
            try:
                last = self.object_text(target)
            except UnityBridgeError as exc:
                last = f"<{exc}>"
            if contains in last:
                return
            if time.monotonic() >= deadline:
                raise AssertionError(f"{target} 的文本里没有 {contains!r}（实际: {last[:300]!r}）")
            time.sleep(0.4)

    # ---- 录像 -------------------------------------------------------------
    @property
    def recording(self) -> bool:
        return self._recording is not None

    def record_start(self, *, fps: float = 6.0, max_frames: int = 1800,
                     name: str | None = None) -> dict:
        """开始逐帧录制（编辑器侧采帧，帧落在 Unity 的临时缓存目录）。

        默认 6fps / 最多 1800 帧（≈5 分钟）。录制会持续占用一点 GPU 与磁盘，
        换来的是**失败现场有录像**——这正是 Playwright 那边 video 的价值。
        """
        subdir = name or time.strftime("rec_%Y%m%d_%H%M%S")
        out = self._raise(self._exec_csharp(cs_record_start(subdir, fps, max_frames),
                                            timeout=max(30.0, self.timeout)))
        result = out.get("result") if isinstance(out.get("result"), dict) else {}
        self._recording = {"dir": result.get("dir") or "", "fps": float(fps),
                           "started": time.monotonic(), "max_frames": int(max_frames)}
        return self._recording

    def record_stop(self, save_as: str | None = "run.mp4", *, keep_frames: bool = False,
                    fps: float | None = None) -> dict:
        """停止录制并合成 mp4（``save_as`` 相对路径按当前工作目录算）。

        不传 ``fps`` 就按**实测速率**合成：编辑器在 Play Mode 下给 update 回调的
        节拍本就慢于请求值（每个 MCP 调用还会占住主线程），按请求值写死会让录像
        比真实时间快放 —— 实测一次 1.7s 的用例只采到 5 帧，写 6fps 就成了 0.8s。

        **不抛异常**：录像只是存证，ffmpeg 缺失/帧目录在另一台机器上都不该把一条
        已经跑出结论的用例改判成失败。失败信息在返回值的 ``error`` 里，prelude
        会把它打进入运行输出。
        """
        info = self._recording or {}
        stopped_at = time.monotonic()
        try:
            out = self._exec_csharp(cs_record_stop(), timeout=max(30.0, self.timeout))
            result = out.get("result") if isinstance(out.get("result"), dict) else {}
        except UnityBridgeError as exc:
            self._recording = None
            return {"ok": False, "error": f"停止录制失败：{exc}"}
        self._recording = None
        folder = Path(result.get("dir") or info.get("dir") or "")
        if not str(folder) or not folder.is_dir():
            return {"ok": False, "frames": int(result.get("frames") or 0), "dir": str(folder),
                    "error": "帧目录不在本机：编辑器和平台不在同一台机器时无法合成录像"
                             "（截图能回传是因为走了 MCP，帧是同机读盘）"}
        frames = _frames_in(folder)
        elapsed = max(0.2, stopped_at - float(info.get("started") or stopped_at))
        measured = len(frames) / elapsed
        fps = float(fps) if fps else (measured if measured >= 0.2 else float(info.get("fps") or 6.0))
        result_out: dict = {"ok": True, "frames": len(frames), "dir": str(folder),
                            "fps": round(fps, 2),
                            "duration_s": round(len(frames) / max(0.2, fps), 1)}
        if save_as:
            target = Path(save_as)
            if not target.is_absolute():
                target = Path.cwd() / target
            stitched = stitch_video(frames, target, fps)
            result_out.update(stitched)
            result_out["path"] = str(target) if stitched.get("ok") else None
        if result_out.get("ok") and not keep_frames:
            shutil.rmtree(folder, ignore_errors=True)
        return result_out

    @contextlib.contextmanager
    def recording_scope(self, save_as: str = "run.mp4", *, fps: float = 6.0):
        """``with u.recording_scope("login.mp4"):`` —— 出来的录像必定收尾。"""
        self.record_start(fps=fps)
        try:
            yield self
        finally:
            self.record_stop(save_as, fps=fps)

    # ---- 失败现场 ---------------------------------------------------------
    def capture_failure(self, save_as: str = "failure.png") -> dict:
        """抓失败现场：截一张图 + 一份人读上下文（走到哪一步、控制台报了什么）。

        Playwright 失败时自动留 failure 截图 + error-context.md；这一条是它的等价物，
        而且**不依赖用例作者**——用例在断言上挂了、根本没走到自己那行 screenshot，
        证据也不会丢。
        """
        stamp = time.strftime("%H:%M:%S")
        result: dict = {"ok": True, "image": None, "context": None, "errors": []}
        try:
            result["image"] = self.screenshot(save_as)
        except Exception as exc:  # noqa: BLE001 —— 连带 Unity 掉线都要兜住
            result["ok"] = False
            result["error"] = f"截图失败：{exc}"
        lines = [f"# 失败现场 {stamp}", ""]
        try:
            state = self.editor_state() or {}
            lines += [f"编辑器: isPlaying={state.get('isPlaying')} "
                      f"isPaused={state.get('isPaused')} state={state.get('state')}", ""]
        except Exception:  # noqa: BLE001
            pass
        steps = self._steps[-25:]
        if steps:
            lines += ["## 走到哪一步", ""]
            for step in steps:
                mark = "OK " if step.get("ok") else "FAIL"
                tail = f"  <- {step['error']}" if step.get("error") else ""
                lines.append(f"- [{mark}] {step['t']}s {step['action']}"
                             f"{(' ' + step['target']) if step.get('target') else ''}"
                             f" ({step['ms']}ms){tail}")
            lines.append("")
        try:
            errors = self.errors(limit=30, types="error,warning")
            result["errors"] = [str(e)[:500] for e in errors[:30]]
            if errors:
                lines += ["## 控制台（error/warning，最后 30 条）", ""]
                lines += [f"- {str(e)[:500]}" for e in errors]
                lines.append("")
        except Exception:  # noqa: BLE001
            pass
        # 最后一个动作如果有对象，把那个对象当前的文本也抓下来：
        # "按钮点了没反应"和"按钮不存在"是两回事，这一行能当场分开。
        last_target = next((s["target"] for s in reversed(self._steps) if s.get("target")), "")
        if last_target:
            try:
                text = self.subtree_text(last_target)
                lines += [f"## {last_target} 的当前文本", "", text[:2000] or "(空)", ""]
            except Exception:  # noqa: BLE001
                pass
        try:
            ctx = Path(save_as).with_suffix(".txt")
            if not ctx.is_absolute():
                ctx = Path.cwd() / ctx
            ctx.write_text("\n".join(lines), encoding="utf-8")
            result["context"] = str(ctx)
        except OSError as exc:
            result["ok"] = False
            result["error"] = (result.get("error") or "") + f" 上下文写入失败：{exc}"
        return result


#: 记进步骤轨迹的动作。只记**用例自己的操作与断言**：轨迹的用途是回答"走到哪一步
#: 挂的、挂之前做了什么"，把 find/console 这类读操作也记进去，真失败会被几十行
#: 噪声淹掉（而读操作的现场，失败上下文里已经带了目标对象的文本）。录像/存证
#: 那些平台自己的收尾动作同理不记 —— 它们的成败已经在运行输出里说清楚了。
_TRACED_ACTIONS = ("click", "set_text", "wait_for", "expect_exists", "expect_absent",
                   "expect_hidden", "expect_text", "screenshot", "play", "stop", "pause",
                   "reset")


def _traced(method):
    """给动作方法套一层"记一笔" —— 成功失败都记，失败先记再抛。

    只记**最外层**那一笔：``expect_exists`` 内部走的是 ``wait_for``，两层都记的话
    轨迹里会出现成对的重复行（"走了两步"其实是一个动作），人读起来就废了。
    """
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        if self._trace_depth:
            return method(self, *args, **kwargs)
        started = time.monotonic()
        error: str | None = None
        self._trace_depth += 1
        try:
            return method(self, *args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 —— 断言失败本身就是要记的证据
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            self._trace_depth -= 1
            self._record_step(method.__name__, args, kwargs, error,
                              (time.monotonic() - started) * 1000)
    return wrapper


for _name in _TRACED_ACTIONS:
    setattr(Unity, _name, _traced(getattr(Unity, _name)))
del _name


__all__ = [
    "Unity", "UnityBridgeError", "call", "click", "console", "cs_click", "cs_describe",
    "cs_find_text", "cs_present", "cs_record_start", "cs_record_stop", "cs_text",
    "cs_tree", "cs_set_text", "editor_action", "exec_csharp", "find_by_text",
    "find_objects", "hierarchy", "object_info", "reset",
    "run_tests", "screenshot", "set_text", "status", "stitch_video", "tools",
    "unity_on_cached_client", "unwrap",
    "wait_for",
]
