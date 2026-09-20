"""Unity 桥的协议与行为契约（services/unity_bridge.py）。

不需要真的 Unity：写一个**假 MCP 服务器**（标准 streamable HTTP：initialize /
tools/list / tools/call / resources/read，含 Mcp-Session-Id 与 SSE 两种响应），
用它验证三件事：

1. 协议层：握手、会话 id 复用、SSE 解析、会话过期后重建、绕过系统代理；
2. 适配层：按服务器广播的 inputSchema 改名/丢参数 —— 这是"换一台 Unity MCP
   服务器也能用"的关键，认不出的参数不能让请求整条失败；
3. 用例脚本层：`Unity` 客户端 + `run_unity_script` 的 prelude 与截图收集。

假服务器故意用**另一套工具名/参数名**（coplay 方言 + 少声明一个参数），所以这里
过的测试等价于"平台不依赖我们调研时看到的那份工具清单"。
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml  # noqa: F401  (与其它测试保持一致的环境依赖)

from src.app.core.config import settings
from src.app.services import unity_bridge, unity_service


def _run(coro):
    """同步跑协程：这些用例是同步风格，不依赖 asyncio 插件的模式开关。"""
    return asyncio.run(coro)


TINY_PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()
TINY_PNG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 32   # 够用的"一个 jpg 字节流"

# 假服务器广播的工具清单：名字/参数都按 CoplayDev 方言，find_gameobjects 刻意
# **不声明** find_inactive（真实情况里各服务器参数并不一致）。
_TOOLS = [
    {"name": "manage_editor", "description": "editor control",
     "inputSchema": {"type": "object", "properties": {"action": {"type": "string"}}}},
    # 场景：复位要"打开起跑场景"，所以服务端得有一套真场景元信息（实测 shape 见 _call）
    {"name": "manage_scene", "description": "scene CRUD",
     "inputSchema": {"type": "object", "required": ["action"], "properties": {
         "action": {"type": "string",
                    "enum": ["create", "load", "save", "get_hierarchy", "get_active",
                             "get_build_settings", "close_scene", "set_active_scene",
                             "get_loaded_scenes", "move_to_scene", "validate"]},
         "path": {"type": "string"}, "name": {"type": "string"}}}},
    # 下面这几个 schema 是照着真实服务器（mcp-for-unity-server 3.4.7）抄的：
    # 只接受 search_term + search_method，分页叫 page_size，只返回 instance id。
    {"name": "find_gameobjects", "description": "find objects",
     "inputSchema": {"type": "object", "required": ["search_term"], "properties": {
         "search_term": {"type": "string"},
         "search_method": {"type": "string", "enum": ["by_name", "by_tag", "by_layer",
                                                      "by_component", "by_path", "by_id"]},
         "include_inactive": {"type": "boolean"},
         "page_size": {"type": "integer"}, "cursor": {"type": "string"}}}},
    {"name": "manage_components", "description": "component data (写：add/remove/set_property)",
     "inputSchema": {"type": "object", "required": ["action", "target", "component_type"],
                     "properties": {
         "action": {"type": "string", "enum": ["add", "remove", "set_property"]},
         "target": {"type": "string"}, "component_type": {"type": "string"}}}},
    {"name": "read_console", "description": "console",
     "inputSchema": {"type": "object", "properties": {
         "action": {"type": "string"}, "filter_text": {"type": "string"},
         "types": {"type": "array"}, "count": {"type": "string"},
         "page_size": {"type": "integer"}}}},
    {"name": "manage_camera", "description": "screenshot",
     "inputSchema": {"type": "object", "required": ["action"], "properties": {
         "action": {"type": "string"}, "capture_source": {"type": "string"},
         "include_image": {"type": "boolean"}, "max_resolution": {"type": "integer"}}}},
    {"name": "execute_code", "description": "run C#",
     "inputSchema": {"type": "object", "properties": {
         "action": {"type": "string"}, "code": {"type": "string"}}}},
    {"name": "manage_tools", "description": "tool groups",
     "inputSchema": {"type": "object", "required": ["action"], "properties": {
         "action": {"type": "string",
                    "enum": ["list_groups", "activate", "deactivate", "sync", "reset"]},
         "group": {"type": "string"}}}},
    {"name": "run_tests", "description": "run UTF tests",
     "inputSchema": {"type": "object", "properties": {
         "mode": {"type": "string"}, "test_filter": {"type": "string"}}}},
    {"name": "get_test_job", "description": "poll tests",
     "inputSchema": {"type": "object", "properties": {"job_id": {"type": "string"}}}},
    {"name": "always_fails", "description": "returns isError",
     "inputSchema": {"type": "object", "properties": {}}},
]


def _text(payload) -> dict:
    body = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return {"content": [{"type": "text", "text": body}]}


class FakeUnityMcp:
    """一个够用的 MCP 服务器：只为平台真正会发的请求负责。"""

    def __init__(self, *, sse: bool = False, expire_session_once: bool = False,
                 gated: bool = False, only_ids: bool = False,
                 editor_down: bool = False, payload_failure: bool = False,
                 sse_multievent: bool = False, expire_method: str = "tools/call",
                 no_own_text: bool = False, mask_value_junk: bool = False) -> None:
        self.sse = sse
        self.expire_session_once = expire_session_once
        self.expire_method = expire_method   # 哪一类请求撞上"会话过期"
        self.no_own_text = no_own_text       # 对象自己不带 text（uGUI 按钮）
        # 组件里带数字型 "value"（GraphicRaycaster 的 LayerMask 就是 {"value": 1023799}）：
        # 实测它会把面板的"文本"污染成一串 ID（jynew 系统菜单）
        self.mask_value_junk = mask_value_junk
        self.session_dead_reads = 0          # 还有几次资源读会回"这条会话看不到 Unity"
        self.empty_instances_once = False    # 第一次读实例清单回"成功但空"
        self.name_search_blind = False       # by_name 查不到（模拟运行时克隆对象）
        self.hidden_object = False           # 对象在场景里但被停用（关掉的面板）
        self.console_noise = False           # Console 里带平台自己的截图噪声行
        self.screenshot_path = ""            # ScreenCapture 那条路要落的临时文件（空=走不通）
        # Play / 场景：复位要用（stop → 打开起跑场景 → play）。playing=True 是默认
        # 现场 —— 大部分用例的起点就是"游戏已经跑着"。
        self.playing = True
        self.scene_path = "Assets/Mods/SAMPLE/Maps/GameMaps/01_moqiaoshanzhuang.unity"
        # 录像：帧目录里的 .jpg（真录像是 Unity 那边逐帧写盘，平台只读盘+合成）
        self.record_started = False
        self.record_frames: list[bytes] = [TINY_PNG_BYTES, TINY_PNG_BYTES]
        self._rec_dir: Path | None = None
        # 并发观测：同时在飞的请求数与峰值（真服务器扛不住并发）
        self.inflight = 0
        self.max_inflight = 0
        self.inflight_lock = threading.Lock()
        # gated=True 模拟真实默认：execute_code / run_tests 关在工具组里，要 manage_tools 激活
        self.gated = gated
        self.only_ids = only_ids          # find_gameobjects 只回 instance id
        self.editor_down = editor_down    # 资源回 "Unity session not available"
        self.payload_failure = payload_failure   # 工具回 200 + 正文 success=false
        # 实测：响应是 CRLF 行尾，且一次里有多个事件（先日志通知、再结果）
        self.sse_multievent = sse_multievent
        self.activated: list[str] = []
        self.resource_reads: list[str] = []
        self.session = "sess-abc"
        self.seen_headers: list[dict] = []
        self.calls: list[tuple[str, dict]] = []
        self._job_polls = 0

    def record_dir(self) -> Path:
        """帧目录：第一次问就建好，并写进 record_frames 指定的几帧。"""
        if self._rec_dir is None:
            self._rec_dir = Path(tempfile.mkdtemp(prefix="fake-unity-rec-"))
            for i, blob in enumerate(self.record_frames):
                (self._rec_dir / f"f_{i:05d}.jpg").write_bytes(blob)
        return self._rec_dir

    def handle(self, method: str, params: dict) -> dict:
        if method == "initialize":            return {"protocolVersion": "2025-06-18", "capabilities": {},
                    "serverInfo": {"name": "mcp-for-unity", "version": "10.2.0"}}
        if method == "tools/list":
            extra = [t for t in _TOOLS if t["name"] in ("execute_code", "run_tests", "get_test_job")]
            return {"tools": _TOOLS if not self.gated else [t for t in _TOOLS if t not in extra]}
        if method == "resources/read":
            uri = params.get("uri", "")
            self.resource_reads.append(uri)
            if self.session_dead_reads > 0 and ("instances" in uri or "editor/state" in uri):
                self.session_dead_reads -= 1
                return {"contents": [{"uri": uri, "text": json.dumps(
                    {"success": False, "error": "Unity session not available",
                     "data": {"reason": "no_unity_session"}})}]}
            if self.editor_down and "editor/state" in uri:
                return {"contents": [{"uri": uri, "text": json.dumps(
                    {"success": False, "error": "Unity session not available",
                     "data": {"reason": "no_unity_session"}})}]}
            if "/components" in uri:
                # no_own_text=True：模拟 uGUI 按钮 —— 自己不带文字，标签在子对象上
                comps = ([{"type": "Button", "interactable": True}] if self.no_own_text
                         else [{"type": "Text", "text": "背包"},
                               {"type": "Button", "interactable": True}])
                if self.mask_value_junk:
                    # 数字型 "value"：LayerMask 序列化就长这样（见 FakeUnityMcp 的注释）
                    comps = [{"type": "GraphicRaycaster",
                              "blockingMask": {"value": 1023799}}]
                return {"contents": [{"uri": uri, "text": json.dumps(
                    {"success": True, "data": {"instance_id": 12345, "components": comps}})}]}
            if "/gameobject/" in uri:
                return {"contents": [{"uri": uri, "text": json.dumps(
                    {"success": True, "data": {"instance_id": 12345, "name": "BagWindow",
                                               "path": "UI/BagWindow", "active": True,
                                               "activeInHierarchy": not self.hidden_object}})}]}
            if "instances" in uri:
                if getattr(self, "empty_instances_once", False):
                    self.empty_instances_once = False
                    return {"contents": [{"uri": uri, "text": json.dumps(
                        {"success": True, "instance_count": 0, "instances": []})}]}
                if self.editor_down:
                    return {"contents": [{"uri": uri, "text": json.dumps(
                        {"success": True, "instance_count": 0, "instances": []})}]}
                return {"contents": [{"uri": uri, "text": json.dumps(
                    {"success": True, "instance_count": 1, "instances": [
                        {"id": "unity-smoke@abc", "name": "unity-smoke",
                         "unity_version": "2022.3.61f1"}]})}]}
            # 实测 shape：schema unity-mcp/editor_state@2 —— play_mode 里是蛇形键
            return {"contents": [{"uri": uri, "text": json.dumps(
                {"success": True, "message": "Retrieved editor state.",
                 "data": {"schema_version": "unity-mcp/editor_state@2",
                          "unity": {"unity_version": "2022.3.61f1"},
                          "editor": {"is_focused": False,
                                     "play_mode": {"is_playing": self.playing and not self.editor_down,
                                                   "is_paused": False,
                                                   "is_changing": False}},
                          "activity": {"phase": "idle"}}})}]}
        if method == "tools/call":
            name = params.get("name", "")
            args = params.get("arguments") or {}
            self.calls.append((name, args))
            self._enter_inflight()
            try:
                time.sleep(0.02)      # 拉宽窗口：真并发一定会被逮到
                return self._call(name, args)
            finally:
                self._exit_inflight()
        raise AssertionError(f"假服务器没实现 {method}")

    # ---- 并发观测 ---------------------------------------------------------
    # 真服务器（mcp-for-unity）一次只服务一条请求：并发打过去，它把第一条回完，
    # 其余的永远不回 —— 客户端卡在读响应体上，界面上那张工具卡片一直转圈。
    # 所以客户端必须串行化（见 McpClient._gate），这里把"同时在飞几条"记下来。
    def _enter_inflight(self) -> None:
        with self.inflight_lock:
            self.inflight += 1
            self.max_inflight = max(self.max_inflight, self.inflight)

    def _exit_inflight(self) -> None:
        with self.inflight_lock:
            self.inflight -= 1

    def _call(self, name: str, args: dict) -> dict:
        if self.session_dead_reads > 0:
            # 会话看不到 Unity 时，工具调用同样失败（真实行为：一整条会话都废）
            return {"content": [{"type": "text", "text": "Unity session not available"}],
                    "isError": True}
        if name == "manage_editor":
            if self.editor_down:   # Unity 没连上时，工具调用同样失败（实测行为）
                return {"content": [{"type": "text", "text": "Unity session not available"}],
                        "isError": True}
            action = args.get("action")
            if action == "get_state":
                return _text({"isPlaying": self.playing, "isPaused": False})
            if action == "play":
                self.playing = True
            elif action == "stop":
                self.playing = False
            return _text({"success": True, "state": action})
        if name == "manage_scene":
            # 实测 shape：{"success":true,"message":…,"data":{name,path,buildIndex,isDirty}}
            if args.get("action") == "get_active":
                return _text({"success": True, "message": "Retrieved active scene information.",
                              "data": {"name": Path(self.scene_path).stem,
                                       "path": self.scene_path, "buildIndex": 4,
                                       "isDirty": False, "isLoaded": True}})
            if args.get("action") == "load":
                if self.playing:   # 真 Unity 不会在 Play 中开场景（会拦下来）
                    return _text({"success": False,
                                  "error": "Cannot open scene while in Play Mode"})
                self.scene_path = args.get("path") or self.scene_path
                return _text({"success": True, "message": "Scene loaded."})
            return _text({"success": True, "data": {}})
        if name == "find_gameobjects":
            if self.payload_failure:   # 实测：Unity 没连上时它就是这么回的
                return _text({"success": False, "error": "Unity session not available",
                              "data": {"reason": "no_unity_session"}})
            if getattr(self, "name_search_blind", False) and args.get("search_method") == "by_name":
                # 实测（jynew）：运行时克隆出来的对象，by_name 一个都查不到
                return _text({"success": True, "message": "Found GameObjects",
                              "data": {"instanceIDs": [], "totalCount": 0, "echo_args": args}})
            # 实测返回形状：{"success":true,"data":{"instanceIDs":[12345], ...}}
            return _text({"success": True, "message": "Found GameObjects",
                          "data": {"instanceIDs": [12345], "pageSize": 50,
                                   "totalCount": 1, "echo_args": args}})
        if name == "manage_components":
            if self.mask_value_junk:
                return _text({"components": [
                    {"type": "CanvasScaler", "referenceResolution": {"value": 1024}},
                    {"type": "GraphicRaycaster",
                     "blockingMask": {"value": 1023799}}]})
            return _text({"components": [{"type": "Text", "text": "背包"}]})
        if name == "manage_tools":
            action = args.get("action")
            if action == "list_groups":
                groups = [{"name": "core", "enabled": True,
                           "tools": ["find_gameobjects", "manage_editor"]},
                          {"name": "scripting_ext", "enabled": False, "tools": ["execute_code"]},
                          {"name": "testing", "enabled": False, "tools": ["run_tests", "get_test_job"]}]
                return _text({"success": True, "data": {"groups": groups}})
            if action == "activate":
                self.activated.append(args.get("group", ""))
                self.gated = False
                return _text({"success": True, "data": {"group": args.get("group")}})
            return _text({"success": True, "data": {}})
        if name == "read_console":
            # 实测 shape：条目嵌在 data.items 里（不是顶层的 logs），types 必须是 list
            items = ["NullReferenceException: Object reference not set"]
            if self.console_noise:
                # 平台自己截图/录像留下的报错（进 Play 头几帧没有"上一帧"可截）
                items = ["CaptureScreenshotAsTexture() failed to generate texture! "
                         "Was method called before the 'end of frame' state was reached?"] + items
            return _text({"success": True, "message": "Retrieved 1 log entries.",
                          "data": {"cursor": 0, "pageSize": 50, "nextCursor": None,
                                   "truncated": False, "items": items}})
        if name == "manage_camera":
            return {"content": [{"type": "text", "text": "captured"},
                                {"type": "image", "data": TINY_PNG, "mimeType": "image/png"}]}
        if name == "execute_code":
            # 实测契约：代码是方法体，return 的值经 data.result 回来
            code = args.get("code") or ""
            # 录像：start 建帧目录（真写几个 jpg），stop 回目录与帧数。
            # 必须排在截图分支之前 —— 两段代码里都有 CaptureScreenshotAsTexture。
            if unity_bridge._REC_DIR_KEY in code and "EditorApplication.update +=" in code:
                self.record_started = True
                return _text({"success": True, "data": {"result": json.dumps(
                    {"ok": True, "dir": str(self.record_dir()), "gap": 0.1667}),
                    "compiler": "codedom"}})
            if unity_bridge._REC_DIR_KEY in code and "SetBool" in code:
                folder = self.record_dir()
                frames = sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []
                return _text({"success": True, "data": {"result": json.dumps(
                    {"ok": True, "dir": str(folder), "frames": len(frames)}),
                    "compiler": "codedom"}})
            if "CaptureScreenshotAsTexture" in code and self.screenshot_path:
                return _text({"success": True, "data": {"result": self.screenshot_path + "|1386x788",
                                                        "compiler": "codedom"}})
            if "probe-only" in code:  # cs_present 探测片段：假服务器只认识 BagWindow
                hit = "BagWindow" in code
                return _text({"success": True, "data": {"result": json.dumps(
                    {"ok": hit, "name": "BagWindow", "path": "UI/BagWindow", "active": True}
                    if hit else {"ok": False, "error": "object not found: probe"}), "compiler": "codedom"}})
            if "findtext-only" in code:   # 按可见文本搜（cs_find_text）
                needle = code.split('__needle = "')[1].split('"')[0]
                # 字段顺序与片段一致：path \t active \t 可点祖先 \t 文本
                pool = [("背包", "UI/Bag/BagButton/Text", "1",
                         "UI/Bag/BagButton", " 背包"),
                        ("关 闭", "UI/Bag/CloseText", "0", "UI/Bag/CloseBtn", " 关 闭")]
                hits = [h for h in pool if needle and needle in h[0]]
                lines = "\n".join("\t".join(h[1:]) for h in hits)
                return _text({"success": True, "data": {"result": json.dumps(
                    {"ok": True, "scanned": 1831, "hits": len(hits),
                     "lines": lines})}})
            if "tree-only" in code:       # 场景层级（cs_tree）
                root = code.split('__rootWant = "')[1].split('"')[0]
                rows = [("MainCanvas", "1", "Canvas,Jyx2_UIManager", ""),
                        ("MainCanvas/NormalUI/BagUIPanel(Clone)", "0", "BagUIPanel", ""),
                        ("MainCanvas/MainUI/MainUIPanel(Clone)", "1", "MainUIPanel", "")]
                if root:
                    rows = [r for r in rows if r[0].startswith(root)]
                    if not rows:
                        return _text({"success": True, "data": {"result": json.dumps(
                            {"ok": False, "error": f"object not found: {root}"})}})
                lines = "\n".join("\t".join(r) for r in rows)
                return _text({"success": True, "data": {"result": json.dumps(
                    {"ok": True, "nodes": len(rows), "truncated": False,
                     "lines": lines})}})
            if "parts" in code:      # cs_text 片段：子孙文本
                return _text({"success": True, "data": {"result": json.dumps(
                    {"ok": True, "path": "UI/BagWindow", "parts": ["NOWA GRA"]})}})
            if "zzz-not-found" in code:
                return _text({"success": True, "data": {"result": json.dumps(
                    {"ok": False, "error": "object not found: zzz-not-found"}),
                    "compiler": "codedom"}})
            return _text({"success": True, "data": {"result": json.dumps(
                {"ok": True, "via": "Button.onClick"}), "compiler": "codedom"}})
        if name == "run_tests":
            return _text({"job_id": "job_123", "status": "started"})
        if name == "get_test_job":
            self._job_polls += 1
            return _text({"status": "completed", "passed": 3, "failed": 0})
        if name == "always_fails":
            return {"content": [{"type": "text", "text": "boom"}], "isError": True}
        raise AssertionError(f"假服务器没有工具 {name}")


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:  # 静音
        return None

    def do_POST(self) -> None:  # noqa: N802
        fake: FakeUnityMcp = self.server.fake  # type: ignore[attr-defined]
        length = int(self.headers.get("Content-Length") or 0)
        msg = json.loads(self.rfile.read(length).decode("utf-8"))
        fake.seen_headers.append({k.lower(): v for k, v in self.headers.items()})
        method = msg.get("method", "")
        if "id" not in msg:  # notification
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if fake.expire_session_once and method == fake.expire_method:
            fake.expire_session_once = False
            body = b'{"error":"session not found"}'
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        result = fake.handle(method, msg.get("params") or {})
        body = json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}).encode()
        if (fake.sse or fake.sse_multievent) and method != "initialize":
            if fake.sse_multievent:
                note = (b'data: {"jsonrpc":"2.0","method":"notifications/message",'
                        b'"params":{"level":"info","data":{"msg":"working"}}}\r\n\r\n')
                body = (b"event: message\r\n" + note + b"event: message\r\ndata: "
                        + body + b"\r\n\r\n")
            else:
                body = b"event: message\ndata: " + body + b"\n\n"
            ctype = "text/event-stream"
        else:
            ctype = "application/json"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Mcp-Session-Id", fake.session)
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(autouse=True)
def _reset_state():
    """熔断与客户端缓存是进程级的：每个用例前后都清干净，避免互相影响。"""
    unity_bridge._bridge_guard.ok()
    unity_bridge._client = None
    unity_bridge._client_key = None
    yield
    unity_bridge._bridge_guard.ok()
    unity_bridge._client = None
    unity_bridge._client_key = None


@pytest.fixture
def fake_mcp(monkeypatch, tmp_path):
    """起一个假 MCP 服务器，并把平台指向它（工作区也挪到 tmp）。"""
    def _start(**kwargs) -> FakeUnityMcp:
        fake = FakeUnityMcp(**kwargs)
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        server.fake = fake  # type: ignore[attr-defined]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        monkeypatch.setattr(settings, "unity_mcp_url",
                            f"http://127.0.0.1:{server.server_address[1]}/mcp")
        monkeypatch.setattr(settings, "unity_mcp_transport", "http")
        monkeypatch.setattr(settings, "unity_mcp_server", "auto")
        monkeypatch.setattr(settings, "workspace_dir", tmp_path)
        return fake

    return _start


# ---------------------------------------------------------------------------
# 1. 协议层
# ---------------------------------------------------------------------------

def test_status_handshake_reports_server_and_editor(fake_mcp):
    fake_mcp()
    st = _run(unity_bridge.status())

    assert st["available"] is True
    assert st["flavor"] == "coplay"        # 从 serverInfo.name 认出来
    assert st["server"]["version"] == "10.2.0"
    assert st["tool_count"] == len(_TOOLS)
    assert st["is_playing"] is True and st["unity_connected"] is True


def test_session_id_is_reused_after_initialize(fake_mcp):
    fake = fake_mcp()
    _run(unity_bridge.status())

    with_session = [h for h in fake.seen_headers if h.get("mcp-session-id") == fake.session]
    # initialize 自己没有 session（服务端在那次响应里才给），之后每个请求都要带上
    assert len(with_session) >= 2


def test_sse_responses_are_parsed(fake_mcp):
    fake_mcp(sse=True)
    st = _run(unity_bridge.status())
    assert st["available"] is True and st["tool_count"] == len(_TOOLS)


def test_sse_with_multiple_events_and_crlf_is_parsed(fake_mcp):
    """实测坑：CRLF 行尾 + 一条响应里多个事件（先日志通知，再结果）。

    按空行分块解析会把两个事件的 data 行粘成一段非法 JSON，整条响应被当成
    "无响应" —— 表现是简单调用都能过、`manage_tools activate` 这类会先打日志的
    调用永远失败。
    """
    fake_mcp(sse_multievent=True)
    st = _run(unity_bridge.status())
    assert st["available"] is True and st["tool_count"] == len(_TOOLS)
    assert _run(unity_bridge.call("manage_editor", {"action": "play"}))["success"] is True


def test_session_expiry_is_retried_once(fake_mcp):
    fake = fake_mcp(expire_session_once=True)
    out = _run(unity_bridge.find_objects(name="Bag"))

    assert out["success"] is True
    assert any(name == "find_gameobjects" for name, _ in fake.calls)


def test_resource_read_recovers_from_expired_session(fake_mcp):
    """会话过期必须对**资源读**也自愈，不只是 tools/call。

    实测踩过：平台长驻进程里 Unity 连着，就绪中心却一直报"未连接" —— 因为
    实例清单/编辑器状态走的是资源读，撞上 404 后没人重握手，被静默当成"没连"。
    """
    fake = fake_mcp(expire_session_once=True, expire_method="resources/read")
    st = _run(unity_bridge.status())

    assert st["available"] is True
    assert st["unity_connected"] is True
    assert len(st["instances"]) == 1


def test_instances_read_on_cold_client(fake_mcp):
    """冷客户端（还没握过手）上读实例清单也必须拿得到。

    资源模板是按 flavor 查的，而 flavor 要握手之后才知道；先查模板再握手会拿到
    兜底的 "generic"，模板里没有 coplay 的资源 uri，于是静默返回空列表。
    """
    fake_mcp()
    client = unity_bridge._get_client()
    assert client.flavor == "generic"          # 冷客户端：还没握手
    instances = unity_bridge._instances_sync(client)
    assert [i["name"] for i in instances] == ["unity-smoke"]


def test_system_proxy_is_bypassed(fake_mcp, monkeypatch):
    """系统代理指向死端口也必须能连通 —— 走代理会把"服务没起"伪装成 HTTP 502。"""
    fake_mcp()
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:1")
    st = _run(unity_bridge.status())
    assert st["available"] is True


def test_stdio_transport(tmp_path, monkeypatch):
    """stdio 模式：常驻一个子进程，逐行收发 JSON-RPC。"""
    server = tmp_path / "fake_stdio_mcp.py"
    server.write_text(
        "import json, sys\n"
        f"TOOLS = {json.dumps(_TOOLS)}\n"
        "for line in sys.stdin:\n"
        "    msg = json.loads(line)\n"
        "    if 'id' not in msg: continue\n"
        "    m, p = msg.get('method'), msg.get('params') or {}\n"
        "    if m == 'initialize':\n"
        "        r = {'protocolVersion': '2025-06-18', 'capabilities': {},\n"
        "             'serverInfo': {'name': 'MCP for Unity Server', 'version': 't'}}\n"
        "    elif m == 'tools/list': r = {'tools': TOOLS}\n"
        "    elif m == 'tools/call': r = {'content': [{'type': 'text', 'text': '{\"ok\": true}'}]}\n"
        "    else: r = {}\n"
        "    sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': msg['id'], 'result': r}) + '\\n')\n"
        "    sys.stdout.flush()\n",
        encoding="utf-8")

    monkeypatch.setattr(settings, "unity_mcp_transport", "stdio")
    monkeypatch.setattr(settings, "unity_mcp_command", f"{sys.executable} {server}")
    monkeypatch.setattr(settings, "unity_mcp_server", "auto")

    st = _run(unity_bridge.status())
    assert st["available"] is True and st["tool_count"] == len(_TOOLS)
    assert _run(unity_bridge.call("manage_editor", {"action": "play"}))["success"]


def test_connection_error_is_reported_not_raised(monkeypatch):
    monkeypatch.setattr(settings, "unity_mcp_url", "http://127.0.0.1:1/mcp")
    monkeypatch.setattr(settings, "unity_mcp_transport", "http")
    st = _run(unity_bridge.status())
    assert st["available"] is False
    assert "无法连接" in st["error"] or "超时" in st["error"]
    assert "unity-mcp" in st["hint"]


# ---------------------------------------------------------------------------
# 2. 适配层：工具名/参数按服务器广播的 schema 适配
# ---------------------------------------------------------------------------

def test_args_are_adapted_to_server_schema(fake_mcp):
    """平台的"四种查法"要折算成这台服务器的 search_term + search_method。"""
    fake = fake_mcp()
    _run(unity_bridge.find_objects(name="Bag", find_inactive=True, limit=5))

    name, args = [c for c in fake.calls if c[0] == "find_gameobjects"][-1]
    assert args["search_term"] == "Bag"          # 平台侧叫 name，服务器叫 search_term
    assert args["search_method"] == "by_name"    # 实测：查询维度只能靠这个枚举表达
    assert args["page_size"] == 5                # 实测：分页叫 page_size，不叫 limit
    assert "limit" not in args and "name" not in args
    # 刻意**不**传 include_inactive：实测这个 flag 会让查询整个返回空（见下条用例）
    assert "include_inactive" not in args


def test_component_search_uses_by_component_method(fake_mcp):
    fake = fake_mcp()
    _run(unity_bridge.find_objects(component="Button", limit=20))
    _name, args = [c for c in fake.calls if c[0] == "find_gameobjects"][-1]
    assert args["search_method"] == "by_component" and args["search_term"] == "Button"


def test_adapt_args_drops_keys_the_server_does_not_declare():
    """服务器 schema 里没有的参数必须丢掉 —— 多传一个就整条请求失败。"""
    schema = {"properties": {"search_term": {}, "page_size": {}}}
    assert unity_bridge._adapt_args(
        {"name": "Bag", "path": "", "limit": 5, "unknown_thing": 1}, schema
    ) == {"search_term": "Bag", "page_size": 5}
    # 没有声明 properties（自由格式）时原样透传，宁可让服务器自己报错
    assert unity_bridge._adapt_args({"name": "Bag", "limit": 5}, {}) == {"name": "Bag", "limit": 5}


def test_find_objects_enriches_instance_ids_from_resources(fake_mcp):
    """实测该服务器只回 instance id：要顺手按 id 读资源，模型才拿得到可用的东西。"""
    fake = fake_mcp(only_ids=True)
    out = _run(unity_bridge.find_objects(name="Bag"))

    assert out["success"] is True
    assert out["objects"] == [{"id": 12345, "name": "BagWindow", "path": "UI/BagWindow",
                               "active": True, "activeInHierarchy": True}]
    assert any("gameobject/12345" in uri for uri in fake.resource_reads)


def test_object_info_reads_component_resource(fake_mcp):
    """读数据走资源（实测 manage_components 的 action 只接受 add/remove/set_property）。"""
    fake_mcp()
    out = _run(unity_bridge.object_info("BagWindow"))

    assert out["success"] is True and out["instance_id"] == 12345
    assert "Text" in json.dumps(out["data"], ensure_ascii=False)


def test_gated_tools_are_activated_on_demand(fake_mcp):
    """execute_code 默认关在 scripting_ext 组里 → 用到时自动激活，而不是报"没有工具"。"""
    fake = fake_mcp(gated=True)
    out = _run(unity_bridge.click("UI/Bag/Button"))

    assert fake.activated == ["scripting_ext"]
    assert out["success"] is True and out["result"]["via"] == "Button.onClick"


def test_status_reports_unity_not_connected(fake_mcp):
    """桥在线 ≠ Unity 在线：实例清单为空且状态读不到时要说清楚。"""
    fake_mcp(editor_down=True)
    st = _run(unity_bridge.status())
    assert st["available"] is True and st["unity_connected"] is False
    assert st["editor"] is None and st["instances"] == []


def test_status_reads_real_editor_state_schema(fake_mcp):
    """实测 schema：data.editor.play_mode.is_playing（蛇形、嵌在 editor 下）。

    只认 isPlaying 会把"Unity 明明连上了"判成未连接（实测踩过）。
    """
    fake_mcp()
    st = _run(unity_bridge.status())
    assert st["is_playing"] is True and st["editor"] == {"isPlaying": True, "isPaused": False}
    assert st["unity_connected"] is True
    assert st["instances"][0]["name"] == "unity-smoke"


def test_console_asks_for_all_log_types_by_default(fake_mcp):
    """实测：服务器默认只回 error/warning，Debug.Log 会被静默丢掉。"""
    fake = fake_mcp()
    _run(unity_bridge.console(filter_text="SMOKE"))
    _name, args = [c for c in fake.calls if c[0] == "read_console"][-1]
    assert args["types"] == ["all"]
    # 条数落到哪个字段取决于服务器 schema（实测真机是 page_size，文档里 count 要字符串）
    assert args.get("page_size") == 50 or args.get("count") in (50, "50")


def test_unknown_operation_names_available_tools(fake_mcp, monkeypatch):
    fake_mcp()
    monkeypatch.setattr(settings, "unity_mcp_server", "ivan")  # 强制认错方言
    out = _run(unity_bridge.run_tests("PlayMode", "Smoke"))

    # ivan 方言找不到 → 回落到 coplay 的 run_tests，而不是直接失败
    assert out["success"] is True


def test_missing_operation_reports_available_tools(monkeypatch, tmp_path):
    """服务器上一个方言的工具都没有时，错误里要带可用清单（模型据此改道）。"""
    fake = FakeUnityMcp()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.fake = fake  # type: ignore[attr-defined]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(settings, "unity_mcp_url",
                        f"http://127.0.0.1:{server.server_address[1]}/mcp")
    monkeypatch.setattr(settings, "unity_mcp_transport", "http")
    monkeypatch.setattr(settings, "unity_mcp_server", "auto")
    monkeypatch.setattr(settings, "workspace_dir", tmp_path)

    # 把工具清单换成一个完全没有编辑器工具的服务器
    fake.handle = lambda m, p: {"tools": [{"name": "unrelated", "inputSchema": {}}]} \
        if m == "tools/list" else {"protocolVersion": "2025-06-18", "capabilities": {},
                                   "serverInfo": {"name": "some-unity-bridge", "version": "1"}}
    out = _run(unity_bridge.editor_action("play"))
    assert out["success"] is False
    assert "unity_mcp_call" in out["error"] and "unrelated" in out["error"]


def test_mcp_tools_lists_full_schemas(fake_mcp):
    fake_mcp()
    out = _run(unity_bridge.tools())
    assert out["success"] and out["count"] == len(_TOOLS)
    find = next(t for t in out["tools"] if t["name"] == "find_gameobjects")
    assert "search_term" in (find["schema"].get("properties") or {})


def test_raw_call_passes_args_untouched(fake_mcp):
    fake = fake_mcp()
    _run(unity_bridge.call("manage_editor", {"action": "play", "weird": 1}))
    _name, args = fake.calls[-1]
    assert args == {"action": "play", "weird": 1}


# ---------------------------------------------------------------------------
# 3. 结果解包与 C# 片段
# ---------------------------------------------------------------------------

def test_screenshot_saves_image_to_workspace(fake_mcp, tmp_path):
    fake_mcp()
    out = _run(unity_bridge.screenshot())
    assert out["success"] is True
    path = out["path"]
    assert path.startswith(str(tmp_path)) and path.endswith(".png")
    assert (tmp_path / "default" / "unity-auto" / "screenshots").exists()


def test_payload_level_failure_is_not_reported_as_success(fake_mcp):
    """实测坑：工具失败是 200 + 正文 {"success": false}，不是 isError。

    不认这一层的话，`click` 会返回 success=True 而正文写着 "Unity session not
    available" —— 模型会把"点了个寂寞"当成通过。
    """
    fake_mcp(payload_failure=True)
    out = _run(unity_bridge.find_objects(name="Bag"))
    assert out["success"] is False
    assert "Unity session not available" in out["error"]


def test_iserror_becomes_failure(fake_mcp):
    fake_mcp()
    out = _run(unity_bridge.call("always_fails", {}))
    assert out["success"] is False and out["error"] == "boom"


def test_csharp_return_value_is_parsed(fake_mcp):
    """实测契约：片段是方法体，`return` 的值在 data.result 里。"""
    fake_mcp()
    ok = _run(unity_bridge.click("UI/Bag/Button"))
    assert ok["success"] is True and ok["result"]["via"] == "Button.onClick"

    bad = _run(unity_bridge.click("zzz-not-found"))
    assert bad["success"] is False and "not found" in bad["error"]


def test_csharp_helpers_are_method_bodies_that_return():
    """内置片段必须是"方法体 + return"（CodeDom 编译器要求所有路径都有返回值）。

    实测踩过：不带 return 的语句序列会编译失败 —— "not all code paths return a value"。
    """
    for snippet in (unity_bridge.cs_click("A/B"),
                    unity_bridge.cs_set_text("A/B", "hi"),
                    unity_bridge.cs_describe("A/B")):
        assert "return __json;" in snippet, snippet[:120]
        # CodeDom 编译器不支持 C# 6+ 的写法
        assert "$\"" not in snippet and "?." not in snippet


def test_csharp_helpers_use_generic_apis():
    """三个内置片段必须是"对任何 Unity 工程都成立"的写法。"""
    click = unity_bridge.cs_click("A/B")
    assert "Button" in click and "ExecuteEvents" in click
    assert "FindObjectsOfType" in click and "(true)" in click   # 含未激活对象

    setter = unity_bridge.cs_set_text("A/B", "hi")
    assert 'GetProperty("text"' in setter and "CanWrite" in setter   # 反射，不依赖 TMPro

    desc = unity_bridge.cs_describe("A/B")
    assert "GetComponents" in desc and "activeInHierarchy" in desc


def test_unwrap_variants():
    assert unity_bridge.unwrap({"content": [{"type": "text", "text": '{"a": 1}'}]})["data"] == {"a": 1}
    assert unity_bridge.unwrap({"content": [{"type": "text", "text": "plain"}]})["text"] == "plain"
    structured = unity_bridge.unwrap({"content": [], "structuredContent": {"b": 2}})
    assert structured["data"] == {"b": 2}


def test_extract_code_from_fence():
    assert unity_service._extract_code("```python\nprint(1)\n```") == "print(1)\n"
    assert unity_service._extract_code("no fence") == "no fence\n"


# ---------------------------------------------------------------------------
# 4. 用例脚本侧：Unity 客户端 + 运行器
# ---------------------------------------------------------------------------

def test_script_client_operations(fake_mcp):
    fake_mcp()
    u = unity_bridge.Unity()

    assert u.is_playing() is True
    u.wait_for("BagWindow", timeout=2)           # 存在 → 直接返回
    assert u.exists("BagWindow") is True
    assert u.object_text("BagWindow") == "背包"
    u.click("UI/BagWindow/Close")
    u.expect_text("BagWindow", "背包")
    logs = u.errors()
    assert logs and "NullReferenceException" in logs[0]


def test_waiting_assertions_do_not_misreport_env_failures(fake_mcp):
    """Unity 没连上时，等待类断言要报"环境问题"，不能说成"对象未出现"。"""
    fake_mcp(payload_failure=True)
    u = unity_bridge.Unity()
    with pytest.raises(unity_bridge.UnityBridgeError) as err:
        u.expect_exists("BagWindow", timeout=1)
    assert "环境问题" in str(err.value) and "Unity session not available" in str(err.value)


def test_script_exists_falls_back_to_path_search(fake_mcp):
    """名字查不到就按路径查（服务器的 by_path 收半截路径），断言才不会假失败。"""
    fake = fake_mcp()
    u = unity_bridge.Unity()
    assert u.exists("BagWindow") is True
    assert u.exists("UI/BagWindow") is True          # 半截路径
    assert u.exists("NoSuchThing") is False
    methods = [a.get("search_method") for n, a in fake.calls if n == "find_gameobjects"]
    assert "by_path" in methods


def test_script_client_raises_on_failure(fake_mcp):
    fake_mcp()
    u = unity_bridge.Unity()
    with pytest.raises(unity_bridge.UnityBridgeError):
        u.click("zzz-not-found")
    with pytest.raises(AssertionError):
        u.expect_text("BagWindow", "不存在的文本", timeout=1)


def test_relative_screenshot_path_lands_in_shots_dir(fake_mcp, tmp_path, monkeypatch):
    """工具拿到相对路径时，文件落在 workspace 的截图目录里（智能体才找得到）。

    实测踩过（真游戏对话）：智能体调 ``unity_screenshot(save_path="00_xx.png")``，
    文件落进了**平台进程的 cwd**（仓库根），它随后在 workspace 里 glob 找不到，
    白折腾一轮才换写法。
    """
    fake = fake_mcp()
    src = tmp_path / "src.png"
    src.write_bytes(base64.b64decode(TINY_PNG))
    fake.screenshot_path = str(src)
    monkeypatch.setattr(settings, "workspace_dir", tmp_path)

    out = _run(unity_bridge.screenshot("00_current_state.png"))

    assert out["success"] is True
    saved = Path(out["path"])
    assert saved.is_absolute() and saved.is_file()
    assert saved.parent == tmp_path / "default" / "unity-auto" / "screenshots"


def test_parallel_calls_are_serialized(fake_mcp):
    """并发调用必须**串行**进服务器 —— 否则请求会石沉大海。

    实测事故（2026-09-19，真游戏 + 真服务器）：模型一步里发了 3 个工具调用
    （write_todos + 两个 unity_find_objects），平台用 ``asyncio.to_thread`` 各起一条
    线程，两条请求同时打到 mcp-for-unity。它只回第一条，其余的永远不回 ——
    faulthandler 抓到的栈停在 ``http/client.py::_read_next_chunk_size``（读响应体），
    界面上那张工具卡片就一直"执行中"，整轮对话卡了 5 分钟才断。
    """
    fake = fake_mcp()

    async def all_at_once():
        return await asyncio.gather(*[
            unity_bridge.find_objects(name="BagWindow") for _ in range(4)])

    results = _run(all_at_once())

    assert all(r.get("success") for r in results)
    assert all(json.dumps(r.get("objects"), ensure_ascii=False).find("BagWindow") >= 0
               for r in results)
    assert fake.max_inflight == 1, f"客户端没有串行化（峰值并发 {fake.max_inflight}）"


def test_hierarchy_lists_tree_with_text(fake_mcp):
    """层级树：一次拿到路径/可见性/组件/文本 —— 探索第一步不该靠猜名字。"""
    fake_mcp()
    out = _run(unity_bridge.hierarchy(depth=2))

    assert out["success"] is True and out["nodes"] == 3
    assert [r[0] for r in out["rows"]] == [
        "MainCanvas", "MainCanvas/NormalUI/BagUIPanel(Clone)",
        "MainCanvas/MainUI/MainUIPanel(Clone)"]
    assert "[显示]" in out["text"] and "[隐藏]" in out["text"]
    # 给了 root 就只回那棵子树；找不到要报"对象不存在"，不是空表
    sub = _run(unity_bridge.hierarchy(root="MainCanvas/NormalUI"))
    assert [r[0] for r in sub["rows"]] == ["MainCanvas/NormalUI/BagUIPanel(Clone)"]
    missing = _run(unity_bridge.hierarchy(root="NoSuchRoot"))
    assert missing["success"] is False and "object not found" in missing["error"]


def test_find_by_text_returns_clickable_ancestor(fake_mcp):
    """按界面上的字找对象：中文游戏里这是入口（对象名是拼音，文字才是线索）。"""
    fake_mcp()
    out = _run(unity_bridge.find_by_text("背包"))

    assert out["success"] is True and out["hits"] == 1
    path, active, click, text = out["rows"][0]
    assert path == "UI/Bag/BagButton/Text"        # 写着这句话的对象
    assert click == "UI/Bag/BagButton"            # 往上最近的可点祖先（直接拿去点）
    assert active == "1" and "背包" in text
    assert "背包" in out["text"]
    # 没有点击处理器时"可点祖先"留空，而不是瞎猜一个
    closed = _run(unity_bridge.find_by_text("关 闭"))
    assert closed["rows"][0][1] == "0" and closed["rows"][0][2] == "UI/Bag/CloseBtn"


def test_subtree_text_reads_panel_content(fake_mcp):
    """面板内容用整棵子树的文本（容器自己身上挂着的是无关的 id）。"""
    fake_mcp()
    out = _run(unity_bridge.subtree_text("BagUIPanel(Clone)"))
    assert out["success"] is True and out["text"] == "NOWA GRA"


def test_script_client_play_waits_for_play_mode(fake_mcp):
    fake = fake_mcp()
    u = unity_bridge.Unity()
    u.play(wait_s=5)
    assert ("manage_editor", {"action": "play"}) in fake.calls


def test_step_trace_records_failure(fake_mcp, tmp_path, monkeypatch):
    """轨迹记的是「做了什么 + 成没成」：断言失败那一步要带错误信息落盘。"""
    fake_mcp()
    trace = tmp_path / "steps.jsonl"
    monkeypatch.setenv(unity_bridge._TRACE_FILE_ENV, str(trace))
    u = unity_bridge.Unity()
    u.click("UI/BagWindow/Close")
    with pytest.raises(AssertionError):
        u.expect_text("BagWindow", "不存在的文本", timeout=1)

    steps = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
    assert [s["action"] for s in steps] == ["click", "expect_text"]
    assert steps[0]["ok"] is True and steps[1]["ok"] is False
    assert "不存在的文本" in steps[1]["error"]
    assert steps[1]["target"] == "BagWindow" and "t" in steps[1] and "ms" in steps[1]


def test_screenshot_without_name_lands_in_run_dir(fake_mcp, tmp_path, monkeypatch):
    """不带文件名的截图要落进本次运行目录（否则前端按"这次执行"取产物会少一张）。"""
    fake = fake_mcp()
    src = tmp_path / "src.png"
    src.write_bytes(base64.b64decode(TINY_PNG))
    fake.screenshot_path = str(src)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    monkeypatch.setenv(unity_bridge._SHOT_DIR_ENV, str(run_dir))

    path = unity_bridge.Unity().screenshot()

    assert Path(path).parent == run_dir and Path(path).is_file()


def test_record_start_stop_stitches_video(fake_mcp, tmp_path, monkeypatch):
    """录制：start 拿帧目录、stop 合成 mp4 并清掉帧（不留垃圾）。"""
    if not _has_ffmpeg():
        pytest.skip("没装 ffmpeg")
    fake = fake_mcp()
    fake.record_frames = _real_jpegs(4)
    monkeypatch.chdir(tmp_path)
    u = unity_bridge.Unity()
    info = u.record_start(fps=4)
    assert info["dir"] and u.recording is True

    out = u.record_stop("run.mp4", fps=4)

    assert out["ok"] is True and out["frames"] == 4
    assert Path(out["path"]).is_file() and Path(out["path"]).stat().st_size > 0
    assert not Path(out["dir"]).exists(), "合成完应当清掉帧目录"
    assert u.recording is False


def test_record_stop_without_local_frames_is_not_fatal(fake_mcp, tmp_path, monkeypatch):
    """帧不在本机 / 没采到帧：录像失败不能把用例变成失败（只回报原因）。"""
    fake = fake_mcp()
    monkeypatch.chdir(tmp_path)
    fake._rec_dir = tmp_path / "gone"          # 指向一个不存在的目录
    u = unity_bridge.Unity()
    u.record_start()
    out = u.record_stop("run.mp4")
    assert out["ok"] is False and "帧目录不在本机" in out["error"]
    assert not (tmp_path / "run.mp4").exists()


def test_run_unity_script_collects_screenshots(fake_mcp, tmp_path, monkeypatch):
    """跑一份真脚本：prelude 注入 u，脚本自己截图 → 记录里能看到截图路径。"""
    fake_mcp()
    content = (
        "u.expect_exists('BagWindow', timeout=5)\n"
        "p = u.screenshot('bag.png')\n"
        "print('PASS: 截图落在', p)\n"
    )
    result = _run(unity_service.run_unity_script("sid", "用例", content))

    assert result["status"] == "passed" and result["exit_code"] == 0
    assert "PASS: 截图落在" in result["output"]
    shots = json.loads(result["screenshots"])
    names = [Path(p).name for p in shots]
    # 用例自己截的图 + 平台自动留的轨迹（录像也在这个目录里，见下面那条用例）
    assert {"bag.png", "steps.jsonl"} <= set(names)
    assert result["script_file"].endswith("case.py")


def test_run_unity_script_traces_steps_without_case_code(fake_mcp, tmp_path, monkeypatch):
    """步骤轨迹不用用例作者操心：prelude 里开的，跑完就有"走到哪一步"。"""
    monkeypatch.setattr(settings, "workspace_dir", tmp_path)
    fake_mcp()
    content = (
        "u.expect_exists('BagWindow', timeout=5)\n"
        "u.click('UI/BagWindow/Close')\n"
        "print('PASS: 点了关闭')\n"
    )
    result = _run(unity_service.run_unity_script("sid", "用例", content))

    assert result["status"] == "passed"
    steps_file = next(Path(p) for p in json.loads(result["screenshots"])
                      if p.endswith("steps.jsonl"))
    steps = [json.loads(line) for line in steps_file.read_text(encoding="utf-8").splitlines()]
    names = [s["action"] for s in steps]
    assert names == ["expect_exists", "click"]
    assert all(s["ok"] for s in steps)
    assert steps[1]["target"] == "UI/BagWindow/Close"


def test_failed_case_leaves_evidence(fake_mcp, tmp_path, monkeypatch):
    """用例挂在断言上也要留下现场：失败截图 + 上下文（哪一步挂的、控制台报了什么）。

    这是 Playwright 的 retain-on-failure 等价物 —— 用例自己没写截图代码，
    证据也不能丢。
    """
    monkeypatch.setattr(settings, "workspace_dir", tmp_path)
    shot = tmp_path / "screen.png"
    shot.write_bytes(base64.b64decode(TINY_PNG))
    fake = fake_mcp()
    fake.screenshot_path = str(shot)
    content = (
        "u.expect_exists('BagWindow', timeout=5)\n"
        "u.expect_text('BagWindow', '不存在的文本', timeout=1)\n"
    )
    result = _run(unity_service.run_unity_script("sid", "用例", content))

    assert result["status"] == "failed" and result["exit_code"] == 1
    names = [Path(p).name for p in json.loads(result["screenshots"])]
    assert "failure.png" in names and "failure.txt" in names and "steps.jsonl" in names
    assert "失败现场 ->" in result["output"]
    context = next(Path(p) for p in json.loads(result["screenshots"])
                   if p.endswith("failure.txt")).read_text(encoding="utf-8")
    assert "expect_text" in context                       # 挂在哪一步
    assert "NullReferenceException" in context            # 控制台摘录
    assert "走到哪一步" in context


def test_recording_runs_by_default_and_stitches_video(fake_mcp, tmp_path, monkeypatch):
    """默认开录：跑完把帧合成 mp4 放进运行目录（产物清单里能看到）。"""
    monkeypatch.setattr(settings, "workspace_dir", tmp_path)
    fake = fake_mcp()
    if _has_ffmpeg():
        fake.record_frames = _real_jpegs(3)
    result = _run(unity_service.run_unity_script("sid", "用例", "print('PASS: 无操作')\n"))

    assert fake.record_started is True, "prelude 应当在用例开始前就开录"
    names = [Path(p).name for p in json.loads(result["screenshots"])]
    if _has_ffmpeg():
        assert "run.mp4" in names
    else:                     # 没装 ffmpeg 的机器：不合成，但也不能因此判失败
        assert "WARN: 录像没有合成" in result["output"]
    assert result["status"] == "passed"


def test_recording_can_be_switched_off(fake_mcp, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", tmp_path)
    monkeypatch.setenv("UNITY_RECORD", "0")
    fake = fake_mcp()
    result = _run(unity_service.run_unity_script("sid", "用例", "print('PASS: 无操作')\n"))
    assert fake.record_started is False
    assert "录像已开始" not in result["output"]


# ---------------------------------------------------------------------------
# 复位（回到用例起跑线）
# ---------------------------------------------------------------------------

def test_reset_hard_stops_then_reopens_then_plays_and_waits(fake_mcp, tmp_path,
                                                            monkeypatch):
    """硬复位：退 Play → 打开起跑场景 → 再进 Play → 等标志物，并记进步骤轨迹。

    顺序是硬要求：Play 中不能打开场景（真 Unity 会拦），所以 stop 必须在 load 之前。
    """
    monkeypatch.setenv("UNITY_TRACE_FILE", str(tmp_path / "steps.jsonl"))
    fake = fake_mcp()
    u = unity_bridge.Unity()
    out = u.reset(scene="Assets/Mods/DC/Maps/Map.unity", wait_for="BagWindow", timeout=5)

    assert out["ok"] is True and out["mode"] == "hard" and out["playing"] is True
    assert out["scene"] == "Assets/Mods/DC/Maps/Map.unity"
    order = [(n, a.get("action")) for n, a in fake.calls
             if n in ("manage_editor", "manage_scene")]
    assert order[0] == ("manage_scene", "get_active")   # 先看现在在哪个场景
    stop = order.index(("manage_editor", "stop"))
    load = order.index(("manage_scene", "load"))
    play = order.index(("manage_editor", "play"))
    assert stop < load < play, order
    assert fake.scene_path == "Assets/Mods/DC/Maps/Map.unity"
    steps = [json.loads(line) for line in
             (tmp_path / "steps.jsonl").read_text(encoding="utf-8").splitlines()]
    assert steps[-1]["action"] == "reset" and steps[-1]["ok"] is True
    # 轨迹里要能看出"回到哪儿了"（运行详情就是这么渲染的）
    assert steps[-1]["target"] == "Assets/Mods/DC/Maps/Map.unity"


def test_reset_same_scene_is_not_reopened(fake_mcp, tmp_path):
    """起跑场景与当前打开的是同一个：不重复打开。

    脏场景的保存对话框是**模态**的 —— 一弹出来 MCP 的执行线程就再也动不了，
    所以"同名不重开"不是优化，是必须。
    """
    fake = fake_mcp()
    u = unity_bridge.Unity()
    out = u.reset(scene="01_moqiaoshanzhuang")     # 只给名字也要认出来是同一个
    assert out["ok"] is True
    assert not [c for c in fake.calls
                if c[0] == "manage_scene" and c[1].get("action") == "load"]


def test_reset_soft_reloads_scene_without_leaving_play(fake_mcp, tmp_path):
    """软复位：不退出 Play，重载当前场景（快，但静态状态与常驻单例不清）。"""
    fake = fake_mcp()
    u = unity_bridge.Unity()
    out = u.reset(mode="soft", wait_for="BagWindow")

    assert out["ok"] is True and out["mode"] == "soft" and fake.playing is True
    assert not [c for c in fake.calls if c[0] == "manage_editor"]
    codes = [a.get("code", "") for n, a in fake.calls if n == "execute_code"]
    assert any("reload-scene" in c and "LoadScene" in c for c in codes)


def test_reset_soft_refuses_scene_switch(fake_mcp, tmp_path):
    """软复位换场景是不可能的（Play 里开不了场景）—— 明确报出来，别装作做完了。"""
    fake_mcp()
    u = unity_bridge.Unity()
    with pytest.raises(unity_bridge.UnityBridgeError) as err:
        u.reset(scene="Assets/Other.unity", mode="soft")
    assert "软复位不能换场景" in str(err.value)


def test_reset_rejects_unknown_mode(fake_mcp, tmp_path):
    fake_mcp()
    u = unity_bridge.Unity()
    with pytest.raises(unity_bridge.UnityBridgeError) as err:
        u.reset(mode="温柔一点")
    assert "未知复位方式" in str(err.value)


def test_absent_timeout_points_at_hidden(fake_mcp):
    """等"消失"超时、但对象其实只是被停用：报错要直接给那条改法。

    实测（jynew 系统菜单）：uGUI 面板关闭是 ``SetActive(false)`` —— 对象还在场景里，
    用 ``absent`` 等它永远等不到，而报错只说"未消失"，人就去怀疑游戏没关掉。
    """
    fake = fake_mcp()
    fake.hidden_object = True          # 对象在场景里，只是被停用
    u = unity_bridge.Unity()
    with pytest.raises(AssertionError) as err:
        u.wait_for("BagWindow", timeout=1, state="absent")
    assert 'state="hidden"' in str(err.value)


def test_hidden_timeout_points_at_absent(fake_mcp):
    """反过来：等"被隐藏"超时、对象其实还显示着 —— 提示改用 absent。"""
    fake_mcp()
    u = unity_bridge.Unity()
    with pytest.raises(AssertionError) as err:
        u.wait_for("BagWindow", timeout=1, state="hidden")
    assert 'state="absent"' in str(err.value)


def test_declared_reset_reads_module_constant():
    """用例里的 ``RESET`` 三种写法：字典 / False / 没写（写坏的不算数）。"""
    assert unity_service.declared_reset(
        'RESET = {"scene": "a.unity", "wait_for": "Hud"}\nu.click("x")\n'
    ) == (True, {"scene": "a.unity", "wait_for": "Hud"})
    assert unity_service.declared_reset("RESET = False") == (True, {})
    assert unity_service.declared_reset("RESET = True") == (True, {})
    assert unity_service.declared_reset("x = 1\n") == (False, {})
    assert unity_service.declared_reset("RESET = {\n") == (False, {})


def test_reset_plan_declared_beats_learned_and_env_can_disable(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", tmp_path)
    state = unity_service.script_dir("sid") / "start_state.json"
    state.write_text(json.dumps({"scene": "learned.unity", "wait_for": "Hud"}),
                     encoding="utf-8")

    # 没声明 → 用记住的起跑线
    assert unity_service.reset_plan("print(1)", "sid") == {"scene": "learned.unity",
                                                           "wait_for": "Hud"}
    # 声明了 → 声明优先，缺的参数（标志物）由记住的补齐
    assert unity_service.reset_plan('RESET = {"scene": "mine.unity"}', "sid") == {
        "scene": "mine.unity", "wait_for": "Hud"}
    # 明确不复位 → 不拿记住的顶上
    assert unity_service.reset_plan("RESET = False", "sid") == {}
    # 全局开关
    monkeypatch.setenv("UNITY_RESET", "0")
    assert unity_service.reset_plan("print(1)", "sid") == {}


def test_run_unity_script_resets_before_recording(fake_mcp, tmp_path, monkeypatch):
    """声明了 RESET 的用例：执行前自动复位，且**复位在开录之前**（录像里没有冷启动）。

    这是"用例之间互不污染"的落地：作者只在文件头写一行 RESET，平台负责每次站回起点。
    """
    fake = fake_mcp()
    content = (
        'RESET = {"scene": "Assets/Mods/DC/Maps/Map.unity", "wait_for": "BagWindow"}\n'
        "u.screenshot('01_hud.png')\n"
        "print('PASS: 到位')\n"
    )
    result = _run(unity_service.run_unity_script("sid", "用例", content))

    assert result["status"] == "passed" and result["exit_code"] == 0
    assert "复位 -> 起跑线" in result["output"]
    order = [(n, a.get("action") or "") for n, a in fake.calls]
    stop = order.index(("manage_editor", "stop"))
    load = order.index(("manage_scene", "load"))
    play = order.index(("manage_editor", "play"))
    record = next(i for i, (n, a) in enumerate(fake.calls)
                  if n == "execute_code" and "EditorApplication.update +=" in (a.get("code") or ""))
    assert stop < load < play < record, order[:8]


def test_start_line_learned_only_after_a_passing_run(fake_mcp, tmp_path, monkeypatch):
    """跑通一次才认这条起跑线：挂掉的那次开场可能只是"半路"，记下来会把下一轮带偏。

    记住的不只是场景，还有轨迹里第一个成功的 `wait_for` —— 它就是这条用例真正等的
    第一个标志物，下一轮复位用它当"到位了没有"的判据。
    """
    fake = fake_mcp()
    state_file = unity_service.script_dir("sid") / "start_state.json"

    bad = ('u.wait_for("BagWindow", timeout=5)\n'
           'u.expect_text("BagWindow", "没有这句话", timeout=1)\n')
    result = _run(unity_service.run_unity_script("sid", "用例", bad))
    assert result["status"] == "failed" and not state_file.exists()

    good = 'u.wait_for("BagWindow", timeout=5)\nprint("PASS: 到位")\n'
    result = _run(unity_service.run_unity_script("sid", "用例", good))
    assert result["status"] == "passed"
    learned = json.loads(state_file.read_text(encoding="utf-8"))
    assert learned["scene"] == fake.scene_path
    assert learned["wait_for"] == "BagWindow"
    # 第二轮就该用上它：输出里能看到复位
    result = _run(unity_service.run_unity_script("sid", "用例", good))
    assert "复位 -> 起跑线" in result["output"]


def _has_ffmpeg() -> bool:
    import shutil
    return shutil.which("ffmpeg") is not None


def _real_jpegs(count: int, size: str = "160x90") -> list[bytes]:
    """用 ffmpeg 造几帧**真** jpg：合成路径要真编码器才算验证过。

    ``size`` 可以给奇数尺寸（如 1737x1065，Game View 的真实值）——那是合不出来
    录像的经典原因，得专门覆盖。
    """
    import shutil
    import subprocess
    import tempfile as _tempfile

    folder = Path(_tempfile.mkdtemp(prefix="real-frames-"))
    subprocess.run([shutil.which("ffmpeg"), "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", f"testsrc=size={size}:rate={count}",
                    "-frames:v", str(count), "-q:v", "5",
                    str(folder / "f_%05d.jpg")], check=True, timeout=60)
    return [p.read_bytes() for p in sorted(folder.glob("f_*.jpg"))]


def test_stitch_survives_odd_frame_size(fake_mcp, tmp_path, monkeypatch):
    """奇数宽高的帧也要能合成：Game View 的形状是用户拖出来的（实测 1737x1065）。

    h264 的 yuv420p 要求宽高都是偶数，不处理就是整段录像合不出来，报错还很难懂
    （`Could not open encoder before EOF`）—— 存证链路上这是"录像突然都没了"的成因。
    """
    if not _has_ffmpeg():
        pytest.skip("本机没有 ffmpeg")
    fake = fake_mcp()
    fake.record_frames = _real_jpegs(3, size="1737x1065")   # 宽高都是奇数
    monkeypatch.chdir(tmp_path)
    u = unity_bridge.Unity()
    u.record_start(fps=3)
    out = u.record_stop("odd.mp4", fps=3)

    assert out["ok"] is True, out.get("error")
    assert Path(out["path"]).stat().st_size > 0


def test_stitch_failure_leaves_no_empty_mp4(fake_mcp, tmp_path, monkeypatch):
    """合成失败别留 0 字节的 mp4：产物列表里出现 run.mp4 就会被人点开。"""
    if not _has_ffmpeg():
        pytest.skip("本机没有 ffmpeg")
    fake = fake_mcp()
    folder = tmp_path / "frames"
    folder.mkdir()
    (folder / "f_00000.jpg").write_bytes(b"not a jpeg at all")   # 解码必然失败
    (folder / "f_00001.jpg").write_bytes(b"also not a jpeg")
    out_file = tmp_path / "run.mp4"

    info = unity_bridge.stitch_video(sorted(folder.glob("f_*.jpg")), out_file, fps=2)

    assert info["ok"] is False and not out_file.exists()


def test_run_unity_script_reports_bridge_down(tmp_path, monkeypatch):
    """桥不可用时脚本以 2 退出（error），而不是"断言失败"。"""
    monkeypatch.setattr(settings, "unity_mcp_url", "http://127.0.0.1:1/mcp")
    monkeypatch.setattr(settings, "unity_mcp_transport", "http")
    monkeypatch.setattr(settings, "workspace_dir", tmp_path)
    result = _run(
        unity_service.run_unity_script("sid", "用例", "u.expect_exists('X')\n"))
    assert result["exit_code"] == 2 and result["status"] == "error"
    assert "ERROR: 连不上 Unity MCP 桥" in result["output"]


def test_run_unity_script_reports_unity_not_connected(fake_mcp, tmp_path):
    """桥在线但 Unity 没连上 → exit 2（环境问题），而不是 exit 1（断言失败）。"""
    fake_mcp(editor_down=True)
    result = _run(unity_service.run_unity_script("sid", "用例", "u.expect_exists('X')\n"))
    assert result["exit_code"] == 2 and result["status"] == "error"
    assert "Unity 编辑器未连接" in result["output"]


def test_probe_reports_ready_with_server_detail(fake_mcp):
    fake_mcp()
    from src.app.core import integrations

    probe = _run(integrations._probe_unity())
    assert probe["ready"] is True
    assert "mcp-for-unity" in probe["detail"] and "Play Mode" in probe["detail"]


def test_probe_is_not_ready_when_unity_is_not_connected(fake_mcp):
    """桥在线但 Unity 没连 → 未就绪（否则用户看到绿灯、用起来每个调用都失败）。"""
    fake_mcp(editor_down=True)
    from src.app.core import integrations

    probe = _run(integrations._probe_unity())
    assert probe["ready"] is False and "Unity 编辑器未连接" in probe["error"]


def test_probe_reports_down(monkeypatch):
    monkeypatch.setattr(settings, "unity_mcp_url", "http://127.0.0.1:1/mcp")
    monkeypatch.setattr(settings, "unity_mcp_transport", "http")
    from src.app.core import integrations

    probe = _run(integrations._probe_unity())
    assert probe["ready"] is False and probe["error"]


def test_object_text_falls_back_to_children(fake_mcp):
    """按钮的标签在子对象上：自己读不到文本时要在子孙里收。

    实测（projectZero）：uGUI 的 Button 自己不带文字，标签挂在 `.../PlayButton/Text`，
    只读自己的组件会让 `expect_text("PlayButton", "NOWA GRA")` 永远失败 —— 而"按钮上
    写着什么"正是真游戏里最常写的一条断言。
    """
    fake = fake_mcp(no_own_text=True)
    u = unity_bridge.Unity()
    assert u.object_text("BagWindow") == "NOWA GRA"
    assert any(name == "execute_code" for name, _ in fake.calls)


def test_object_text_prefers_own_text(fake_mcp):
    """自己身上有文本时就用它，不必多跑一次 C#（省一次往返）。"""
    fake = fake_mcp()
    u = unity_bridge.Unity()
    assert u.object_text("BagWindow") == "背包"
    assert not any(name == "execute_code" for name, _ in fake.calls)


def test_object_text_ignores_numeric_component_values(fake_mcp):
    """只收字符串：``{"value": 1023799}`` 这类不是文本。

    实测（jynew 系统菜单）：GraphicRaycaster 的 LayerMask 序列化成 ``{"value": 1023799}``，
    被当成"对象自己的文本"收走后，面板的文本就成了一串 ID —— 断言永远不成立，
    人还以为是游戏坏了。数字一律跳过，让子孙文本兜底。
    """
    fake = fake_mcp(mask_value_junk=True)
    u = unity_bridge.Unity()
    text = u.object_text("BagWindow")
    assert text == "NOWA GRA" and "1023799" not in text
    assert any(name == "execute_code" for name, _ in fake.calls)   # 走了子孙兜底


def test_console_drops_platform_capture_noise(fake_mcp):
    """平台截图/录像自己留下的报错不进 `errors()`。

    实测（jynew）：进 Play 的头几帧没有"上一帧"可截，`CaptureScreenshotAsTexture` 会
    往 Console 里打一条 Error（Unity 内部打的，调用方 catch 不到）。留着它，"无新增
    报错"这类断言就会把平台噪声当成游戏的新报错 —— 用例偶发红，还查不出原因。
    """
    fake = fake_mcp()
    fake.console_noise = True
    u = unity_bridge.Unity()

    assert u.errors(limit=30) == ["NullReferenceException: Object reference not set"]
    # 工具层（模块级 console）读到的是同一份干净数据（服务器把条目套了两层，
    # 这里只关心"噪声没了、真报错还在"）
    blob = json.dumps(_run(unity_bridge.console(limit=30)), ensure_ascii=False)
    assert "NullReferenceException" in blob and "CaptureScreenshotAsTexture" not in blob


def test_errors_unwraps_nested_console_shape(fake_mcp):
    """errors() 必须能穿过 data.items 这一层。

    实测（真游戏上）：服务器把条目嵌在 ``data.items`` 里，以前只认顶层的
    errors/logs/entries，于是**明明有报错也返回空** —— "断言控制台没报错"这条用例
    会永远通过，等于没测。
    """
    fake = fake_mcp()
    u = unity_bridge.Unity()
    errs = u.errors()
    assert len(errs) == 1 and "NullReferenceException" in errs[0]
    name, args = [c for c in fake.calls if c[0] == "read_console"][-1]
    assert isinstance(args.get("types"), list)          # 传字符串会被服务器直接拒
    assert "exception" not in (args.get("types") or [])  # 非法的取值不能漏出去


def test_log_types_are_normalised():
    """types 归一：只留服务器认的取值，且永远是 list。"""
    norm = unity_bridge._norm_log_types
    assert norm("error,warning,exception,assert") == ["error", "warning"]
    assert norm("all") == ["all"]
    assert norm("bogus") == ["all"]
    assert norm(["error", "log"]) == ["error", "log"]


def test_dead_session_is_reestablished_for_resources(fake_mcp):
    """会话被绑在已退出的 Unity 实例上时，要重建会话再读，而不是判定"Unity 没连"。

    实测（连开第二个游戏工程）：旧编辑器退出后，同一条 MCP 会话读实例清单永远回
    "Unity session not available"，新会话却正常 —— 平台因此一直显示未连接。
    """
    fake = fake_mcp()
    fake.session_dead_reads = 1          # 第一次资源读撞上死会话，重建后就好
    st = _run(unity_bridge.status())

    assert st["unity_connected"] is True
    assert [i["name"] for i in st["instances"]] == ["unity-smoke"]


def test_dead_session_failure_is_not_swallowed_forever(fake_mcp):
    """真没人连的时候，仍然如实报"未连接" —— 重建一次救不回来就认账，别死循环。"""
    fake = fake_mcp()
    fake.session_dead_reads = 99
    st = _run(unity_bridge.status())
    assert st["available"] is True and st["unity_connected"] is False


def test_dead_session_hint_detection():
    assert unity_bridge._is_dead_session("Unity session not available")
    assert unity_bridge._is_dead_session("会话已过期（HTTP 404）")
    assert not unity_bridge._is_dead_session("object not found: X")


def test_screenshot_prefers_screencapture(fake_mcp, tmp_path):
    """截图默认走 ScreenCapture —— 相机渲染拍不到 Screen Space - Overlay 的 UI。

    实测（Trash Dash）：START 按钮就在屏幕坐标上、没被剔除，相机路径的图里却一个 UI
    都没有；换 ScreenCapture 截游戏视图才拍得到。UI 自动化靠截图当证据，这条路不能错。
    """
    from pathlib import Path
    overlay = tmp_path / "overlay.png"
    payload = b"\x89PNG\r\n\x1a\noverlay-bytes"
    overlay.write_bytes(payload)
    fake = fake_mcp()
    fake.screenshot_path = str(overlay)

    saved = tmp_path / "saved.png"
    out = _run(unity_bridge.screenshot(str(saved)))
    assert out["success"] is True and out["tool"] == "screencapture"
    assert Path(out["path"]).read_bytes() == payload
    assert not overlay.exists()          # 编辑器临时文件用完即删，别在人家工程里堆垃圾
    assert not any(name == "manage_camera" for name, _ in fake.calls)


def test_screenshot_falls_back_to_camera_tool(fake_mcp, tmp_path):
    """ScreenCapture 走不通（比如编辑器临时目录读不到）时退回服务器自带的相机截图。"""
    fake = fake_mcp()                       # screenshot_path 为空 -> C# 那条路不可用
    out = _run(unity_bridge.screenshot(str(tmp_path / "saved.png")))
    assert out["success"] is True and out["tool"] == "manage_camera"
    assert any(name == "manage_camera" for name, _ in fake.calls)


def test_exists_tolerates_whitespace_in_names(fake_mcp):
    """名字两端有空白也要查得到。

    实测（Chop Chop）：菜单项叫 ``Button Settings ``（名字带尾随空格），用例里写正常名字
    就查不到 —— 服务器的 by_name 是精确匹配，兜底的是 C# 探测那层（Trim 后比较）。
    """
    fake_mcp()
    u = unity_bridge.Unity()
    assert u.exists("  BagWindow  ") is True
    assert u.exists("NopeNotHere") is False


def test_empty_instance_list_triggers_rebuild(fake_mcp):
    """实例清单"成功但空"也要换会话重读。

    实测（连着换第四个工程）：旧编辑器退出后，那条会话读实例清单回的是
    ``success: true, instances: []``（不是报错），于是换工程后的**第一次**探活
    仍显示"未连接"，要等下一次才恢复 —— 就绪中心上就是一次假红。
    """
    fake = fake_mcp()
    fake.session_dead_reads = 0
    fake.empty_instances_once = True          # 第一次回空清单，重建会话后正常
    st = _run(unity_bridge.status())
    assert [i["name"] for i in st["instances"]] == ["unity-smoke"]
    assert st["unity_connected"] is True


def test_click_falls_back_to_visible_text(fake_mcp):
    """名字/路径都没命中时按**可见文本**找 —— 中文真游戏里对象名是英文，界面上写中文。

    （这一段是 C# 片段里的兜底逻辑，假服务器只验证片段生成没坏、调用链没变。）
    """
    fake = fake_mcp()
    u = unity_bridge.Unity()
    out = u.click("返回游戏")            # 假服务器里没有这个对象
    assert isinstance(out, dict)

    code = [c for n, c in fake.calls if n == "execute_code"][-1].get("code", "")
    assert "IPointerClickHandler" in code          # 文本兜底那段确实拼进去了
    assert "GetProperty(\"text\")" in code


def test_find_objects_falls_back_from_name_to_path(fake_mcp):
    """名字查空要按路径再查一次。

    实测（jynew）：服务器的 by_name 对运行时克隆出来的对象（``MainUIPanel(Clone)``）
    一个都查不到，by_path 却查得到 —— 不回退的话，"按名字查界面对象"在真游戏里
    永远返回空，用例只能靠猜路径。
    """
    fake = fake_mcp()
    fake.name_search_blind = True                   # by_name 查不到、by_path 查得到
    u = unity_bridge.Unity()
    out = u.find_objects(name="BagWindow")
    assert out["count"] >= 1

    methods = [a.get("search_method") for n, a in fake.calls if n == "find_gameobjects"]
    assert "by_name" in methods and "by_path" in methods


def test_find_objects_does_not_send_include_inactive(fake_mcp):
    """不要把 include_inactive 发给服务器。

    实测（jynew）：带上 ``include_inactive: true`` 后，同一个 by_path 查询从 1 条变成 0 条；
    不带则正常，且默认就包含未激活对象（关掉的界面面板照样查得到）。
    """
    fake = fake_mcp()
    u = unity_bridge.Unity()
    u.find_objects(name="BagWindow")
    sent = [a for n, a in fake.calls if n == "find_gameobjects"][-1]
    assert "include_inactive" not in sent and "find_inactive" not in sent


def test_subtree_text_reads_descendants(fake_mcp):
    """subtree_text 走的是子孙文本，和 object_text（先看自己）分工不同。"""
    fake = fake_mcp(no_own_text=True)
    u = unity_bridge.Unity()
    assert u.subtree_text("BagWindow") == "NOWA GRA"


def test_is_visible_and_expect_hidden(fake_mcp):
    """界面开关要看 activeInHierarchy，不是"在不在场景里"。

    实测（jynew）：点「返回游戏」后面板仍在场景里（只是被停用），
    所以 `expect_absent` 永远等不到，必须用 `expect_hidden`。
    """
    fake = fake_mcp()
    u = unity_bridge.Unity()
    assert u.is_visible("BagWindow") is True
    assert u.exists("BagWindow") is True

    fake.hidden_object = True                     # 面板被停用（还在场景里）
    assert u.exists("BagWindow") is True          # "在不在" 仍然是 True
    assert u.is_visible("BagWindow") is False     # "显示着吗" 变成 False
    u.expect_hidden("BagWindow", timeout=2)


def test_start_line_snapshot_when_case_plays_itself(fake_mcp, tmp_path, monkeypatch):
    """用例自己 `u.play()` 也要能学到起跑线（在"等到标志物"的那一瞬记）。

    实测踩到：智能体写的《群侠传》新手流程用例全程由用例自己 play，prelude 那次
    快照（在用例动作之前）拍到的还是"没进 Play"，于是跑通了起跑线仍为空、下一轮
    不会复位。这里的判据是"第一个动作就是等待" —— 那就是等就绪，不是等中途面板。
    """
    candidate = tmp_path / "start_state.candidate.json"
    monkeypatch.setenv("UNITY_START_STATE_FILE", str(candidate))
    fake = fake_mcp()

    u = unity_bridge.Unity()
    assert not candidate.exists()
    u.wait_for("BagWindow", timeout=5)          # 第一个动作：等就绪

    state = json.loads(candidate.read_text(encoding="utf-8"))
    assert state["scene"] == fake.scene_path and state["wait_for"] == "BagWindow"
    assert state["play"] is True and state["mode"] == "hard"


def test_start_line_snapshot_skips_when_wait_is_not_first(fake_mcp, tmp_path, monkeypatch):
    """中途的等待不记：那时已经是半路状态，记下来比不记更糟（会把下一轮带偏）。"""
    candidate = tmp_path / "start_state.candidate.json"
    monkeypatch.setenv("UNITY_START_STATE_FILE", str(candidate))
    fake_mcp()

    u = unity_bridge.Unity()
    u.click("UI/BagWindow/Close")               # 先有动作
    u.wait_for("BagWindow", timeout=5)

    assert not candidate.exists()


def test_start_line_snapshot_skips_without_play_mode(fake_mcp, tmp_path, monkeypatch, ):
    """没进 Play Mode 就没有"起跑线"可言（编辑器里等到的对象不算游戏现场）。"""
    candidate = tmp_path / "start_state.candidate.json"
    monkeypatch.setenv("UNITY_START_STATE_FILE", str(candidate))
    fake = fake_mcp()
    fake.playing = False

    u = unity_bridge.Unity()
    u.wait_for("BagWindow", timeout=5)

    assert not candidate.exists()


def test_run_script_uses_the_given_workdir(fake_mcp, tmp_path, monkeypatch):
    """调用方指定运行目录时就用它（REST 入队那条路要能把目录记进执行记录）。"""
    from src.app.core.config import settings

    monkeypatch.setattr(settings, "workspace_dir", tmp_path)
    monkeypatch.setenv("UNITY_RECORD", "0")
    fake_mcp()
    workdir = tmp_path / "default" / "unity-auto" / "sid" / "20260919_120000_用例"
    workdir.mkdir(parents=True)

    # 用例里带一个动作：轨迹文件是第一次记步骤时才落盘的（没动作就没有轨迹文件）
    out = _run(unity_service.run_unity_script(
        "sid", "用例", "u.expect_exists('BagWindow', timeout=5)\n", workdir=workdir))

    assert out["status"] == "passed"
    assert (workdir / "case.py").is_file()
    names = {Path(p).name for p in json.loads(out["screenshots"])}
    assert {"steps.jsonl"} <= names
