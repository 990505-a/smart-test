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
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from src.app.core.breaker import Guard
from src.app.core.config import settings
from src.app.services.unity_recorder import (
    HEARTBEAT_STALE_S,
    cs_drag,
    cs_key,
    cs_record_ui_fetch,
    cs_record_ui_start,
    cs_record_ui_status,
    cs_record_ui_stop,
)

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
        # 硬规则（永不触发域重载）的执行点：下面这批工具在**桥内部**带 preflight，
        # 一旦工程的"外部改动"被判脏，桥会替我们发 refresh_unity(compile="request")
        # —— 强制同步重编译 + 域重载。2026-09-22 就是这么卡死 Unity 的（5 次）。
        if tool in _PREFLIGHT_GATED_TOOLS:
            _refuse_if_project_dirty(self, tool)
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
#: 下面三个是 2026-09-22 加的：那天连着崩了两次 Unity，日志里刷的全是这个钩子。
#: 原来的"保险"只数**成功**的帧，而截图一直被拒时帧数永远是 0 —— 钩子退不掉，
#: 就以 fps 频率一直截（实测一次会话里 11532 次失败），把编辑器和 GPU 一起拖垮。
_REC_TRIES_KEY = "unity_auto_rec_tries"     # 尝试次数（成功失败都算）
_REC_FAILS_KEY = "unity_auto_rec_fails"     # 连续失败次数
_REC_WHY_KEY = "unity_auto_rec_why"         # 停止原因（给人看的一句话）

#: 连续失败多少次就自己退订。20 次 ≈ 5fps 下 4 秒 —— 真不可用时立刻停手，
#: 又不会被 Play Mode 头几帧的偶发失败误伤。
_REC_MAX_FAILS = 20

#: 录像帧率（固定值，2026-09-23 起）：5fps 够看清"点了哪个按钮、面板怎么出现"，
#: 又只有 10fps 一半的写盘量与 GPU 回读次数 —— 配 30 分钟的执行预算 ≈ 9000 帧。
#: 想改就改这一个数（prelude 仍可用环境变量 UNITY_RECORD_FPS 覆盖单次运行）。
DEFAULT_RECORD_FPS = 5.0


def record_budget(fps: float = DEFAULT_RECORD_FPS) -> tuple[int, int]:
    """录像的（帧数上限, 秒上限）—— 跟着**执行预算**走，别各写一套。

    为什么必须联动：执行预算调大（比如 30 分钟）而录像上限还写死 5 分钟的话，
    长流程的录像会莫名其妙在第 5 分钟停掉，人看到的是"录像少了后半段"，
    很难联想到是两处常量没对齐。帧数按 fps × 秒数算出来，保证两道闸一致。
    """
    try:
        seconds = int(float(settings.unity_run_timeout_s))
    except (TypeError, ValueError):
        seconds = 1800
    seconds = max(30, seconds)
    return int(round(fps * seconds)), seconds

#: 进出 Play 时编辑器会重排渲染目标，这时截一帧可能失败。挂钩子前**先试一帧**：
#: 试不过就干脆不挂（把原因说给用例听），而不是挂上去刷几万次失败。
#:
#: 试的是**文件版**（和钩子、和 `unity_screenshot` 同一条路）：2026-09-23 实测
#: `CaptureScreenshotAsTexture()` 在 `execute_code` 与 `EditorApplication.update`
#: **两个上下文里都返回 null**（它只能在 end-of-frame 调），拿它当探针的结果是
#: 每一次录制都被"录像不可用：…返回 null"挡掉；而文件版在同一钩子里成功落盘
#: 1157745 字节。落盘是 end-of-frame 的事，所以要**挂一次性钩子 + 稍后再问结果**：
#: 这就是本函数返回"已武装"、`probe_capture_ok` 再读结果的原因。
_CS_CAPTURE_PROBE_ARM = r"""// capture-probe: 挂一次性钩子，试一帧（文件版）后把结果记进 SessionState
string __probe_dir = System.IO.Path.Combine(UnityEngine.Application.temporaryCachePath,
                                            "unity-auto-probe");
System.IO.Directory.CreateDirectory(__probe_dir);
string __probe_path = System.IO.Path.Combine(__probe_dir, "probe_" + System.Guid.NewGuid()
                                             .ToString("N").Substring(0, 8) + ".png");
UnityEditor.SessionState.SetString("unity_auto_probe_result", "pending");
UnityEditor.SessionState.SetString("unity_auto_probe_path", __probe_path);
UnityEditor.SessionState.SetInt("unity_auto_probe_ticks", 0);
UnityEditor.EditorApplication.CallbackFunction __pcb = null;
__pcb = delegate {
  int __n = UnityEditor.SessionState.GetInt("unity_auto_probe_ticks", 0) + 1;
  UnityEditor.SessionState.SetInt("unity_auto_probe_ticks", __n);
  if (__n < 2) return;                     // 第 1 帧只是刚挂上，落盘还没轮到
  string __p = UnityEditor.SessionState.GetString("unity_auto_probe_path", "");
  if (UnityEditor.SessionState.GetString("unity_auto_probe_result", "") != "pending") {
    UnityEditor.EditorApplication.update -= __pcb;
    return;
  }
  if (System.IO.File.Exists(__p) && new System.IO.FileInfo(__p).Length > 0) {
    UnityEditor.EditorApplication.update -= __pcb;
    UnityEditor.SessionState.SetString("unity_auto_probe_result",
        "OK:" + new System.IO.FileInfo(__p).Length);
    return;
  }
  // 别急着判死：`CaptureScreenshot` 是**异步**的（排到 end-of-frame 写盘），
  // 实测同一台机器上有时第 2 帧就到、有时要等几帧 —— 只给一两帧的耐心，
  // 录像是"有时候能开始、有时候报不可用"（2026-09-23 11:35 实测踩到）。
  // 给它 ~3 秒（60fps 约 180 帧；编辑器卡着时按帧数算也够）。
  if (__n >= 180) {
    UnityEditor.EditorApplication.update -= __pcb;
    UnityEditor.SessionState.SetString("unity_auto_probe_result",
        "ERROR: 请求截图后 3 秒仍没有落盘（" + __p + "）");
  }
};
UnityEditor.EditorApplication.update += __pcb;
UnityEngine.ScreenCapture.CaptureScreenshot(__probe_path);
return "ARMED:" + __probe_path;
"""

#: 探针结果的读取（与上一步隔着一次往返 + 一点等待，见 ``probe_capture_ok``）。
_CS_CAPTURE_PROBE_READ = r"""// capture-probe: 读上次试拍的结果
return UnityEditor.SessionState.GetString("unity_auto_probe_result", "pending") + "|"
     + UnityEditor.SessionState.GetInt("unity_auto_probe_ticks", 0);
"""


def cs_record_start(subdir: str, fps: float, max_frames: int, max_seconds: int = 300,
                    max_tries: int = 0, max_fails: int = _REC_MAX_FAILS) -> str:
    """挂钩子开始逐帧录制。

    钩子自己有三道保险，任何一道到点就退订 —— 一个挂在编辑器里、不会自己停的
    每帧截图循环，代价是整台机器（2026-09-22 实测：残留钩子把 D3D11 设备刷掉、
    整机只能断电）：

    - ``max_frames`` 帧数上限（成功的路径）；
    - ``max_tries`` 尝试次数上限（默认 4× 帧数：失败也算，防"一直截不到"）;
    - ``max_seconds`` **墙上时钟**上限（帧数/尝试次数都挡不住"帧率被拖慢"的情形）。
    """
    gap = round(1.0 / max(0.5, min(60.0, fps)), 4)
    max_seconds = max(30, int(max_seconds))
    max_tries = int(max_tries) or max(600, int(max_frames) * 4)
    return r"""
var __dir = System.IO.Path.Combine(UnityEngine.Application.temporaryCachePath,
                                   "unity-auto-rec", "{subdir}");
System.IO.Directory.CreateDirectory(__dir);
UnityEditor.SessionState.SetString("{dir_key}", __dir);
UnityEditor.SessionState.SetBool("{on_key}", true);
UnityEditor.SessionState.SetInt("{n_key}", 0);
UnityEditor.SessionState.SetInt("{tries_key}", 0);
UnityEditor.SessionState.SetInt("{fails_key}", 0);
// 上一轮可能留了个"待验收"的路径（那个文件属于上一次录制）—— 不清掉会把别人的帧记到这一轮
UnityEditor.SessionState.SetString("{pending_key}", "");
UnityEditor.SessionState.SetString("{why_key}", "");
UnityEditor.SessionState.SetFloat("{gap_key}", {gap}f);
UnityEditor.SessionState.SetInt("{max_key}", {max_frames});
UnityEditor.SessionState.SetInt("{max_tries_key}", {max_tries});
UnityEditor.SessionState.SetBool("{was_playing_key}", UnityEditor.EditorApplication.isPlaying);
UnityEditor.SessionState.SetFloat("{deadline_key}",
    (float)UnityEngine.Time.realtimeSinceStartup + {max_seconds}f);
double __last = 0.0;
// 必须声明成 CallbackFunction 而不是 System.Action：EditorApplication.update 是
// **命名委托类型**，C# 不允许用 Action 去 += / -=（实测报
// "Operator `-=' cannot be applied to operands of type CallbackFunction and System.Action"）。
UnityEditor.EditorApplication.CallbackFunction __cb = null;
System.Action<string> __disarm = delegate(string __why) {{
  UnityEditor.SessionState.SetString("{why_key}", __why);
  UnityEditor.SessionState.SetBool("{on_key}", false);
  UnityEditor.EditorApplication.update -= __cb;
}};
__cb = delegate {{
  if (!UnityEditor.SessionState.GetBool("{on_key}", false)) {{
    UnityEditor.EditorApplication.update -= __cb;
    return;
  }}
  // 退出 Play 就收工：挂钩子时若在 Play，那么 Play 结束之后再截已经没意义了。
  // （挂钩子时不在 Play 的话不管这条，别把"编辑模式下的录制"误伤掉。）
  if (UnityEditor.SessionState.GetBool("{was_playing_key}", false)
      && !UnityEditor.EditorApplication.isPlaying) {{
    __disarm("Play 已结束");
    return;
  }}
  double __now = (double)UnityEngine.Time.realtimeSinceStartup;
  // 墙上时钟上限：帧数/尝试次数都只挡得住"有在跑"的钩子，这条保证它一定会退订。
  if (__now > (double)UnityEditor.SessionState.GetFloat("{deadline_key}", 0f)) {{
    __disarm("到时间上限（{max_seconds}s）");
    return;
  }}
  if (__now - __last < (double)UnityEditor.SessionState.GetFloat("{gap_key}", {gap}f)) return;
  __last = __now;
  // 先验收**上一拍**请求的那一帧：文件版是 Unity 自己排到 end-of-frame 写的，
  // 所以"请求"和"落盘"天然隔一拍 —— 这一拍验收，同时发下一张，帧率不降。
  string __pending = UnityEditor.SessionState.GetString("{pending_key}", "");
  if (!string.IsNullOrEmpty(__pending)) {{
    UnityEditor.SessionState.SetString("{pending_key}", "");
    if (System.IO.File.Exists(__pending) && new System.IO.FileInfo(__pending).Length > 0) {{
      UnityEditor.SessionState.SetInt("{n_key}", UnityEditor.SessionState.GetInt("{n_key}", 0) + 1);
      UnityEditor.SessionState.SetInt("{fails_key}", 0);
    }} else {{
      int __f = UnityEditor.SessionState.GetInt("{fails_key}", 0) + 1;
      UnityEditor.SessionState.SetInt("{fails_key}", __f);
      if (__f >= {max_fails}) {{
        __disarm("逐帧截图连续失败 " + __f + " 次，已停止录制（最后一帧没落盘："
                 + __pending + "）");
        return;
      }}
      UnityEditor.SessionState.SetString("{why_key}",
          "逐帧截图连续失败 " + __f + " 次（最后一帧没落盘：" + __pending + "）");
    }}
  }}
  int __n = UnityEditor.SessionState.GetInt("{n_key}", 0);
  if (__n >= UnityEditor.SessionState.GetInt("{max_key}", {max_frames})) {{
    __disarm("帧数到上限（" + __n + "）");
    return;
  }}
  int __tries = UnityEditor.SessionState.GetInt("{tries_key}", 0) + 1;
  UnityEditor.SessionState.SetInt("{tries_key}", __tries);
  if (__tries > UnityEditor.SessionState.GetInt("{max_tries_key}", {max_tries})) {{
    __disarm("尝试次数到上限（" + __tries + " 次，成功 " + __n + " 帧）");
    return;
  }}
  // 用**文件版**截：`CaptureScreenshotAsTexture()` 在 update 回调里实测恒为 null
  // （它只能在 end-of-frame 调），旧版钩子因此每一帧都抛异常、留下一堆假"失败"。
  try {{
    string __shot = System.IO.Path.Combine(
        UnityEditor.SessionState.GetString("{dir_key}", __dir),
        string.Format("f_{{0:D5}}.png", __n));
    UnityEngine.ScreenCapture.CaptureScreenshot(__shot);
    UnityEditor.SessionState.SetString("{pending_key}", __shot);
  }} catch (System.Exception __e) {{
    int __f2 = UnityEditor.SessionState.GetInt("{fails_key}", 0) + 1;
    UnityEditor.SessionState.SetInt("{fails_key}", __f2);
    if (__f2 >= {max_fails}) {{
      __disarm("逐帧截图连续失败 " + __f2 + " 次，已停止录制（" + __e.Message + "）");
    }} else {{
      UnityEditor.SessionState.SetString("{why_key}",
          "逐帧截图连续失败 " + __f2 + " 次：" + __e.Message);
    }}
  }}
}};
UnityEditor.EditorApplication.update += __cb;
return "{{\"ok\":true,\"dir\":\"" + __dir.Replace("\\", "/") + "\",\"gap\":" + {gap}
     + ",\"max_tries\":" + {max_tries} + "}}";
""".format(subdir=subdir.replace('"', ""), dir_key=_REC_DIR_KEY, on_key=_REC_ON_KEY,
           n_key=_REC_N_KEY, gap_key=_REC_GAP_KEY, max_key=_REC_MAX_KEY,
           tries_key=_REC_TRIES_KEY, fails_key=_REC_FAILS_KEY, why_key=_REC_WHY_KEY,
           pending_key="unity_auto_rec_pending",
           max_tries_key="unity_auto_rec_max_tries",
           was_playing_key="unity_auto_rec_was_playing",
           deadline_key="unity_auto_rec_deadline",
           gap=gap, max_frames=int(max_frames), max_tries=int(max_tries),
           max_seconds=int(max_seconds), max_fails=int(max_fails))


def cs_record_stop() -> str:
    """解除钩子并回传结果（帧数 / 尝试次数 / 停止原因）。

    ``reason`` 只在**钩子自己退订**过的时候才回（帧数/尝试次数/时间上限、连续失败、
    退出 Play）——那才是"录像提前结束"。平台主动停的那次：钩子只是被通知收工，
    而它最后发出的那一帧还没来得及验收（文件版隔一拍落盘），残留的"连续失败 1 次"
    会被当成故障播出去，实测一句 `WARN: 录像提前结束 —— 逐帧截图连续失败 1 次`
    盖在一段 44 帧、10.8s 的正常录像上。
    """
    return r"""
bool __was_on = UnityEditor.SessionState.GetBool("{on_key}", false);
UnityEditor.SessionState.SetBool("{on_key}", false);
string __dir = UnityEditor.SessionState.GetString("{dir_key}", "");
int __n = UnityEditor.SessionState.GetInt("{n_key}", 0);
int __tries = UnityEditor.SessionState.GetInt("{tries_key}", 0);
string __why = __was_on ? "" : UnityEditor.SessionState.GetString("{why_key}", "");
System.Threading.Thread.Sleep(150);
return "{{\"ok\":true,\"dir\":\"" + __dir.Replace("\\", "/") + "\",\"frames\":" + __n
     + ",\"tries\":" + __tries
     + ",\"reason\":\"" + __why.Replace("\\", "\\\\").Replace("\"", "'") + "\"}}";
""".format(on_key=_REC_ON_KEY, dir_key=_REC_DIR_KEY, n_key=_REC_N_KEY,
           tries_key=_REC_TRIES_KEY, why_key=_REC_WHY_KEY)


def _frames_in(folder: Path) -> list[Path]:
    """录到的帧（``f_00000.png``；老录像的 ``.jpg`` 也认，迁移期两代并存）。"""
    try:
        return sorted(p for p in folder.iterdir()
                      if p.suffix.lower() in (".png", ".jpg") and p.name.startswith("f_"))
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
    # 帧名是 f_00000.png 这种定宽序号，用 %05d 让 ffmpeg 自己按序读；扩展名跟着
    # 实际帧走（新录像 PNG、老录像 JPG —— 混着放会让我读一半就断）。
    suffix = frames[0].suffix.lower() or ".png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [exe, "-y", "-loglevel", "error", "-framerate", f"{max(1.0, fps):.3f}",
           "-start_number", "0", "-i", str(frames[0].parent / f"f_%05d{suffix}"),
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
        # 熔断期间顺手探一次：Unity 重启过（换实例）就自动解除，不然平台会一直卡着。
        if _gpu_state["lost"]:
            _gpu_recheck_sync()
        rpc_client = _rpc(lambda c: c.tools())
        instances = _instances_sync(client)
        editor = _editor_state_sync(client)
        connected = bool(instances) or editor is not None
        if not connected:
            # 掉线了：是"普通没连上"还是"显卡把编辑器打死了"，只有编辑器自己的日志知道
            # —— 顺手读一眼（带 mtime + TTL 缓存，5 秒内最多读一次）。
            scan_editor_log()
        dirty = _project_external_changes_dirty(client)
        playing = bool((editor or {}).get("isPlaying"))
        # 有实例清单却读不到编辑器状态 = 编辑器忙（域重载 / 导入中）或刚掉线。
        # 这两件事在平台上长得一样，但下一步该做什么完全不同：忙要等，掉线要重启
        # MCP 桥 —— 所以分开报，别让 agent 对着"未连接"瞎试。
        stale = bool(instances) and editor is None
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
            # 工程有未导入的外部改动 → 桥会在下次带 preflight 的工具调用里自己
            # 刷新+请求重编译（= 域重载）。是就如实报出去，让 agent 先请用户刷新。
            "external_changes_dirty": dirty,
            # 连上没有以实例清单为准（编辑器状态在编辑器忙/重编译时可能读不到）
            "unity_connected": connected,
            # 编辑器在、但状态读不到：正在域重载 / 导入中 / 刚掉线。
            "editor_stale": stale,
            # 那批"桥会自己刷新 + 重编译"的工具现在能不能发：没连上就不用说，
            # 脏了不能发，Play 中更不能（重载会毁掉这一局）。
            "can_run_gated_tools": connected and not dirty and not playing,
            "gated_tools": sorted(_PREFLIGHT_GATED_TOOLS),
            # 显卡设备丢失（DXGI_ERROR_DEVICE_REMOVED）：编辑器随时会关，平台已停手。
            "gpu_device_lost": bool(_gpu_state["lost"]),
            "gpu_evidence": str(_gpu_state["evidence"] or ""),
            # 编辑器日志多久没写过了。**只在已知出问题时当线索**：正常空闲也会几分钟不写。
            "editor_log_age_s": (round(editor_log_age_s() or 0.0, 1)
                                 if _gpu_state["lost"] else None),
            "advice": _status_advice(stale=stale, playing=playing, dirty=dirty,
                                     connected=connected,
                                     gpu_lost=str(_gpu_state["evidence"] or ""),
                                     log_age_s=editor_log_age_s() if _gpu_state["lost"] else None),
        }

    if (reason := _bridge_guard.blocked()) is not None:
        return {"available": False, "error": reason, "hint": ""}
    try:
        return await asyncio.to_thread(_do)
    except UnityBridgeError as exc:
        return {"available": False, "error": str(exc), "hint": _hint_for_error(str(exc))}
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "error": f"{type(exc).__name__}: {exc}", "hint": ""}


def _status_advice(*, stale: bool, playing: bool, dirty: bool,
                   connected: bool = True, gpu_lost: str = "",
                   log_age_s: float | None = None) -> list[str]:
    """状态页/agent 照着做的一行行话（没有问题时返回空表）。"""
    out: list[str] = []
    if gpu_lost:
        # 放在最前面：这条压过其它一切 —— 显卡没了，别的建议都没有意义。
        out.append("**显卡设备丢失**（DXGI_ERROR_DEVICE_REMOVED / 0x887a0005）："
                   "平台已停手，编辑器随后会自行关闭。请用户更新显卡驱动、检查供电线/PCIe "
                   "插槽与超频降压设置，然后重启 Unity（新实例起来后熔断自动解除）。")
        # 待机/睡眠是这台机器上最常见的触发点（合盖、Idle Timeout 都会），
        # 恢复后 D3D 设备可能已经失效 —— 值得单独点一句。
        out.append("同一时间如果有待机/睡眠/合盖（Windows 事件里是"
                   "「正在进入新型待机状态」），那条就是触发点：Unity 在 Play 时机器睡眠，"
                   "恢复后显卡设备常常已经失效。跑 Unity 时把电源计划设成「从不睡眠」，"
                   "别合盖。")
        if log_age_s is not None and log_age_s > 60:
            out.append(f"编辑器日志已经 {int(log_age_s)} 秒没有写入了 —— 编辑器多半不是"
                       "「掉线」而是**已经卡死**（日志停在最后一行）。请在任务管理器里"
                       "结束 Unity 再重新打开工程。")
    if not connected and not stale:
        out.append("Unity 编辑器没连上：请用户在 Unity 里打开工程、"
                   "Window ▸ MCP for Unity 连到本机 5016。")
    if stale:
        out.append("编辑器有实例但状态读不到：多半正在域重载 / 导入资产。等它回来"
                   "（别继续发命令）；一直不回就重启 unity-mcp 服务。")
    if dirty and playing:
        out.append("工程有未导入的外部改动，且正在 Play：**先退出 Play**，再调 "
                   "unity_sync_assets 清标记，否则那批工具一个都发不出去。")
    elif dirty:
        out.append("工程有未导入的外部改动（latch，Ctrl+R 清不掉）：调 "
                   "unity_sync_assets 清掉（只刷新、不重编译），再继续。")
    return out


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


#: 桥内部带 ``preflight(..., refresh_if_dirty=True)`` 的工具（清单来自桥源码
#: ``services/tools/*.py``）。工程被判"有未导入的外部改动"时，**桥自己**会调
#: ``refresh_unity(mode=if_dirty, compile="request")``：强制同步刷新 + 请求重编译
#: = 一次域重载。所以这些工具在脏的时候一个都不能代发（硬规则：平台永不触发 reload）。
_PREFLIGHT_GATED_TOOLS = frozenset({
    "manage_scene", "find_gameobjects", "manage_components", "manage_prefabs",
    "run_tests", "manage_asset", "manage_gameobject", "manage_texture",
})

#: 脏检查的缓存秒数：状态资源本身很便宜，但每次工具调用都读一遍没必要
_DIRTY_CHECK_TTL_S = 5.0
_dirty_cache: tuple[float, bool, str] | None = None


def _deep_find(node: object, key: str) -> object | None:
    """在嵌套的 payload 里按 key 找一个值（各家状态形状不一致，别写死层级）。"""
    if isinstance(node, dict):
        if key in node:
            return node[key]
        for value in node.values():
            found = _deep_find(value, key)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _deep_find(item, key)
            if found is not None:
                return found
    return None


def _project_external_changes_dirty(client: McpClient) -> bool:
    """工程里有没有"Unity 还没导入的外部改动"（桥侧扫描器判定，带几秒缓存）。

    真源：桥的 ``services/state/external_changes_scanner.py`` 扫工程目录（跳过
    Library/Temp/Logs），看到比基线更新的 mtime 就置脏；之后任何一个带 preflight 的
    工具调用都会触发"刷新 + 请求重编译"。所以这里必须先知道脏不脏。
    """
    global _dirty_cache
    now = time.monotonic()
    if _dirty_cache is not None and now - _dirty_cache[0] < _DIRTY_CHECK_TTL_S:
        return _dirty_cache[1]

    dirty = False
    try:
        uri = (_RESOURCE_TEMPLATES.get(client.flavor) or {}).get("editor_state")
        if uri:
            payload = _read_resource_sync(client, uri, timeout=10.0)
            value = _deep_find(payload, "external_changes_dirty")
            dirty = bool(value) if value is not None else False
    except Exception:  # noqa: BLE001 — 读不到就按"不脏"放行：宁可漏判也不要卡死正常流程
        dirty = False
    _dirty_cache = (now, dirty)
    return dirty


def _gate_state(client: McpClient) -> dict | None:
    """代发"闸内工具"之前要看的那一眼现场：``{dirty, knows_dirty, playing}``。

    和 ``_project_external_changes_dirty`` 的区别在**读不到时怎么办**：那条给
    ``status()`` 用，读不到就报"不脏"（状态页不该因为一次读失败就变红）；这条给
    闸门用，读不到返回 ``None``，由调用方**拒绝**。

    不吃那 5 秒缓存是有意的 —— 危险就在这个缝里：2026-09-23 01:37 的事故中，平台
    缓存里还是"干净"，而桥进程里的扫描器已经变脏，于是那记 ``manage_scene`` 被
    放过去，桥自己发了 ``refresh_unity(compile="request")``：Play Mode 里一次
    域重载，编辑器卡死在 Reloading Domain，随后 D3D11 设备丢失、整机断电。
    """
    uri = (_RESOURCE_TEMPLATES.get(client.flavor) or {}).get("editor_state")
    if not uri:
        # 这个方言没有"编辑器状态"资源（平台只认识了 coplay 的那几个）—— **问都问不了**，
        # 也就无从知道它会不会替我们刷新，按"不脏"放行（否则换一台 MCP 服务器就整个不可用）。
        return {"dirty": False, "knows_dirty": False, "playing": False}
    try:
        payload = _read_resource_sync(client, uri, timeout=10.0)
    except Exception:  # noqa: BLE001 —— 能问却问不到：编辑器忙/正在重载/已掉线，按危险处理
        return None
    dirty = _deep_find(payload, "external_changes_dirty")
    playing = _deep_find(payload, "isPlaying")
    if playing is None:
        playing = _deep_find(payload, "is_playing")
    return {
        # 桥压根没有这个标志（别的方言）→ 它也不会替我们刷新，按"不脏"走
        "dirty": bool(dirty) if dirty is not None else False,
        "knows_dirty": dirty is not None,
        "playing": bool(playing) if playing is not None else False,
    }


def _refuse_if_project_dirty(client: McpClient, tool: str) -> None:
    """闸门：脏 / 读不到 / Play 中带脏 —— 一律拒绝代发（桥会借这次调用重编译）。

    三种拒绝对应三件要做的事，文案里都写清楚：读不到 → 稍后重试 / 看编辑器是不是
    掉线；脏 + Play → **先退出 Play**（唯一会毁掉这一局并卡死编辑器的组合）；
    脏 + 非 Play → ``unity_sync_assets``（只刷新、不重编译）或重启 unity-mcp。
    特别写明 Ctrl+R 没用：这标记是桥进程内存里的 latch，只有桥自己的刷新会清它。
    """
    state = _gate_state(client)
    if state is None:
        raise UnityBridgeError(
            f"拒绝调用 {tool}：读不到 Unity 的编辑器状态，无法确认工程里有没有"
            "「未导入的外部改动」。这批工具在桥内部带 preflight，脏的时候会自己"
            "「刷新 + 请求重编译」（= 域重载）——**读不到就不放行**。稍后重试；"
            "一直读不到就先看 unity_status（编辑器可能正在重载或已经掉线）。"
        )
    if not state["dirty"]:
        return
    if state["playing"]:
        raise UnityBridgeError(
            f"拒绝调用 {tool}：工程有未导入的外部改动，而且 Unity **正在 Play Mode**。"
            "这次调用会触发「刷新 + 请求重编译」= 一次域重载 —— Play 中重载会毁掉这一局，"
            "实测还会把编辑器卡死在 Reloading Domain（只能关掉编辑器重开）。"
            "请先在 Unity 里退出 Play，再用 unity_sync_assets 清标记（只刷新、不重编译），"
            "清完重新进 Play。"
        )
    raise UnityBridgeError(
        f"拒绝调用 {tool}：Unity 工程里有未导入的外部改动（刚拉过代码 / 改过资源文件），"
        "这批工具在桥内部带 preflight —— 脏的时候桥会自己「刷新 + 请求重编译」，"
        "那就是一次域重载，平台按硬规则（永不触发 reload）拒绝执行。"
        "**注意：在 Unity 里按 Ctrl+R / Assets ▸ Refresh all 清不掉这个标记**"
        "（它是桥进程内存里的 latch，只有桥自己的刷新会清它）。"
        "正确做法二选一：① 调 unity_sync_assets（非 Play 时可用，只刷新、不重编译）；"
        f"② 重启 unity-mcp 服务。清完再调 {tool}。"
    )


# ===========================================================================
# GPU 设备丢失熔断（DEVICE_REMOVED）
# ===========================================================================
#: 显卡被驱动/系统摘掉时，Unity 编辑器自己的日志长这样（2026-09-23 10:26 实测，
#: 整机卡死到只能长按电源）：
#:
#:   D3D11: Failed to create RenderTexture (828 x 1472 fmt 26 aa 1), error 0x887a0005
#:   …（85 条）…
#:   Failed to present D3D11 swapchain due to device reset/removed. … This is an
#:   unrecoverable error and the editor will shut down.
#:
#: ``0x887a0005`` = ``DXGI_ERROR_DEVICE_REMOVED``：显卡没了，编辑器随后**一定会**死。
#: 此刻平台唯一正确的动作是**停手**：再发任何 Unity 调用，都只是往一块已经不存在的
#: GPU 上继续叠加负载（那个现场紧接着就是整机 socket 缓冲区耗尽 / 掉电重启）。
#: 所以这里置一个熔断标记，所有工具调用一律拒绝，并在文案里让人去看显卡。
_GPU_LOSS_MARKS = (
    "0x887a0005",
    "dxgi_error_device_removed",
    "device reset/removed",
    "failed to present d3d11 swapchain",
    "d3d11: failed to create",
)

#: 扫描预算：一段结果里只看前 12 万字（截图 base64 是几十万个字符的噪声）。
_GPU_SCAN_MAX = 120_000

#: 熔断期间重新探活的最小间隔（秒）：够便宜，又不至于每次都去打一个可能已经不在的编辑器。
_GPU_RECHECK_S = 20.0

_gpu_state: dict[str, Any] = {"lost": False, "when": 0.0, "evidence": "",
                              "instances": "", "probed": 0.0}


def _gpu_scan_text(payload: object, budget: int = _GPU_SCAN_MAX) -> str:
    """把结果里可能有签名的部分拼成一段文本（图片 base64 只取头尾，别整个遍历）。"""
    parts: list[str] = []
    spent = 0

    def _walk(node: object, depth: int = 0) -> None:
        nonlocal spent
        if spent >= budget or depth > 6:
            return
        if isinstance(node, str):
            if len(node) > 20_000:            # 图片 base64 / 超大文本：签名总在报错行里
                parts.append(node[:300] + " … " + node[-300:])
                spent += 600
            else:
                parts.append(node)
                spent += len(node)
        elif isinstance(node, dict):
            for value in node.values():
                _walk(value, depth + 1)
        elif isinstance(node, (list, tuple)):
            for value in node:
                _walk(value, depth + 1)

    _walk(payload)
    return "\n".join(parts)


def _gpu_evidence_in(payload: object) -> str:
    """结果文本里有没有"显卡被摘掉"的签名（有就返回命中那一行，便于人一眼看懂）。"""
    blob = _gpu_scan_text(payload)
    if not blob:
        return ""
    low = blob.lower()
    for mark in _GPU_LOSS_MARKS:
        at = low.find(mark)
        if at < 0:
            continue
        start = blob.rfind("\n", 0, at) + 1
        end = blob.find("\n", at)
        line = " ".join(blob[start: end if end >= 0 else len(blob)].split())
        if not line:      # 整段就是一行超长 JSON：退回窗口截取
            line = " ".join(blob[max(0, at - 160): at + 200].split())
        return line[:400]
    return ""


def note_gpu_loss(payload: object) -> bool:
    """扫一段输出；命中就置熔断。返回"现在是否处于熔断状态"。"""
    evidence = _gpu_evidence_in(payload)
    if not evidence:
        return bool(_gpu_state["lost"])
    if not _gpu_state["lost"]:
        _gpu_state.update(lost=True, when=time.time(), evidence=evidence,
                          instances=_instance_key(), probed=time.time())
        print(f"[unity] **GPU 设备丢失熔断**：{evidence[:300]}")
    return True


def gpu_device_lost() -> str:
    """熔断中返回现场证据（一句话），健康返回空串。"""
    return str(_gpu_state["evidence"]) if _gpu_state["lost"] else ""


def clear_gpu_loss(reason: str = "") -> None:
    """解除熔断（只该在"确认 Unity 重启过 / 显卡恢复正常"之后调）。"""
    if _gpu_state["lost"]:
        print(f"[unity] GPU 熔断解除：{reason or '人工确认'}")
    _gpu_state.update(lost=False, evidence="", instances="", when=0.0, probed=0.0)


def _instance_key() -> str:
    """当前连着的 Unity 实例指纹（换实例 = Unity 重启过）。读不到就返回空串。"""
    try:
        return "|".join(sorted(str(i.get("id") or i.get("name") or "") for i in
                               _instances_sync(_get_client())))
    except Exception:  # noqa: BLE001 —— 探活失败不该影响调用方
        return ""


def _gpu_recheck_sync() -> bool:
    """熔断期间的自动解除：编辑器换成**另一个实例**了（= Unity 重启过）就放行。

    没有这条，一次瞬时现象会把平台焊死到进程结束 —— 而现场的处理办法恰恰就是
    "重启 Unity"，所以判据选"实例指纹变了"，而不是"过了多久"。读不到实例时**保持熔断**
    （宁可多拦一次，也不要往一块状态不明的显卡上继续发指令）。
    """
    if not _gpu_state["lost"]:
        return False
    now = time.time()
    if now - float(_gpu_state.get("probed") or 0.0) < _GPU_RECHECK_S:
        return True
    _gpu_state["probed"] = now
    fresh = _instance_key()
    if fresh and fresh != str(_gpu_state.get("instances") or ""):
        clear_gpu_loss(f"Unity 实例已更换（{_gpu_state.get('instances') or '未知'} → {fresh}）")
        return False
    return True


def _gpu_refusal_text(evidence: str) -> str:
    return (
        "拒绝调用：Unity 编辑器已经报出**显卡设备丢失**"
        f"（DXGI_ERROR_DEVICE_REMOVED / 0x887a0005），平台按硬规则停手不再发任何指令。\n"
        f"现场证据：{evidence[:400]}\n"
        "这件事软件层修不了：编辑器随后会自行关闭（Unity 原话 the editor will shut down），"
        "继续调用只会往一块已经不在的显卡上叠加负载 —— 2026-09-23 那次现场紧接着就是"
        "整机资源耗尽、只能长按电源重启。\n"
        "现在该做的：① 别重试、别换工具绕（用例的下一次工具调用也会被拒，这是有意的）；"
        "② 去看 Unity 的 Editor.log（`%LOCALAPPDATA%\\Unity\\Editor\\Editor.log`）确认这条报错；"
        "③ 请用户检查显卡本体：驱动版本、供电线、PCIe 插槽、超频/降压设置；"
        "④ 重启 Unity（平台检测到新实例后会自动解除熔断）。"
    )


#: 编辑器日志的尾部读取量。显卡丢失/卡死都写在最后几屏里，读整份（几 MB）没必要。
_EDITOR_LOG_TAIL = 200_000

#: 同一份日志最多每 5 秒看一次（日志一直在长，纯按 mtime 缓存等于每次都读）。
_EDITOR_LOG_TTL_S = 5.0
_editor_log_cache: dict[str, Any] = {"mtime": 0.0, "size": 0, "evidence": "",
                                     "checked": 0.0, "age": None}


def editor_log_path() -> Path | None:
    """本机 Unity 的 Editor.log（Windows / macOS / Linux 三个默认位置）。"""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or ""
        if not base:
            return None
        path = Path(base) / "Unity" / "Editor" / "Editor.log"
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Logs" / "Unity" / "Editor.log"
    else:
        path = Path.home() / ".config" / "unity3d" / "Editor.log"
    return path if path.is_file() else None


def scan_editor_log(*, force: bool = False) -> str:
    """读 Editor.log 尾部找「显卡设备丢失」签名；命中就置熔断并返回证据。

    插件掉线之后，平台自己的调用一律失败、什么都看不到 —— 但**编辑器自己的日志**
    还在这台机器上，显卡丢失的原话（``0x887A0005`` / swapchain device reset）就在
    里面。这是唯一一条"Unity 已经死了、平台还能知道为什么"的通路：
    2026-09-23 12:25 那次就是这么丢的（插件 1005 掉线、熔断没响，页面上只显示
    "未连接"，人得自己去翻 Editor.log 才知道是显卡）。
    """
    if gpu_device_lost() and not force:
        return gpu_device_lost()      # 已经熔断了，不用再读文件
    path = editor_log_path()
    if path is None:
        return ""
    now = time.time()
    try:
        stat = path.stat()
    except OSError:
        return ""
    if (not force and _editor_log_cache["mtime"] == stat.st_mtime
            and now - float(_editor_log_cache["checked"] or 0) < _EDITOR_LOG_TTL_S):
        return str(_editor_log_cache["evidence"] or "")
    try:
        with path.open("rb") as fh:
            fh.seek(max(0, stat.st_size - _EDITOR_LOG_TAIL))
            blob = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    evidence = _gpu_evidence_in(blob)
    _editor_log_cache.update(mtime=stat.st_mtime, checked=now, evidence=evidence,
                             size=stat.st_size, age=max(0.0, now - stat.st_mtime))
    if evidence:
        note_gpu_loss({"source": "Editor.log", "evidence": evidence})
        return evidence
    return ""


def editor_log_age_s() -> float | None:
    """Editor.log 多久没写过了（秒）。**只在已知出问题时**当线索用：正常的空闲编辑器
    也会几分钟不写一行，单看它说明不了任何事。"""
    path = editor_log_path()
    if path is None:
        return None
    try:
        return max(0.0, time.time() - path.stat().st_mtime)
    except OSError:
        return None


async def sync_assets() -> dict:
    """安全清理「未导入的外部改动」这个 latch：**只刷新，不请求重编译**。
    为什么需要单独一条：那标记是桥（MCP 服务器进程）内存里的 latch，一旦置脏就
    不会自己消失，而 Ctrl+R / Assets ▸ Refresh all **清不掉**它（插件从不把自己
    刷新的结果回报给扫描器）。脏着的时候那批带 preflight 的工具一个都发不出去，
    整个自动化就卡住了 —— 这条走 ``refresh_unity(compile="none")``：刷新资产但不
    请求重编译，因此**不产生域重载**。

    **Play 中拒绝**：刷新本身也会打断这一局（大工程要几秒到几十秒），平台不在
    Play 里做任何刷新 —— 这是"永不触发 reload"之外的第二条硬规则。
    """
    def _probe() -> dict | None:
        return _gate_state(_get_client())

    state = await asyncio.to_thread(_probe)
    if state is None:
        return {"success": False,
                "error": "读不到 Unity 编辑器状态（编辑器可能正在重载 / 已经掉线）"}
    if state["playing"]:
        return {"success": False, "dirty": state["dirty"],
                "error": "Unity 正在 Play Mode —— 请先在 Unity 里退出 Play 再同步资源"
                         "（刷新会打断这一局；平台不在 Play 中做刷新）"}

    def _do() -> dict:
        client = _get_client()
        tool, schema, _flavor = _resolve("refresh")
        args = _adapt_args({"mode": "if_dirty", "scope": "all",
                            "compile": "none", "wait_for_ready": False}, schema)
        return unwrap(client.call(tool, args, timeout=120.0), save_image=False)

    try:
        out = await asyncio.to_thread(_do)
    except UnityBridgeError as exc:
        return {"success": False, "error": str(exc), "dirty": state["dirty"],
                "hint": "清不掉就直接重启 unity-mcp 服务（标记在它的进程内存里）"}

    after = await asyncio.to_thread(_probe)
    still = bool((after or {}).get("dirty"))
    return {
        "success": not still,
        "dirty_before": state["dirty"],
        "dirty_after": (after or {}).get("dirty"),
        "result": out,
        "hint": ("标记已清，可以继续" if not still else
                 "刷完了还是脏：多半是工程里又有文件在变（版本管理 / 打包脚本 / 游戏自己"
                 "在写盘）。重启 unity-mcp 服务可以强制清一次。"),
    }


async def disarm_all_recorders() -> dict:
    """把挂在编辑器上的录制钩子都卸掉（帧录像 + 手动录制）。

    退出路径必须有一条"不管父进程死活都能收尾"的通道：帧钩子挂在
    ``EditorApplication.update`` 上，是**编辑器**在按 fps 一直截图 —— runner 被
    硬杀（超时 / 用户中断 / 进程被杀）时它的 atexit 不会执行。2026-09-22 就是残留
    的帧钩子（一次会话 11532 次失败截图）把 D3D11 设备刷掉的。
    """
    report: dict = {}

    for key, fn in (("frames", lambda: unity_on_cached_client().record_stop("run.mp4")),
                    ("ui", lambda: unity_on_cached_client().record_ui_stop())):
        try:
            report[key] = await asyncio.to_thread(fn)
        except Exception as exc:  # noqa: BLE001 —— 编辑器可能已经不在了，收尾尽力而为
            report[key] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return report


#: "取状态"这件事在各家方言里的叫法（用于判断某个工具的 schema 认不认）
_STATE_ACTIONS = ("get_state", "state", "get", "status", "info", "query")


def _accepts_state_action(tool: dict) -> bool:
    """这个工具是不是"取编辑器状态"的？

    只看名字会踩坑：coplay 的 ``manage_editor`` 把 ``action`` 限成一长串枚举
    （play/pause/stop/...），**里面根本没有取状态的值** —— 拿 ivan 方言的
    ``get_state`` 去调它，每次都被判参数非法。实测桥日志里这种无效调用积了 170 条
    （每轮探活一条，2026-09-22 定位）。schema 没把 action 限成枚举的（通常是
    "一个工具一个动作"的方言）视为可以试。
    """
    props = (tool.get("inputSchema") or {}).get("properties") or {}
    key = _pick_key(set(props.keys()), "action") or "action"
    enum = (props.get(key) or {}).get("enum")
    if not isinstance(enum, list) or not enum:
        return True
    return any(a in {str(v).strip().lower() for v in enum} for a in _STATE_ACTIONS)


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
        if not _accepts_state_action(tool):
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
    # 显卡已经丢了：一律不发（急停 / 卸钩子 / 同步资源那几条不走这里，不受影响）。
    if gpu_device_lost() and await asyncio.to_thread(_gpu_recheck_sync):
        return {"success": False, "gpu_device_lost": True, "stop": True,
                "error": _gpu_refusal_text(gpu_device_lost())}
    if (reason := _bridge_guard.blocked()) is not None:
        return {"success": False, "error": reason}
    try:
        out = await asyncio.to_thread(fn)
    except UnityBridgeError as exc:
        note_gpu_loss(str(exc))
        if not gpu_device_lost():
            # 调用失败时顺手看一眼编辑器日志：显卡丢失的原话只写在那儿，
            # 插件掉线之后平台自己再也看不到（2026-09-23 12:25 的盲区）。
            await asyncio.to_thread(scan_editor_log)
            if gpu_device_lost():
                return {"success": False, "gpu_device_lost": True, "stop": True,
                        "error": _gpu_refusal_text(gpu_device_lost())}
        return {"success": False, "error": str(exc), "hint": _hint_for_error(str(exc))}
    except Exception as exc:  # noqa: BLE001
        note_gpu_loss(str(exc))
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}
    note_gpu_loss(out)
    return out


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


async def drag(from_target: str, to_target: str, steps: int = 12) -> dict:
    """拖拽（完整指针序列，见 ``cs_drag``）：录制回放与手写用例共用。"""
    out = await _guard_call(
        lambda: _exec_csharp_sync(cs_drag(from_target, to_target, steps)))
    out["action"] = "drag"
    out["target"] = f"{from_target} -> {to_target}"
    return out


async def key(key: str) -> dict:
    """按一次键（尽力而为，见 ``Unity.key``）。"""
    out = await _guard_call(lambda: _exec_csharp_sync(cs_key(key)))
    out["action"] = "key"
    out["target"] = key
    return out


# ---- 手动录制（玩家自己点，平台录成用例）----------------------------------

def _ui_rec_envelope(res: object) -> dict:
    """把 ``Unity.record_ui_*`` 的**结果字典**包成平台统一的信封。

    为什么要这一层（实测踩到）：类方法与模块级函数的返回形态不同 ——
    `click`/`screenshot` 这类模块级函数返回 `{"success":…, "result":…}`，而
    `Unity.record_ui_start` 返回的是内层 result（`{"ok":true,"file":…}`）。
    服务层按统一信封读 `success`，少了这层就会把**成功**的注入报成失败。
    """
    if not isinstance(res, dict):
        return {"success": False, "error": "桥返回了非字典结果", "result": {}}
    if res.get("ok") is False:
        return {"success": False, "error": str(res.get("error") or "操作失败"), "result": res}
    return {"success": True, "result": res}


async def record_ui_start(*, name: str = "", max_seconds: int = 3600,
                          max_events: int = 5000) -> dict:
    """安装/重挂 UI 录制器（幂等；钩子活着时不重复挂）。"""
    def _do() -> dict:
        return unity_on_cached_client().record_ui_start(
            name=name, max_seconds=max_seconds, max_events=max_events)
    out = _ui_rec_envelope(await _guard_call(_do))
    out["action"] = "record_ui_start"
    return out


async def record_ui_status() -> dict:
    """录制状态（开没开/已录几条/心跳多旧）——平台轮询它就是"自动重挂"的依据。"""
    def _do() -> dict:
        return unity_on_cached_client().record_ui_status()
    out = _ui_rec_envelope(await _guard_call(_do))
    out["action"] = "record_ui_status"
    return out


async def record_ui_stop() -> dict:
    """停止录制（事件文件留在 Unity 临时目录，随后由 record_ui_fetch 取回）。"""
    def _do() -> dict:
        return unity_on_cached_client().record_ui_stop()
    out = _ui_rec_envelope(await _guard_call(_do))
    out["action"] = "record_ui_stop"
    return out


async def record_ui_fetch(since: int = 0, cap: int = 300) -> dict:
    """分片取录制事件（长录制必须分片：MCP 响应有上限）。"""
    def _do() -> dict:
        return unity_on_cached_client().record_ui_fetch(since, cap)
    out = _ui_rec_envelope(await _guard_call(_do))
    out["action"] = "record_ui_fetch"
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


#: 抓图第一手段：**文件版** ``ScreenCapture.CaptureScreenshot(path)``。
#: 为什么不用 ``CaptureScreenshotAsTexture()``：那个 API 必须在 end-of-frame 调用，
#: 而我们的代码是从 ``EditorApplication.update``（插件命令队列）里跑的 —— 实测
#: （2026-09-23，1080x1920 的移动端工程）它**直接返回 null**，于是"截一张看一眼"
#: 这条最该好用的路整个失效：工具报错、录像探针失败、失败现场没图。
#: 文件版是 Unity 自己排到 end-of-frame 写的，从哪儿调都能出图，而且**不需要场景里有
#: 相机**（编辑模式下游戏场景常常一个相机都没有 —— 相机是运行时建的），
#: Overlay UI 也照收（实测 1MB PNG，剧情页的血条/按钮/文字全在）。
#:
#: **不许出现 ``System.IO.File.Delete``**：插件的 ``execute_code`` 安检把它列在
#: ``Blocked pattern``，整段代码会被原样拒绝（实测 11:29 前后三连：每次都退到相机截图，
#: 而相机截图看不见 Overlay UI —— 表面上"success"却是错的图）。文件名靠
#: 毫秒时间戳 + Guid 前 6 位保证不重，压根不需要先删。
_CS_SCREENSHOT_FILE = r"""
string __name = "bridge_shot_" + System.DateTime.Now.ToString("yyyyMMdd_HHmmss_fff")
              + "_" + System.Guid.NewGuid().ToString("N").Substring(0, 6) + ".png";
string __path = System.IO.Path.Combine(UnityEngine.Application.temporaryCachePath, __name);
UnityEngine.ScreenCapture.CaptureScreenshot(__path);
return "FILE:" + __path;
"""


#: 兜底：文件版拿不到图（老版本 Unity / 被平台策略挡住）时再试 texture 版。
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


#: 文件版落盘是"下一帧才写"的（Unity 排到 end-of-frame），所以要等一等再看 ——
#: 0.15s × 20 ≈ 3s 上限；判据是"文件存在且大小连续两次读到一样"（写一半就读会拿到半张图）。
_SHOT_WAIT_S = 0.15
_SHOT_TRIES = 20


def _wait_for_shot(path: Path) -> int:
    """等截图落盘，返回字节数（0 = 超时/是空文件）。"""
    last = -1
    for _ in range(_SHOT_TRIES):
        time.sleep(_SHOT_WAIT_S)
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size <= 0:
            continue
        if size == last:      # 连着两次一样 → 写完了
            return size
        last = size
    return max(0, last)


#: 活动场景路径：走 execute_code（**只读**）。不用 ``manage_scene`` 是有意的 ——
#: 那个工具在桥内部带 preflight，脏工程上会由桥自己发 refresh_unity(compile="request")，
#: 2026-09-23 01:37 的域重载卡死就是这么发出去的（"记一下起跑线"这种无害需求）。
_CS_ACTIVE_SCENE = r"""
var __scene = UnityEngine.SceneManagement.SceneManager.GetActiveScene();
if (!__scene.IsValid()) return "{\"ok\":false,\"error\":\"没有活动场景\"}";
string __p = __scene.path;
if (string.IsNullOrEmpty(__p)) __p = __scene.name;
return "{\"ok\":true,\"path\":\"" + __p.Replace("\\", "\\\\").Replace("\"", "'") + "\"}";
"""


#: 编辑器侧截图的连续失败计数（**只是诊断信息与"这次改道"的判据，不永久关闭**）。
#:
#: 为什么不再"永久改道"：用户口径是"Play 下截图要**一直可用**"。永久熔断的代价是 ——
#: 一次瞬时失败（游戏正在切场景/加载、编辑器刚重编译完）就把这条最好的路封死到会话
#: 结束，之后每次都退到"相机截图"（看不见 Overlay UI）甚至报错。截图是低频动作
#: （不像逐帧录像每秒都在打 GPU），每次重试的代价只是一次 execute_code 往返，
#: 所以这里改成：每次调用都先试最好的路；连续失败只在**当次**改道，并把原因写在
#: 结果里（note），下一次仍然从文件版开始。
_OVERLAY_FAILS_TO_SWITCH = 2
_overlay_state: dict[str, Any] = {"fails": 0, "why": "", "last_error": ""}


def _overlay_disabled_reason() -> str:
    """连续失败≥2 时给一句"这次为什么改道"（成功一次就清空）。"""
    if int(_overlay_state["fails"]) < _OVERLAY_FAILS_TO_SWITCH:
        return ""
    return str(_overlay_state["why"])


def _capture_overlay(save_path: str | None, *, client=None, call=None) -> dict | None:
    """截 Game View（**含 Overlay 的 UI**）—— 编辑器侧两条路，先文件版，再 texture 版。

    为什么要绕开服务器自带的截图工具：那条路是"渲染某个相机"，而
    Screen Space - Overlay 的 Canvas 不进任何相机的渲染 —— 实测 Trash Dash 的
    START 按钮在屏幕坐标上、没被剔除，相机路径的图里却一个 UI 都没有。更糟的是
    编辑模式下游戏场景**常常一个相机都没有**（相机是运行时建的），那条路会直接报
    "No camera found in the scene. Add a Camera …"（2026-09-23 实测踩到，agent 想
    "截一张看一眼"却被这条路挡住）。

    这里截的是游戏视图本身，Overlay / 相机 / 世界空间三种 Canvas 都在，
    **Play 内外都能出图、也不需要相机**；编辑器临时目录读不到（比如桥在另一台机器）
    时返回 None，由调用方退回服务器工具。

    **每次都从最好的路开始试**（文件版 → texture 版），不设"永久改道"：一次瞬时失败
    （切场景 / 刚重编译）不该把这条路封死到会话结束 —— 截图是低频动作，重试很便宜。
    连续失败只在当次结果里留一句说明（note），下一次照样重试。

    **两条路的错误都要留着**：只报"最后一个错误"会让真凶被掩盖 —— 实测就是
    texture 版那句"返回 null"（它本来就不该在我们这个调用点成功）盖住了文件版
    被插件安检拦下的真相（``Blocked pattern: System.IO.File.Delete``）。
    """
    errors: list[str] = []
    for label, snippet in (("文件版", _CS_SCREENSHOT_FILE), ("texture 版", _CS_SCREENSHOT)):
        out = _exec_csharp_sync(snippet, client=client, call=call)
        result = str(out.get("result") or "")
        if out.get("success") and result.startswith("FILE:"):
            src_path = Path(result[5:])
            if _wait_for_shot(src_path):
                target = _resolve_shot_path(save_path) or (_shots_dir() / src_path.name)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src_path, target)
                try:
                    src_path.unlink()
                except OSError:
                    pass
                _overlay_state["fails"] = 0
                size = _png_size(target)
                return {"success": True, "path": str(target), "tool": "screencapture",
                        **({"size": size} if size else {})}
            errors.append(f"{label}：截图文件没有落盘（{result[5:]}）")
            continue
        if out.get("success") and "|" in result:
            src, _, size = result.partition("|")
            src_path = Path(src)
            if src_path.exists():
                target = _resolve_shot_path(save_path) or (_shots_dir() / src_path.name)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src_path, target)
                try:
                    src_path.unlink()
                except OSError:
                    pass
                _overlay_state["fails"] = 0
                return {"success": True, "path": str(target), "tool": "screencapture",
                        "size": size}
            errors.append(f"{label}：落了盘但文件不见了")
            continue
        errors.append(f"{label}：{result or str(out.get('error') or '未知')}")
    _overlay_state["fails"] = int(_overlay_state["fails"]) + 1
    _overlay_state["last_error"] = "；".join(e[:160] for e in errors)[:400]
    _overlay_state["why"] = (
        "编辑器侧截图（ScreenCapture 文件版 + texture 版）这次都没成；"
        + _overlay_state["last_error"])
    return None


def _png_size(path: Path) -> str:
    """从 PNG 头里读宽高（不装图像库；读不到就不报 size）。"""
    try:
        head = path.read_bytes()[:24]
    except OSError:
        return ""
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n":
        return ""
    width = int.from_bytes(head[16:20], "big")
    height = int.from_bytes(head[20:24], "big")
    return f"{width}x{height}" if width and height else ""


def _screenshot_sync(save_path: str | None, *, client=None, call=None) -> dict:
    # 首选 ScreenCapture（含 Overlay UI）；它失败才退回服务器工具（纯相机视角）
    overlay = _capture_overlay(save_path, client=client, call=call)
    if overlay is not None:
        return overlay
    # 编辑器侧那条路被熔断时，如实说清楚"这张图是怎么来的"——相机截图看不见
    # Overlay 的 UI，不知道这件事的人会以为"按钮没渲染出来"。
    note = _overlay_disabled_reason()
    tool, schema, flavor = _resolve("screenshot")
    # include_image 默认 false（实测该服务器还把内联图压到 640px）——要图就得明说，
    # 并把长边放宽，否则界面上小字看不清。
    args: dict[str, Any] = {"include_image": True, "max_resolution": 1568}
    if flavor == "coplay":
        args.update({"action": "screenshot", "capture_source": "game_view"})
    args = _adapt_args(args, schema)
    raw = (call or _rpc)(lambda c: c.call(tool, args, timeout=90.0))
    if raw.get("isError"):
        return _translate_shot_error(unwrap(raw))
    blocks = [b for b in (raw.get("content") or []) if isinstance(b, dict)]
    for block in blocks:
        if block.get("type") == "image" and block.get("data"):
            path = _save_image(block["data"], block.get("mimeType", "image/png"), save_path)
            return {"success": True, "path": path, "tool": tool, **({"note": note} if note else {})}
    out = unwrap(raw, save_image=False)
    if not out.get("success"):
        return _translate_shot_error(out)   # 把插件内部报错翻成"下一步做什么"
    # 没有图片块：有些服务器只回文件名/路径
    text = (out.get("text") or "").strip()
    m = re.search(r"[^\s\"']+\.png", text)
    if m:
        return {"success": True, "path": m.group(0), "tool": tool, "text": text}
    return {"success": False, "error": "服务器没有返回图片内容（可能要开 include_image）",
            "text": text, "tool": tool}


#: 插件在"编辑模式 + 场景里没有相机"时给的原文。它说得没错，但对平台的使用者
#: （人和 agent）没有信息量：真正要知道的是"为什么截不到、那我现在该干嘛"。
_SHOT_NO_CAMERA = ("no camera found in the scene", "outside of play mode")


def _translate_shot_error(out: dict) -> dict:
    """截图失败的报错翻译：相机/Play 这一类死胡同，说清楚原因与替代手段。"""
    blob = f"{out.get('error') or ''} {out.get('text') or ''}".lower()
    if any(marker in blob for marker in _SHOT_NO_CAMERA):
        return {
            "success": False,
            "error": (
                "截不到游戏画面：编辑器现在**不在 Play**（编辑模式下 Game View 没有帧"
                "可截），而这个场景在编辑模式下也没有相机（相机是游戏运行时建的）。"
                "→ 要看画面：请让用户在 Unity 里点 Play，然后再截图；"
                "→ 不打算进 Play：界面信息改用 unity_hierarchy / unity_find_by_text / "
                "unity_object_text（这些不需要画面），控制台报错用 unity_console。"
            ),
            "tool": out.get("tool"),
        }
    return out


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


def _scene_matches(want: str, path: str) -> bool:
    """"场景标识"是不是同一个：全路径相等，或去掉路径/扩展名后同名。

    用例里写 ``scene="01_moqiaoshanzhuang"``、现场是
    ``Assets/Mods/SAMPLE/Maps/GameMaps/01_moqiaoshanzhuang.unity`` —— 得认成同一个，
    否则会把"已经在起跑线"误判成"要复位"。
    """
    a = str(want or "").strip().replace("\\", "/")
    b = str(path or "").strip().replace("\\", "/")
    if not a or not b:
        return False
    if a == b or a.lower() == b.lower():
        return True
    stem = lambda s: s.rsplit("/", 1)[-1].rsplit(".", 1)[0].strip().lower()   # noqa: E731
    return stem(a) == stem(b)


def start_line_instruction(scene: str = "", wait_for: str = "", playing: bool = True) -> str:
    """起跑线差距的人话说明（要不要回过去由用户决定：平台不复位、也不拦执行）。"""
    lines = ["当前不在起跑线（平台不强制，回不回去由你决定）："]
    if scene:
        lines.append("  起跑要求场景：%s" % scene)
    if wait_for:
        lines.append("  起跑要求标志物：界面上出现 %s" % wait_for)
    if not playing:
        lines.append("  另外：Unity 现在不在 Play Mode，请先在 Unity 里点 Play。")
    lines.append("  要恢复的话：在 Unity 里把游戏调成上面这个状态（重进 Play / 手动走回该界面），")
    lines.append("              然后重新运行本用例。")
    return "\n".join(lines)


async def check_start_line(scene: str = "", wait_for: str = "") -> dict:
    """看当前**是不是起跑线**（只读）。不在就把"该复位到什么状态"讲成人话。

    平台不做复位（2026-09-22 起，理由见 ``unity_service`` 的起跑线一节）：这里
    只回答两个问题 —— 在不在起跑线、不在的话该恢复成什么样，动作由用户来做。
    """
    def _do() -> dict:
        u = unity_on_cached_client()
        state = u.editor_state() or {}
        playing = bool(state.get("isPlaying"))
        now_scene = str((u.active_scene() or {}).get("path") or "") if playing else ""
        want_scene = str(scene or "").strip()
        anchor = str(wait_for or "").strip()
        reasons: list[str] = []
        if not playing:
            reasons.append("Unity 不在 Play Mode")
        if want_scene and not _scene_matches(want_scene, now_scene):
            reasons.append(f"当前场景是 {now_scene or '(未知)'}，要的是 {want_scene}")
        if anchor and playing and not u.exists(anchor):
            reasons.append(f"界面上还没出现 {anchor}")
        out = {"success": True, "at_start_line": not reasons, "playing": playing,
               "scene": now_scene, "want_scene": want_scene, "wait_for": anchor}
        if reasons:
            out["reasons"] = reasons
            out["instruction"] = start_line_instruction(want_scene, anchor, playing)
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
            # "hierarchy"/"find_by_text" 只写动作名等于没写。
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

    def active_scene_path(self) -> str:
        """当前活动场景的资产路径（``Assets/…/*.unity``），读不到给空串。

        **走 execute_code，不走 ``manage_scene``** —— 这是有意的：``manage_scene``
        在桥内部带 ``preflight(refresh_if_dirty=True)``，工程被判脏时会**由桥自己**
        发一次 ``refresh_unity(compile="request")``（= 域重载）。2026-09-23 01:37
        卡死编辑器、最终整机断电的那一记域重载，就是从"跑用例时想记一下起跑线场景"
        这条无害需求、经 ``manage_scene`` 发出去的。读路径不该有写风险。
        """
        try:
            out = self._exec_csharp(_CS_ACTIVE_SCENE, timeout=self.timeout)
        except UnityBridgeError:
            return ""
        result = out.get("result") if isinstance(out.get("result"), dict) else {}
        return str(result.get("path") or "").strip() if result.get("ok") else ""

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
                {"scene": scene, "play": True, "mode": "lua", "timeout": 180,
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

    def record_start(self, *, fps: float = DEFAULT_RECORD_FPS,
                     max_frames: int | None = None,
                     max_seconds: int | None = None, name: str | None = None) -> dict:
        """开始逐帧录制（编辑器侧采帧，帧落在 Unity 的临时缓存目录）。

        默认 **5fps**；帧数与秒数上限**跟着执行预算走**（``record_budget``：30 分钟
        的预算就是 9000 帧 / 1800s），两条都可由调用方显式覆盖。墙上时钟那条是必须的：
        帧数与尝试次数都只挡得住"有在跑"的钩子 —— 一个挂在编辑器里、不会自己停的
        每帧截图循环，代价是整台机器（2026-09-22 实测：残留钩子把 D3D11 设备刷掉）。
        录制会持续占用一点 GPU 与磁盘，换来的是**失败现场有录像**。

        **挂钩子之前先试一帧**（``probe_capture_ok``）：截不到就不挂，直接
        抛 ``UnityBridgeError`` 说明原因。实测那台工程 Screen 报 1080x1920、
        Game View 只有 1754x1299，逐帧截图每次都被拒 —— 那种情况下挂上去只是
        以 fps 频率白刷（并持续打 GPU），用例该照常跑，只是没有录像。
        """
        budget_frames, budget_seconds = record_budget(fps)
        max_frames = int(max_frames or budget_frames)
        max_seconds = int(max_seconds or budget_seconds)
        if gpu_device_lost():
            # 显卡已经没了：这时候去挂一个"每帧截图"的钩子，就是往坏掉的 GPU 上继续加负载。
            raise UnityBridgeError("录像不可用：显卡设备已丢失（DXGI_ERROR_DEVICE_REMOVED）")
        ok, detail = self.probe_capture_ok()
        if not ok:
            raise UnityBridgeError("录像不可用：" + detail)
        subdir = name or time.strftime("rec_%Y%m%d_%H%M%S")
        out = self._raise(self._exec_csharp(
            cs_record_start(subdir, fps, max_frames, max_seconds=max_seconds),
            timeout=max(30.0, self.timeout)))
        result = out.get("result") if isinstance(out.get("result"), dict) else {}
        self._recording = {"dir": result.get("dir") or "", "fps": float(fps),
                           "started": time.monotonic(), "max_frames": int(max_frames),
                           "max_seconds": int(max_seconds)}
        return self._recording

    def probe_capture_ok(self, *, tries: int = 12, wait_s: float = 0.4) -> tuple[bool, str]:
        """试拍一帧（**文件版**），返回 ``(能不能截, 说明)``。

        为什么是两步：文件版由 Unity 排到 end-of-frame 落盘，"请求"和"落盘"天然
        隔一拍，一次 ``execute_code`` 往返里看不到结果。所以先武装一次性钩子
        （``_CS_CAPTURE_PROBE_ARM``，它自己会在下一帧验收并记进 SessionState），
        再轮询读结果（``_CS_CAPTURE_PROBE_READ``）。

        为什么不用 ``CaptureScreenshotAsTexture`` 当探针：2026-09-23 实测它在
        ``execute_code`` 和 ``EditorApplication.update`` 两个上下文里**都返回 null**
        （那个 API 只能在 end-of-frame 调）—— 拿它当探针等于把每一次录制都判成
        "录像不可用"，而真正能用的文件版从没被试过。
        """
        armed = self._exec_csharp(_CS_CAPTURE_PROBE_ARM, timeout=max(30.0, self.timeout))
        armed_text = str((armed or {}).get("result") or "")
        if not armed_text.startswith("ARMED"):
            return False, (armed_text or "试拍没有返回结果")
        for _ in range(max(1, int(tries))):
            time.sleep(max(0.05, wait_s))
            read = self._exec_csharp(_CS_CAPTURE_PROBE_READ, timeout=max(30.0, self.timeout))
            text = str((read or {}).get("result") or "")
            verdict = text.split("|", 1)[0]
            if verdict.startswith("OK"):
                return True, verdict
            if verdict.startswith("ERROR"):
                return False, verdict
        return False, ("试拍后一直没有落盘（编辑器可能不在 Play：逐帧截图截的是渲染出来的"
                       "最后一帧，编辑模式下没有帧可截）")

    def record_stop(self, save_as: str | None = "run.mp4", *, keep_frames: bool = False,
                    fps: float | None = None) -> dict:
        """停止录制并合成 mp4（``save_as`` 相对路径按当前工作目录算）。

        不传 ``fps`` 就按**实测速率**合成：编辑器在 Play Mode 下给 update 回调的
        节拍本就慢于请求值（每个 MCP 调用还会占住主线程），按请求值写死会让录像
        比真实时间快放 —— 实测一次 1.7s 的用例只采到 5 帧，写 6fps 就成了 0.8s。

        **不抛异常**：录像只是存证，ffmpeg 缺失/帧目录在另一台机器上都不该把一条
        已经跑出结论的用例改判成失败。失败信息在返回值的 ``error`` 里，prelude
        会把它打进入运行输出。编辑器侧自己熔断停掉的（连续截图失败）原因放在
        ``note`` 里 —— 不然"录像只有 3 帧"看起来像丢帧，其实是根本截不到。
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
        # 平台兜底收尾时（runner 被超时杀掉，见 unity_service._salvage_recording）
        # 拿不到 start 时间：这时按请求 fps 合成，别用"帧数 / 0.2s"算出个荒唐的速率。
        started = info.get("started")
        elapsed = (stopped_at - float(started)) if started else 0.0
        measured = (len(frames) / elapsed) if elapsed > 0.5 else 0.0
        fps = float(fps) if fps else (measured if measured >= 0.2 else float(info.get("fps") or DEFAULT_RECORD_FPS))
        result_out: dict = {"ok": True, "frames": len(frames), "dir": str(folder),
                            "tries": int(result.get("tries") or 0),
                            "fps": round(fps, 2),
                            "duration_s": round(len(frames) / max(0.2, fps), 1)}
        if result.get("reason"):
            result_out["note"] = str(result["reason"])
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
    def recording_scope(self, save_as: str = "run.mp4", *, fps: float = DEFAULT_RECORD_FPS):
        """``with u.recording_scope("login.mp4"):`` —— 出来的录像必定收尾。"""
        self.record_start(fps=fps)
        try:
            yield self
        finally:
            self.record_stop(save_as, fps=fps)

    # ---- 拖拽 / 按键（录制回放要用；手写用例同样可用）----------------------
    def drag(self, from_target: str, to_target: str, steps: int = 12) -> dict:
        """把 ``from_target`` 拖到 ``to_target``（完整指针序列，见 cs_drag）。

        实测取舍：编辑器里合成不了真实指针，走 ``ExecuteEvents`` 直发拖拽事件链——
        对实现 ``IDragHandler``/``IDropHandler`` 的控件通用；个别自绘控件若只认
        真实输入，改用例（用 ``exec_csharp`` 调它的业务方法）。
        """
        out = self._exec_csharp(cs_drag(from_target, to_target, steps))
        if not out.get("success"):
            raise UnityBridgeError(f"拖拽失败 {from_target} → {to_target}: {out.get('error')}")
        return out.get("result") or {}

    def key(self, key: str) -> dict:
        """按一次键（**尽力而为**：先事件系统 Esc/Enter，再输入系统合成）。

        实测已知：新版 Input System 的合成对游戏的 InputAction 常不生效
        （技能文档记过 Esc 关面板失败的案例）。返回体里 ``verified=false`` ——
        调用方看到 ``via_events=false`` 且 ``via_input=false`` 时就是完全没送到。
        """
        out = self._exec_csharp(cs_key(key))
        if not out.get("success"):
            raise UnityBridgeError(f"按键失败 {key}: {out.get('error')}")
        return out.get("result") or {}

    # ---- 手动录制（玩家自己点，平台录成用例）------------------------------
    def record_ui_start(self, *, name: str = "", max_seconds: int = 3600,
                        max_events: int = 5000) -> dict:
        """安装 UI 录制器（编辑器帧回调；不改工程、不建脚本文件）。

        幂等：钩子还活着时不会重复挂（防双份事件）。进 Play Mode 的域重载会
        清掉钩子，平台侧靠 ``record_ui_status`` 的心跳发现并重挂。
        """
        subdir = name or time.strftime("uirec_%Y%m%d_%H%M%S")
        out = self._raise(self._exec_csharp(
            cs_record_ui_start(subdir, max_seconds=max_seconds, max_events=max_events),
            timeout=max(30.0, self.timeout)))
        result = out.get("result") if isinstance(out.get("result"), dict) else {}
        return result

    def record_ui_status(self) -> dict:
        """录制状态：开没开 / 已录几条 / 心跳多旧（平台据此判断要不要重挂）。"""
        out = self._exec_csharp(cs_record_ui_status(), timeout=max(30.0, self.timeout))
        result = out.get("result") if isinstance(out.get("result"), dict) else {}
        return result

    def record_ui_stop(self) -> dict:
        """停止录制（置标志让帧回调自己退订；事件文件保留在 Unity 临时目录）。"""
        out = self._exec_csharp(cs_record_ui_stop(), timeout=max(30.0, self.timeout))
        result = out.get("result") if isinstance(out.get("result"), dict) else {}
        return result

    def record_ui_fetch(self, since: int = 0, cap: int = 300) -> dict:
        """分片取录制事件（MCP 响应有上限，长录制必须分片）。"""
        out = self._exec_csharp(cs_record_ui_fetch(since, cap), timeout=max(30.0, self.timeout))
        result = out.get("result") if isinstance(out.get("result"), dict) else {}
        return result

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
                   "drag", "key")


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
    "cs_drag", "cs_find_text", "cs_key", "cs_present", "cs_record_start",
    "cs_record_ui_fetch", "cs_record_ui_start", "cs_record_ui_status", "cs_record_ui_stop",
    "cs_record_stop", "cs_text", "cs_tree", "cs_set_text",
    "drag", "editor_action", "exec_csharp", "find_by_text",
    "find_objects", "hierarchy", "key", "object_info",
    "record_ui_fetch", "record_ui_start", "record_ui_status", "record_ui_stop",
    "run_tests", "screenshot", "set_text", "status", "stitch_video", "tools",
    "unity_on_cached_client", "unwrap",
    "wait_for",
]
