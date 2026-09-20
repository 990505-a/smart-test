"""Smart Test Platform — 服务控制台 (Launcher/Supervisor)

独立的进程管理器，与被管理的服务解耦（因此可以重启包括 FastAPI 在内的所有服务）。

- 地址: http://localhost:5010
- 管理对象: LangGraph(:5011) / FastAPI(:5012) / WebUI(:5013) / Playwright 执行器(:5015) /
  Unity MCP 桥(:5016，autostart=False) / LightRAG(:5014，autostart=False)。
  这份名单就是"平台能自己拉起的全部服务"，与 core/integrations.py 的 launch 字段
  一一对应（有测试保证）。
- 能力: 启动/停止/重启、端口探测、进程树查杀（含非本控制台启动的进程）、实时日志（内存环形缓冲 + logs/ 文件落盘）
- 启动: 双击 启动控制台.bat（或 .venv\\Scripts\\python.exe launcher.py）
- 注: codebase-memory 的 stdio 会话由 FastAPI/LangGraph 进程内部按需拉起，不在此管理；
  它的二进制由平台自管安装（services/cbm_install.py，见 /codebase 页的「安装/升级」）。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
import uuid
import webbrowser
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import socket
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

ROOT = Path(__file__).parent.resolve()
LOGS_DIR = ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)

#: logs/<svc>.log 采用逐行追加（可 tail -f），超过这个大小就在下次启动时轮转成
#: <svc>.log.1。上限宽松：留得住最近几次运行，又不至于让文件无限长。
LOG_FILE_MAX_BYTES = 5 * 1024 * 1024

LAUNCHER_PORT = int(os.environ.get("LAUNCHER_PORT", "5010"))
IS_WIN = sys.platform == "win32"
PY = str(ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python"))

# 子进程一律绕开系统代理。httpx 的 trust_env 会通过 urllib.getproxies() 读到 macOS
# 的系统代理设置（Clash 之类把 HTTP/HTTPS/SOCKS 都指到 127.0.0.1:7897），于是模型
# 请求被塞进代理——实测 langgraph 进程挂着一条到 :7897 的 ESTABLISHED，run 停在
# tools 节点 30 分钟没动静。容器版 compose 早就用 NO_PROXY:"*" + 清空 https_proxy
# 挡掉了这件事（见 docker-compose.yml 的 x-no-proxy-env 注释），本机模式必须同样处理，
# 否则"本机比容器还不稳"。
NO_PROXY_ENV = {
    "NO_PROXY": "*",
    "no_proxy": "*",
    "HTTP_PROXY": "",
    "HTTPS_PROXY": "",
    "http_proxy": "",
    "https_proxy": "",
    "ALL_PROXY": "",
    "all_proxy": "",
}

@dataclass
class ServiceSpec:
    name: str
    label: str
    command: list[str]
    cwd: Path
    port: int | None = None            # 用于状态探测（外部实例识别）
    health_note: str = ""
    autostart: bool = True
    env: dict[str, str] | None = None  # 附加环境变量（合并到 os.environ 之上）


@dataclass
class ServiceState:
    spec: ServiceSpec
    proc: asyncio.subprocess.Process | None = None
    logs: deque = field(default_factory=lambda: deque(maxlen=4000))
    started_at: float | None = None
    task: asyncio.Task | None = None       # log pump task
    restart_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


SERVICES: dict[str, ServiceState] = {}


def _llm_extra_headers(base_url: str) -> dict[str, str]:
    """上游 LLM 网关要求的额外请求头。

    opencode.ai 的 Zen Go 网关缺 ``x-opencode-session`` 会直接 400
    （MissingSessionID）——平台自己的智能体那边由 ``model_factory`` 附上这个头，
    但 LightRAG 加不了：它的 ``default_headers`` 在源码里写死（只对 DashScope 开了
    一个 env 口子），LLM 绑定又只有 host/key/model 三个环境变量。
    所以本机模式下由控制台代转一层补头，见 ``llm_proxy``。
    """
    low = (base_url or "").lower()
    if "opencode.ai" in low:
        return {"x-opencode-session": LLM_SESSION_ID}
    return {}


def _llm_upstream() -> dict:
    """LightRAG 要用的上游 LLM 端点（读当前 .env，不是启动时那份快照）。

    每次现读是有意的：设置页改完 LLM 配置，重启知识库实例就该生效，
    不该再要求重启整个控制台（控制台是常驻进程，那份配置是 import 时读的）。
    """
    try:
        from src.app.core.config import Settings

        cfg = Settings()
    except Exception:  # noqa: BLE001 — 控制台保持可独立运行
        return {"base_url": "", "headers": {}}
    base_url = (cfg.lightrag_llm_base_url or cfg.llm_base_url
                or "https://api.deepseek.com/v1").rstrip("/")
    return {"base_url": base_url, "headers": _llm_extra_headers(base_url)}


def _lightrag_llm_host() -> str:
    """LightRAG 的 LLM_BINDING_HOST：上游要额外头时指向本控制台的代转端点。"""
    upstream = _llm_upstream()
    if upstream["headers"]:
        return f"http://127.0.0.1:{LAUNCHER_PORT}{LLM_PROXY_PATH}"
    return upstream["base_url"]


def _lightrag_env(kb) -> dict[str, str]:
    """Build the env overlay for one lightrag-server instance (= 一个知识库).

    每个库一个进程、一个端口、一个 ``WORKSPACE``（数据命名空间）：这是官方
    LightRAG 的隔离单位——``/query``、``/documents/*`` 的请求体里没有 workspace
    字段，WebUI 也只是展示，所以"两个项目分开"只能靠两个实例。文件类存储按
    ``working_dir/<workspace>/`` 落盘，因此所有库共用同一个工作目录即可。

    LLM/embedding 是所有库共用的（同一套模型读同一批文档）；三项 LLM 绑定优先取
    ``LIGHTRAG_LLM_*``，留空则跟随平台主模型——过去这里硬编码
    ``https://api.deepseek.com/v1``，配上的却是另一个厂商的 key，入库/检索必 401。
    """
    try:
        from src.app.core.config import Settings

        cfg = Settings()   # 现读 .env：设置页改完重启实例即生效
    except Exception:  # noqa: BLE001 — 控制台保持可独立运行
        return {}
    env = {
        "HOST": "127.0.0.1",
        "PORT": str(kb.port),
        "WORKING_DIR": str(ROOT / cfg.lightrag_working_dir),
        "WORKSPACE": kb.workspace,
        "LLM_BINDING": "openai",
        "LLM_BINDING_HOST": _lightrag_llm_host(),
        "LLM_BINDING_API_KEY": (cfg.lightrag_llm_api_key or cfg.llm_api_key
                                or cfg.deepseek_api_key),
        "LLM_MODEL": (cfg.lightrag_llm_model or cfg.llm_model
                      or cfg.deepseek_model),
        "EMBEDDING_BINDING": "openai",
        "EMBEDDING_BINDING_HOST": cfg.lightrag_embedding_base_url,
        "EMBEDDING_BINDING_API_KEY": cfg.lightrag_embedding_api_key,
        "EMBEDDING_MODEL": cfg.lightrag_embedding_model,
        "EMBEDDING_DIM": str(cfg.lightrag_embedding_dim),
    }
    return env


# ---------------------------------------------------------------------------
# LightRAG 自带界面的「RAG 设置」页（overlay）
#
# 官方 WebUI 是一个写死在包里的静态构建（``lightrag/api/webui``，挂载目录
# 不可配置），没有设置页、也没有改配置的 API——LLM/embedding 是启动环境变量，
# 模型/embedding 想改只能改完重启进程。所以平台侧的配置入口只能"贴"进那个目录：
# 把 tools/lightrag-ui/ 下的静态页同步过去，并在 index.html 里注入一个入口按钮。
#
# 为什么敢往 site-packages 里写：本机模式就是这个 venv，且**每次启动知识库都同步
# 一次**（覆盖 + 补齐），所以升级/重装 LightRAG 之后会自动长回来。注入用显式标记
# 包裹，重复执行是幂等的。
# ---------------------------------------------------------------------------

LIGHTRAG_UI_SRC = ROOT / "tools" / "lightrag-ui"
#: index.html 里注入片段的标记（成对出现，重复注入时先删旧的）
_UI_MARK_START = "<!-- smart-test:rag-settings -->"
_UI_MARK_END = "<!-- /smart-test:rag-settings -->"
#: 同步进 WebUI 目录的文件（config.js 由启动器按当前部署现生成）
_UI_FILES = ("rag-settings.html", "rag-settings.js", "rag-settings.css",
             "rag-settings-button.js")


def _lightrag_webui_dir():
    """已安装 lightrag 的 WebUI 静态目录（找不到包时返回 None）。"""
    try:
        import lightrag
        return Path(lightrag.__file__).parent / "api" / "webui"
    except Exception:  # noqa: BLE001 — 没装 lightrag 时不同步
        return None


def _service_port(name: str, default: int) -> int:
    """本控制台服务表里的端口（找不到就用默认值）。"""
    for spec in _default_services():
        if spec.name == name and spec.port:
            return spec.port
    return default


def _sync_lightrag_ui() -> str:
    """把「RAG 设置」页同步进 LightRAG 的 WebUI 目录，返回一句人话结果。"""
    webui = _lightrag_webui_dir()
    if webui is None or not webui.is_dir():
        return "未找到已安装的 lightrag WebUI 目录，跳过"
    if not LIGHTRAG_UI_SRC.is_dir():
        return f"缺少 {LIGHTRAG_UI_SRC.relative_to(ROOT)}，跳过"

    copied = []
    for name in _UI_FILES:
        src = LIGHTRAG_UI_SRC / name
        if not src.is_file():
            continue
        dst = webui / name
        try:
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            copied.append(name)
        except OSError as exc:
            return f"写入 {dst} 失败: {exc}"

    # 给静态资源加内容指纹：页面文件名固定（无害的启发式缓存），改完 overlay 之后
    # 浏览器可能还在用旧 JS/CSS——实测踩过："读不到平台配置（...）：Cannot set
    # properties of null"。HTML 本身是 no-store 的，所以把指纹写进它的引用里即可。
    html_path = webui / "rag-settings.html"
    try:
        html = html_path.read_text(encoding="utf-8")
        digest = hashlib.md5()
        for name in ("rag-settings.js", "rag-settings.css"):
            source = LIGHTRAG_UI_SRC / name
            if source.is_file():
                digest.update(source.read_bytes())
        stamp = digest.hexdigest()[:8]
        for name in ("rag-settings.js", "rag-settings.css"):
            html = html.replace(f"./{name}", f"./{name}?v={stamp}")
        html_path.write_text(html, encoding="utf-8")
    except OSError as exc:
        return f"写入 {html_path} 失败: {exc}"

    # 页面靠这个文件知道平台在哪：LightRAG 在 :50xx，平台后端在 :5012 前端在 :5013，
    # 跨端口（平台后端开了 CORS，见 fastapi_app.py），所以地址必须由部署侧注入。
    cfg_js = webui / "rag-settings-config.js"
    try:
        cfg_js.write_text(
            "window.__SMART_TEST__ = " + json.dumps({
                "platformApi": f"http://127.0.0.1:{_service_port('fastapi', 5012)}",
                "platformRagPage": f"http://localhost:{_service_port('webui', 5013)}/rag",
            }, ensure_ascii=False) + ";\n",
            encoding="utf-8",
        )
    except OSError as exc:
        return f"写入 {cfg_js} 失败: {exc}"
    copied.append(cfg_js.name)

    # 入口按钮：注入 index.html（管理端 WebUI）。workspace.html 是"查询用户"
    # 入口，故意不注入——那个入口面向只提问的人。
    index = webui / "index.html"
    try:
        html = index.read_text(encoding="utf-8")
    except OSError as exc:
        return f"读取 {index} 失败: {exc}"
    if _UI_MARK_START in html:
        html = html.split(_UI_MARK_START)[0] + html.split(_UI_MARK_END)[-1]
    snippet = (
        f"{_UI_MARK_START}\n"
        f'    <script src="./rag-settings-button.js" defer></script>\n'
        f"    {_UI_MARK_END}"
    )
    marker = "<!-- __LIGHTRAG_RUNTIME_CONFIG__ -->"
    if marker in html:
        html = html.replace(marker, marker + "\n    " + snippet, 1)
    else:
        html = html.replace("</body>", snippet + "\n  </body>", 1)
    try:
        index.write_text(html, encoding="utf-8")
    except OSError as exc:
        return f"注入 {index} 失败: {exc}"
    return f"已同步 {len(copied)} 个文件到 {webui}"


def _lightrag_spec(kb) -> ServiceSpec:
    """一个知识库 = 一条 lightrag 服务（名字/端口/workspace 都按库区分）。"""
    return ServiceSpec(
        name=kb.service_name,
        label=f"LightRAG 知识库 · {kb.label} (:端口 {kb.port})",
        command=[PY, "-m", "lightrag.api.lightrag_server"], cwd=ROOT,
        port=kb.port, env=_lightrag_env(kb), autostart=False,
        health_note=f"RAG 知识库本体（图谱+向量检索）；数据目录 {kb.data_dir}；"
                    f"自带 WebUI /webui（含平台注入的「RAG 设置」页）；"
                    f"需 LIGHTRAG_EMBEDDING_API_KEY",
    )


def _lightrag_specs() -> list[ServiceSpec]:
    """按知识库注册表生成 lightrag 服务（每库一个实例）。

    官方 LightRAG 的隔离单位是**实例**（``--workspace`` 启动时定死，请求体里没有
    workspace 字段），所以"两个项目别混在一起"= 两个实例，见 services/rag_kbs.py。
    """
    try:
        from src.app.services.rag_kbs import load_kbs
        specs = [_lightrag_spec(kb) for kb in load_kbs()]
        if specs:
            return specs
    except Exception as exc:  # noqa: BLE001 — 注册表/模块坏了也要能起来
        print(f"[launcher] 知识库注册表不可用（{exc}），按单库兜底")
    # 兜底：默认库那一条（:5014）。core/integrations.py 的 launch="lightrag"
    # 与就绪中心的「启动」按钮找的就是这个名字。
    from types import SimpleNamespace
    return [ServiceSpec(
        name="lightrag", label="LightRAG 知识库 (:5014)",
        command=[PY, "-m", "lightrag.api.lightrag_server"], cwd=ROOT,
        port=5014, env=_lightrag_env(SimpleNamespace(port=5014, workspace="")),
        autostart=False,
        health_note="RAG 知识库本体（图谱+向量检索）；自带 WebUI /webui；"
                    "需 LIGHTRAG_EMBEDDING_API_KEY",
    )]




def _playwright_env() -> dict[str, str]:
    """playwright runner 的环境（等价于 tools/playwright-runner/start-local.sh）。

    RUNS_ROOT 必须与平台约定一致（workspace/default/web-ui-auto/runs），否则
    Web-UI 自动化页看不到录像/轨迹。
    """
    return {
        "PW_HOME": str(ROOT / "tools" / "playwright-runner"),
        "RUNS_ROOT": str(ROOT / "workspace" / "default" / "web-ui-auto" / "runs"),
        "PORT": "5015",
    }


#: 与 Unity 工程里「MCP for Unity」包版本对应的 PyPI 服务器版本
_UNITY_MCP_SERVER_VERSION = "10.2.0"


# ---------------------------------------------------------------------------
# LLM 代转（本机模式）：给上游网关补它要求的请求头
#
# 控制台是唯一"一定在跑、且知道 LightRAG 的 LLM 该指向哪"的进程，所以这层放在这里：
# LightRAG 的绑定只有 host/key/model 三个环境变量，加不了自定义头。
# 只接受来自 127.0.0.1 的请求（控制台监听 0.0.0.0，不能让它变成开放的转发器）。
# ---------------------------------------------------------------------------

#: LightRAG 的 LLM_BINDING_HOST 指向这个前缀
LLM_PROXY_PATH = "/api/llm"
#: 进程级会话 id：网关要求"稳定"（用于路由/缓存分片），值本身无所谓
LLM_SESSION_ID = uuid.uuid4().hex


def _unity_mcp_command() -> list[str]:
    """Unity MCP 桥（官方 CoplayDev/unity-mcp 的 python 服务器）的启动命令。

    端口取 UNITY_MCP_URL 里的端口（默认 5016），与平台侧的 unity_mcp_url 保持一致；
    整条命令可用 UNITY_MCP_COMMAND 覆盖（没装 uv 时指到自己的服务器）。
    Unity 侧装「MCP for Unity」包后连到这个地址即可 —— 平台本身不含任何 Unity 代码。
    """
    from urllib.parse import urlparse

    from src.app.core.config import settings as cfg

    custom = (cfg.unity_mcp_command or "").strip()
    if custom and (cfg.unity_mcp_transport or "http").strip().lower() == "http":
        return shlex.split(custom)
    port = urlparse(cfg.unity_mcp_url).port or 5016
    # 钉版本：Unity 侧插件按 `mcpforunityserver==<插件版本>` 拉同一个 PyPI 包
    # （见 MCPForUnity/Editor/Helpers/AssetPathUtility.cs），两边版本不一致时插件会
    # 提示不匹配。升级 Unity 侧包之后把这里和 .env.example 一起改。
    return ["uvx", "--from", f"mcpforunityserver=={_UNITY_MCP_SERVER_VERSION}",
            "mcp-for-unity", "--transport", "http", "--http-port", str(port)]


def _default_services() -> list[ServiceSpec]:
    specs = [
        ServiceSpec(
            name="langgraph", label="LangGraph 智能体服务 (:5011)",
            command=[PY, "start_server.py"], cwd=ROOT, port=5011,
            health_note="用例生成 / UI 自动化 Agent 运行时",
        ),
        ServiceSpec(
            name="fastapi", label="FastAPI 后端 (:5012)",
            command=[PY, "-m", "uvicorn", "src.app.fastapi_app:app",
                     "--host", "0.0.0.0", "--port", "5012"],
            cwd=ROOT, port=5012,
            health_note="平台 API / 图谱定时调度 / 记忆模块文件管理",
        ),
        ServiceSpec(
            name="webui", label="Web 前端 Next.js (:5013)",
            command=(["cmd", "/c", "npm", "run", "dev", "--", "-p", "5013"] if IS_WIN
                     else ["npm", "run", "dev", "--", "-p", "5013"]),
            cwd=ROOT / "webui", port=5013,
            health_note="平台界面",
        ),
        ServiceSpec(
            # 以前它只能靠手工跑 start-local.sh 拉起：命令在仓库里、依赖也现成，
            # 却不在控制台上，于是"重启机器后 Web-UI 自动化连不上"成了偶发故障。
            name="playwright", label="Playwright 执行器 (:5015)",
            command=["node", str(ROOT / "tools" / "playwright-runner" / "server.mjs")],
            cwd=ROOT / "tools" / "playwright-runner", port=5015,
            env=_playwright_env(),
            health_note="Web-UI 自动化执行器（浏览器侧）；首次需 npm i + "
                        "playwright install chromium（见 tools/playwright-runner/start-local.sh）",
        ),
        # 知识库：注册表里每个库一条服务（默认库的服务名是 "lightrag"，
        # 与 core/integrations.py 的 launch 字段、就绪中心的一键启动对应）
        *_lightrag_specs(),
        ServiceSpec(
            # Unity 侧只装一个 MCP 桥包，平台侧就是这一个服务器进程；两者互为镜像：
            # 少了它"Unity 自动化"整个能力不可用（就绪中心会红）。
            name="unity-mcp", label="Unity MCP 桥 (:5016)",
            command=_unity_mcp_command(), cwd=ROOT, port=5016, autostart=False,
            health_note="通用 Unity 自动化桥（标准 MCP，CoplayDev/unity-mcp）；"
                        "需 uv（Python 3.10+），Unity 工程里装「MCP for Unity」包后指向本机 5016",
        ),
    ]
    return specs


def _port_listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.6):
            return True
    except OSError:
        return False


async def _pid_on_port(port: int) -> int | None:
    """占用该端口的监听进程 PID（Windows 用 netstat，POSIX 用 lsof）。

    过去非 Windows 直接 ``return None``，后果是 **launcher 只能管理自己启动的进程**：
    控制台上的「重启」对一个它没启动过的服务（例如上一次 launcher 重启前留下的那些）
    会静默地什么都不做——点了像没反应；而 launcher 一旦重启，之前的服务就全部变成
    "管不了"的状态。macOS/Linux 上这条是主路径，不是边角情况。
    """
    if IS_WIN:
        try:
            proc = await asyncio.create_subprocess_exec(
                "netstat", "-ano", stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL)
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        except Exception:  # noqa: BLE001
            return None
        for line in out.decode("utf-8", errors="replace").splitlines():
            if f":{port} " in line and "LISTENING" in line:
                parts = line.split()
                if parts:
                    pid = int(parts[-1])
                    if pid > 0:
                        return pid
        return None

    # POSIX：lsof -t 直接只输出 PID（可能多个，取第一个；树由 _kill_tree 处理）
    try:
        proc = await asyncio.create_subprocess_exec(
            "lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
    except Exception:  # noqa: BLE001 — 未装 lsof 时退化为"查不到"，不影响启动
        return None
    for token in out.decode("utf-8", errors="replace").split():
        if token.isdigit():
            pid = int(token)
            if pid > 0 and pid != os.getpid():
                return pid
    return None


async def _kill_tree(pid: int) -> None:
    if IS_WIN:
        proc = await asyncio.create_subprocess_exec(
            "taskkill", "/PID", str(pid), "/T", "/F",
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        await proc.communicate()
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def _log_path(state: ServiceState) -> Path:
    return LOGS_DIR / f"{state.spec.name}.log"


def _append_log_file(state: ServiceState, entry: str) -> None:
    """逐行追加到 logs/<svc>.log。

    过去这里只在进程退出/停止时用 ``write_text`` 整体快照一次，运行期的日志只存在
    内存 deque 里（控制台 UI 走 ``GET /api/logs/{name}`` 读它）。后果是：**排查时最
    需要 ``tail -f`` 的那一刻，文件恰恰停在"上一次停止"的时间点**，看起来像日志采集
    断了——实际只是没到写盘时机。改成逐行追加后，文件与接口内容一致、可 tail。
    """
    try:
        with open(_log_path(state), "a", encoding="utf-8") as fh:
            fh.write(entry + "\n")
    except OSError:
        pass


def _ensure_log_file_ends_with_newline(state: ServiceState) -> None:
    """老日志可能不以换行结尾，先补一个。

    追加式写入之前，文件是"停止时整体快照"写的，末尾未必有换行；直接 append 会让
    新行黏在旧行尾（实测：``[00:12:52] (已停止 …)[00:27:34] ===== 启动 … =====``）。
    """
    path = _log_path(state)
    try:
        if path.exists() and path.stat().st_size:
            with open(path, "rb") as fh:
                fh.seek(-1, os.SEEK_END)
                if fh.read(1) != b"\n":
                    with open(path, "a", encoding="utf-8") as out:
                        out.write("\n")
    except OSError:
        pass


def _rotate_log_if_large(state: ServiceState) -> None:
    """追加式日志会无限增长，启动前把过大的那份挪成 .log.1。"""
    path = _log_path(state)
    try:
        if path.exists() and path.stat().st_size > LOG_FILE_MAX_BYTES:
            path.replace(path.with_suffix(".log.1"))
    except OSError:
        pass


def _append_log(state: ServiceState, line: str) -> None:
    ts = time.strftime("%H:%M:%S")
    entry = f"[{ts}] {line.rstrip()}"
    state.logs.append(entry)
    _append_log_file(state, entry)


async def _pump(state: ServiceState) -> None:
    proc = state.proc
    assert proc is not None and proc.stdout is not None
    try:
        async for raw in proc.stdout:
            _append_log(state, raw.decode("utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001
        _append_log(state, f"(日志读取中断: {exc})")
    finally:
        rc = await proc.wait() if proc.returncode is None else proc.returncode
        _append_log(state, f"(进程退出 code={rc})")


def _service_spec(name: str) -> ServiceSpec | None:
    """服务名 → spec（现算，所以知识库清单改了不用重启控制台）。"""
    for spec in _default_services():
        if spec.name == name:
            return spec
    return None


def _state(name: str) -> ServiceState | None:
    """按名字取运行状态；知识库的服务是按注册表现算出来的，第一次用到才建。

    以前服务表只在控制台启动时建一次，于是"在平台上新增一个知识库"必须重启
    控制台——一重启，智能体/后端/前端的连接也跟着抖一下。服务名是纯函数
    （``rag_kbs.KB.service_name``），所以这里改成用的时候现算，注册表改完即时可见。
    """
    state = SERVICES.get(name)
    if state is not None:
        return state
    spec = _service_spec(name)
    if spec is None:
        return None
    state = ServiceState(spec=spec)
    SERVICES[name] = state   # 进程/日志状态按名字留着（重启控制台后靠端口识别接管）
    return state


async def start_service(name: str) -> dict:
    state = _state(name)
    if state is None:
        raise HTTPException(status_code=404, detail=f"未知服务: {name}")
    if name.startswith("lightrag"):
        # 知识库实例起来之前先把「RAG 设置」页同步进 LightRAG 的 WebUI 目录：
        # 顺序反了的话，用户点开 WebUI 会看到入口按钮却打不开页面。
        _append_log(state, _sync_lightrag_ui())
    async with state.restart_lock:
        if state.proc is not None and state.proc.returncode is None:
            return {"started": True, "note": "已在运行"}
        spec = state.spec
        # 端口被外部进程占用时先接管清理
        if spec.port:
            ext_pid = await _pid_on_port(spec.port)
            if ext_pid:
                _append_log(state, f"端口 {spec.port} 被 PID {ext_pid} 占用，先停止该进程")
                await _kill_tree(ext_pid)
                for _ in range(20):
                    if not _port_listening(spec.port):
                        break
                    await asyncio.sleep(0.5)

        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if IS_WIN else 0
        _rotate_log_if_large(state)
        _ensure_log_file_ends_with_newline(state)
        # 每次启动写一条分隔线：日志是追加式的，没有它就分不清哪几行属于哪一次运行
        _append_log(state, f"===== 启动 {time.strftime('%Y-%m-%d %H:%M:%S')} =====")
        _append_log(state, f"启动: {' '.join(spec.command)}  (cwd={spec.cwd})")
        try:
            state.proc = await asyncio.create_subprocess_exec(
                *spec.command, cwd=str(spec.cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                creationflags=creationflags,
                env={**os.environ, **NO_PROXY_ENV, "PYTHONUNBUFFERED": "1", **(spec.env or {})},
            )
        except OSError as exc:
            _append_log(state, f"启动失败: {exc}")
            raise HTTPException(status_code=500, detail=f"启动失败: {exc}")
        state.started_at = time.time()
        if state.task:
            state.task.cancel()
        state.task = asyncio.create_task(_pump(state))
        await asyncio.sleep(0.5)
        return {"started": True, "pid": state.proc.pid}


async def stop_service(name: str) -> dict:
    state = _state(name)
    if state is None:
        raise HTTPException(status_code=404, detail=f"未知服务: {name}")
    async with state.restart_lock:
        stopped = []
        if state.proc is not None and state.proc.returncode is None:
            await _kill_tree(state.proc.pid)
            for _ in range(20):
                if state.proc.returncode is not None:
                    break
                await asyncio.sleep(0.5)
            stopped.append(f"子进程 PID {state.proc.pid}")
        elif state.spec.port and _port_listening(state.spec.port):
            ext_pid = await _pid_on_port(state.spec.port)
            if ext_pid:
                await _kill_tree(ext_pid)
                stopped.append(f"外部进程 PID {ext_pid}")
        _append_log(state, f"(已停止 {'; '.join(stopped) or '本就未运行'})")
        return {"stopped": True, "detail": stopped}


def service_status(state: ServiceState) -> dict:
    ours = state.proc is not None and state.proc.returncode is None
    port_up = _port_listening(state.spec.port) if state.spec.port else None
    if ours:
        status = "running"
    elif port_up:
        status = "external"   # 端口有服务但不是本控制台启动
    else:
        status = "stopped"
    return {
        "name": state.spec.name,
        "label": state.spec.label,
        "status": status,
        "pid": state.proc.pid if ours else None,
        "port": state.spec.port,
        "port_up": port_up,
        "uptime_sec": int(time.time() - state.started_at) if ours and state.started_at else None,
        "note": state.spec.health_note,
        "log_lines": len(state.logs),
    }


# ---------------------------------------------------------------------------
# HTTP API + GUI
# ---------------------------------------------------------------------------

app = FastAPI(title="Smart Test Launcher")


@app.get("/api/services")
async def list_services():
    # spec 现算：知识库清单改了之后新库立刻出现在控制台上（进程状态按端口探测，
    # 所以上一次控制台留下的实例也能被接管，显示为「外部实例」）。
    return {"services": [service_status(_state(spec.name)) for spec in _default_services()]}


@app.post("/api/services/{name}/{action}")
async def service_action(name: str, action: str):
    if _service_spec(name) is None:
        raise HTTPException(status_code=404, detail=f"未知服务: {name}")
    if action == "start":
        return await start_service(name)
    if action == "stop":
        return await stop_service(name)
    if action == "restart":
        await stop_service(name)
        await asyncio.sleep(1)
        return await start_service(name)
    raise HTTPException(status_code=400, detail=f"未知操作: {action}")


@app.post("/api/all/{action}")
async def all_actions(action: str):
    if action not in ("start", "stop"):
        raise HTTPException(status_code=400, detail="仅支持 start/stop")
    results = {}
    order = [spec.name for spec in _default_services()]
    for name in (order if action == "start" else reversed(order)):
        try:
            if action == "start":
                results[name] = await start_service(name)
                await asyncio.sleep(2)  # 按依赖顺序错峰启动
            else:
                results[name] = await stop_service(name)
        except HTTPException as exc:
            results[name] = {"error": exc.detail}
    return {"results": results}


@app.get("/api/logs/{name}")
async def get_logs(name: str, after: int = 0):
    state = _state(name)
    if state is None:
        raise HTTPException(status_code=404, detail=f"未知服务: {name}")
    lines = list(state.logs)
    chunk = lines[after:]
    return {"lines": chunk, "next": after + len(chunk), "total": len(lines)}


@app.api_route(LLM_PROXY_PATH + "/{path:path}", methods=["GET", "POST"])
async def llm_proxy(path: str, request: Request):
    """把 LLM 请求代转到上游并补上上游要求的请求头（LightRAG 专用）。

    只转发对话/模型这类 OpenAI 兼容路径，认证头由调用方（LightRAG）自己带——
    这里不持有 key，也就不给"控制台变成开放代理"留口子。流式响应原样透传。
    """
    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(status_code=403, detail="该转发端点仅限本机调用")

    upstream = _llm_upstream()
    if not upstream["base_url"]:
        raise HTTPException(status_code=503, detail="没有配置上游 LLM 端点（设置页「模型」）")

    headers = {
        name: value for name, value in request.headers.items()
        if name.lower() in ("authorization", "content-type", "accept", "user-agent")
    }
    headers.update(upstream["headers"])
    body = await request.body()
    client = httpx.AsyncClient(timeout=None, trust_env=False)
    try:
        upstream_resp = await client.send(client.build_request(
            request.method, f"{upstream['base_url']}/{path}",
            content=body, headers=headers,
        ), stream=True)
    except Exception as exc:  # noqa: BLE001 — 上游不通要给一句人话，别 500 堆栈
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"上游 LLM 不可达: {exc}") from exc

    async def relay():
        try:
            async for chunk in upstream_resp.aiter_raw():
                yield chunk
        finally:
            await upstream_resp.aclose()
            await client.aclose()

    # content-encoding 必须原样带走：aiter_raw 给的是**未解压**的字节，丢了这行
    # 客户端就自己去 utf-8 解码 gzip 流（实测：'utf-8' codec can't decode byte 0x8b）。
    passthrough = {
        name: value for name, value in upstream_resp.headers.items()
        if name.lower() in ("content-type", "content-encoding", "cache-control")
    }
    return StreamingResponse(relay(), status_code=upstream_resp.status_code,
                            headers=passthrough)


@app.get("/api/logs/{name}/file")
async def download_logs(name: str):
    state = SERVICES.get(name)
    if state is None:
        raise HTTPException(status_code=404, detail=f"未知服务: {name}")
    path = _log_path(state)
    if not path.exists():
        # 该服务还一行都没输出过：用内存缓冲补一份，避免"日志文件不存在"的误导
        try:
            path.write_text("\n".join(state.logs) + "\n", encoding="utf-8")
        except OSError:
            pass
    if not path.exists():
        raise HTTPException(status_code=404, detail="暂无日志文件")
    return JSONResponse({"path": str(path)})


PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>智能测试平台 · 服务控制台</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: "Segoe UI", "Microsoft YaHei", sans-serif; background:#0f1115; color:#e6e8ee; }
  header { display:flex; align-items:center; gap:14px; padding:14px 20px; background:#161a22; border-bottom:1px solid #232936; }
  header h1 { font-size:16px; font-weight:600; }
  header .sub { color:#8b93a7; font-size:12px; }
  header .spacer { flex:1; }
  button { border:1px solid #2a3140; background:#1c2230; color:#e6e8ee; border-radius:6px; padding:6px 12px; font-size:12px; cursor:pointer; }
  button:hover { background:#252d3d; }
  button.primary { background:#2563eb; border-color:#2563eb; }
  button.primary:hover { background:#1d4ed8; }
  button.danger { color:#f87171; border-color:#7f1d1d; }
  button:disabled { opacity:.45; cursor:not-allowed; }
  main { display:grid; grid-template-columns: 380px 1fr; gap:14px; padding:14px 20px; height:calc(100vh - 59px); }
  .cards { display:flex; flex-direction:column; gap:10px; overflow-y:auto; }
  .card { background:#161a22; border:1px solid #232936; border-radius:10px; padding:12px 14px; cursor:pointer; }
  .card.selected { border-color:#2563eb; }
  .card .row1 { display:flex; align-items:center; gap:8px; }
  .dot { width:9px; height:9px; border-radius:50%; }
  .dot.running { background:#22c55e; box-shadow:0 0 6px #22c55e; }
  .dot.external { background:#eab308; }
  .dot.stopped { background:#4b5563; }
  .card .name { font-size:13px; font-weight:600; }
  .card .meta { color:#8b93a7; font-size:11px; margin-top:4px; }
  .card .btns { display:flex; gap:6px; margin-top:8px; }
  .logpanel { background:#0b0d12; border:1px solid #232936; border-radius:10px; display:flex; flex-direction:column; overflow:hidden; }
  .logpanel .bar { display:flex; align-items:center; gap:10px; padding:10px 14px; border-bottom:1px solid #232936; font-size:12px; color:#8b93a7; }
  .logpanel pre { flex:1; overflow:auto; padding:12px 14px; font:12px/1.55 Consolas, monospace; white-space:pre-wrap; word-break:break-all; }
  .badge { font-size:10px; padding:2px 8px; border-radius:99px; border:1px solid #2a3140; }
  label.chk { display:flex; gap:6px; align-items:center; font-size:12px; color:#8b93a7; cursor:pointer; }
</style>
</head>
<body>
<header>
  <h1>智能测试平台 · 服务控制台</h1>
  <span class="sub" id="summary"></span>
  <div class="spacer"></div>
  <button class="primary" onclick="allAction('start')">全部启动</button>
  <button class="danger" onclick="allAction('stop')">全部停止</button>
  <button onclick="openPlatform()">打开平台</button>
</header>
<main>
  <div class="cards" id="cards"></div>
  <div class="logpanel">
    <div class="bar">
      <span id="logTitle">选择左侧服务查看日志</span>
      <div class="spacer" style="flex:1"></div>
      <label class="chk"><input type="checkbox" id="autoscroll" checked>自动滚动</label>
      <button onclick="clearView()">清屏</button>
    </div>
    <pre id="logview"></pre>
  </div>
</main>
<script>
let services = [], selected = null, logOffset = 0;

async function refresh() {
  const r = await fetch('/api/services'); const d = await r.json();
  services = d.services;
  const running = services.filter(s=>s.status==='running').length;
  const ext = services.filter(s=>s.status==='external').length;
  document.getElementById('summary').textContent =
    `${running} 运行中 · ${ext} 外部实例 · ${services.length} 服务`;
  renderCards();
}

function statusText(s) {
  if (s.status==='running') return '运行中 · PID ' + s.pid + (s.uptime_sec!=null ? ' · ' + fmt(s.uptime_sec) : '');
  if (s.status==='external') return '外部实例占用 :' + s.port;
  return '已停止';
}

function renderCards() {
  const el = document.getElementById('cards');
  el.innerHTML = '';
  for (const s of services) {
    const c = document.createElement('div');
    c.className = 'card' + (selected===s.name ? ' selected' : '');
    c.innerHTML = `
      <div class="row1">
        <span class="dot ${s.status}"></span>
        <span class="name">${s.label}</span>
        ${s.port ? `<span class="badge">:${s.port}</span>` : ''}
      </div>
      <div class="meta">${statusText(s)}<br>${s.note||''}</div>
      <div class="btns">
        <button onclick="event.stopPropagation();act('${s.name}','start')">启动</button>
        <button onclick="event.stopPropagation();act('${s.name}','restart')">重启</button>
        <button class="danger" onclick="event.stopPropagation();act('${s.name}','stop')">停止</button>
      </div>`;
    c.onclick = () => selectService(s.name);
    el.appendChild(c);
  }
}

function selectService(name) {
  selected = name; logOffset = 0;
  document.getElementById('logview').textContent = '';
  document.getElementById('logTitle').textContent = name + ' 日志';
  renderCards(); pollLogs();
}

async function pollLogs() {
  if (!selected) return;
  const r = await fetch(`/api/logs/${selected}?after=${logOffset}`);
  const d = await r.json();
  if (d.lines.length) {
    const v = document.getElementById('logview');
    v.textContent += d.lines.join('\n') + '\n';
    if (document.getElementById('autoscroll').checked) v.scrollTop = v.scrollHeight;
  }
  logOffset = d.next;
}

async function act(name, action) {
  const btns = event.target; btns.disabled = true;
  try {
    const r = await fetch(`/api/services/${name}/${action}`, {method:'POST'});
    if (!r.ok) { const e = await r.json(); alert(e.detail || '操作失败'); }
  } finally { setTimeout(()=>btns.disabled=false, 1500); refresh(); }
}

async function allAction(action) {
  if (!confirm(action==='start' ? '启动全部服务？' : '停止全部服务？')) return;
  await fetch(`/api/all/${action}`, {method:'POST'});
  setTimeout(refresh, 1000);
}

function openPlatform() { window.open('http://localhost:5013', '_blank'); }
function clearView() { document.getElementById('logview').textContent=''; }
function fmt(sec) {
  if (sec < 60) return sec + 's';
  if (sec < 3600) return Math.floor(sec/60) + 'm' + (sec%60) + 's';
  return Math.floor(sec/3600) + 'h' + Math.floor(sec%3600/60) + 'm';
}

refresh();
setInterval(refresh, 3000);
setInterval(pollLogs, 1500);
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(PAGE)


async def _autostart() -> None:
    # LAUNCHER_SKIP_AUTOSTART=1：只接管、不动手。用于"改了控制台自己但不想打断
    # 正在跑的服务"——新控制台起来后，那些服务会显示为「外部实例」，一样能重启/停止。
    if os.environ.get("LAUNCHER_SKIP_AUTOSTART") == "1":
        print("[launcher] LAUNCHER_SKIP_AUTOSTART=1：跳过自启动，只接管已有服务")
        return
    for state in SERVICES.values():
        if state.spec.autostart:
            try:
                await start_service(state.spec.name)
                await asyncio.sleep(2)
            except HTTPException:
                pass


@app.on_event("startup")
async def on_start():
    for spec in _default_services():
        SERVICES[spec.name] = ServiceState(spec=spec)
    # 提前同步一次「RAG 设置」页：知识库可能是上一次控制台留下的进程（external），
    # 那种情况下不会有 start_service 的机会去同步。
    print(f"[launcher] {_sync_lightrag_ui()}")
    asyncio.create_task(_autostart())


if __name__ == "__main__":
    if os.environ.get("LAUNCHER_NO_BROWSER") != "1":
        webbrowser.open(f"http://localhost:{LAUNCHER_PORT}")
    uvicorn.run(app, host="0.0.0.0", port=LAUNCHER_PORT, log_config=None)
