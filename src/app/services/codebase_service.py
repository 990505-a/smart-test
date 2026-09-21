"""Codebase-memory service (代码图谱模块).

Standalone platform feature (no agent coupling): manages which local repos
are graph-indexed through the codebase-memory exe, materializes per-repo
file-type rules as a managed block in <repo>/.cbmignore, orchestrates
manual + scheduled (incremental) indexing with a global single-flight lock,
and proxies precomputed graph layout data from the exe's built-in HTTP UI
(``--ui=true``, default :9749).

Design:
- stdio MCP core (shim + cached client) unchanged: the exe is spawned on
  demand, one child per calling process.
- DB access follows everos_service: background jobs open their own
  sessions via async_session_factory; API reads go through the same helpers.
- Never raises at the API boundary: failures degrade to
  ``{"success": False, "error": ...}``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import httpx
from sqlalchemy import delete as sa_delete, select, update as sa_update

from src.app.core import breaker
from src.app.core.config import settings
from src.app.core.http import local_client
from src.app.db.database import async_session_factory
from src.app.db.models.codebase import (
    CodebaseImpactReport,
    CodebaseIndexRun,
    CodebaseRepo,
)
from src.app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

_CBM_TIMEOUT = 45.0
_INDEX_TIMEOUT = 1800.0  # 大仓库全量索引可能很慢
_LAYOUT_TIMEOUT = 90.0
_DAEMON_BOOT_TIMEOUT = 20.0

# exe 不在/起不来的时候，每次工具调用都要等满 45s。快速失败把它压成一次。
_cbm_guard = breaker.Guard("代码图谱 exe")

INDEX_MODES = ("fast", "moderate", "full")
FILE_TYPE_MODES = ("all", "include", "exclude")


# ===========================================================================
# stdio MCP core (unchanged behavior from the previous version)
# ===========================================================================

_client = None
_tools: dict | None = None


def _cbm_isolated_base() -> Path:
    """隔离目录的根：用户私有数据区（Windows %LOCALAPPDATA%，POSIX ~/.cache）。

    不能放仓库目录里：exe 对 daemon 运行时目录做「仅当前用户」的 ACL 校验
    且会检查整条祖先链，仓库路径到盘根的 ACL 通常太宽，直接被拒
    （"secure CLI coordination could not be created"）。"""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "smart-test-platform" / "cbm"


def cbm_process_env() -> dict[str, str]:
    """平台 exe 的隔离环境（CLI 直调与 stdio 垫片共用一份）。

    同一台机器可能还有别的 codebase 安装（别的版本、其他客户端拉起的
    daemon）。它们与平台这份共享默认 ~/.cache/codebase-memory-mcp 的激
    活锁，版本不同就互相拒绝（"conflicting CBM process is active"）。
    平台固定用自管目录，与机器上其他安装互不可见，也不受其影响。"""
    runtime, cache = _cbm_isolated_base() / "runtime", _cbm_isolated_base() / "cache"
    # exe 只在已存在的父目录下创建自己的 cbm-daemon-* 子目录，链必须先建好
    runtime.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    return {
        "CBM_RUNTIME_DIR": str(runtime),
        "CBM_CACHE_DIR": str(cache),
    }


def shim_command() -> tuple[list[str], dict[str, str]]:
    """stdio 连接命令：经 python 垫片拉起 exe（见 codebase_memory_shim.py 的兼容性说明）。"""
    root = Path(__file__).resolve().parents[3]
    return (
        [sys.executable, "-m", "src.app.mcp_servers.codebase_memory_shim"],
        {"CODEBASE_MEMORY_EXE": settings.codebase_memory_exe,
         "PYTHONPATH": str(root), **cbm_process_env()},
    )


async def _tools_map() -> dict:
    global _client, _tools
    if _tools is None:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        command, env = shim_command()
        _client = MultiServerMCPClient({
            "codebase-memory": {
                "transport": "stdio",
                "command": command[0],
                "args": command[1:],
                "env": env,
            }
        })
        tools = await asyncio.wait_for(_client.get_tools(), timeout=_CBM_TIMEOUT)
        _tools = {t.name: t for t in tools}
    return _tools


def _unwrap(result) -> object:
    """langchain-mcp-adapters 返回 [{"type":"text","text": "..."}] 内容块，解出 JSON。"""
    if isinstance(result, list) and result and isinstance(result[0], dict) and "text" in result[0]:
        text = "".join(b.get("text", "") for b in result if isinstance(b, dict))
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return result


async def cbm_call(tool_name: str, args: dict, timeout: float = _CBM_TIMEOUT) -> dict:
    """Call one codebase-memory tool over stdio; never raises."""
    if (reason := _cbm_guard.blocked()) is not None:
        return {"success": False, "error": reason}
    try:
        tools = await _tools_map()
        tool = tools.get(tool_name)
        if tool is None:
            return {"success": False, "error": f"codebase-memory 无工具 {tool_name}"}
        result = await asyncio.wait_for(tool.ainvoke(args), timeout=timeout)
        data = _unwrap(result)
        _cbm_guard.ok()
        if isinstance(data, (dict, list)):
            return {"success": True, "data": data}
        if isinstance(data, str):
            try:
                return {"success": True, "data": json.loads(data)}
            except json.JSONDecodeError:
                return {"success": True, "data": data}
        return {"success": True, "data": str(data)}
    except Exception as exc:  # noqa: BLE001 — optional dependency
        global _tools
        _tools = None  # 会话可能已死，下次重连
        _cbm_guard.fail()
        return {"success": False,
                "error": f"codebase-memory 调用失败 ({settings.codebase_memory_exe}): {exc}"}


def _reset_client() -> None:
    global _client, _tools
    _client = None
    _tools = None


# ===========================================================================
# CLI mode (一锤子调用) — 平台模块全部走这条路
# ===========================================================================
# exe 的 `cli <tool>` 模式：stdout 给结果、stderr 给日志，无会话生命周期问题。
# stdio MCP 会话（cbm_call，经垫片）偶发在 index_repository 长调用上挂起（子进程
# 已退出而客户端不觉察），故平台自身的索引/查询改走 CLI；cbm_call 仅供 Agent 的
# 代码图谱工具继续使用（agents/codebase/tools.py）。
#
# ⚠️ 官方 v0.11.0 起，读工具默认输出**给人看的紧凑树**；要机器可读的结构化 JSON
# 必须带 format=json。写工具（index_repository / delete_project）默认就是 JSON，
# 也不接受该参数。名单是对着 v0.11.0 `cli <tool> --help` 逐个核过的。
_TOOLS_WITH_JSON_FORMAT = frozenset({
    "list_projects", "search_graph", "search_code", "query_graph",
    "index_status", "trace_path", "get_code_snippet", "get_architecture",
})


def cbm_args(tool_name: str, args: dict) -> dict:
    """补上 CLI 侧的方言差异：读工具需要 format=json 才是结构化输出。"""
    payload = dict(args)
    if tool_name in _TOOLS_WITH_JSON_FORMAT:
        payload.setdefault("format", "json")
    return payload


def cbm_cli_sync(tool_name: str, args: dict, timeout: float = _CBM_TIMEOUT,
                 on_log=None) -> dict:
    """同步 CLI 调用；永不抛异常。调用方用 asyncio.to_thread 包裹。

    参数经 **stdin** 传：位置参数 JSON 自 v0.11.0 起 deprecated（会往 stderr 打
    警告并在未来版本移除），stdin 是官方推荐的三种写法之一，且不需要临时文件。
    on_log: 可选回调（每行 stderr 日志调用一次），用于索引进度透出。
    stdout/stderr 各由独立线程排水（communicate 会与手动读 stderr 抢管道，
    在 Windows 上引发 NULL buffer 崩溃）；主线程按截止时间看护，超时杀进程。
    """
    import threading
    payload = cbm_args(tool_name, args)
    try:
        proc = subprocess.Popen(
            [settings.codebase_memory_exe, "cli", tool_name],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, **cbm_process_env()})
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"CLI 启动失败: {exc}"}
    try:
        proc.stdin.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        proc.stdin.close()
    except (OSError, ValueError):
        pass  # 写不进去就让下面按"无输出"报错，错误信息里带 stderr 尾部

    stderr_lines: list[str] = []
    stdout_buf: dict = {}

    def _drain_err() -> None:
        try:
            for raw in iter(proc.stderr.readline, b""):
                line = raw.decode("utf-8", errors="replace").rstrip()
                stderr_lines.append(line)
                if on_log is not None:
                    try:
                        on_log(line)
                    except Exception:  # noqa: BLE001 — 进度回调不阻断
                        pass
        except (OSError, ValueError):
            pass

    def _drain_out() -> None:
        try:
            stdout_buf["data"] = proc.stdout.read()
        except (OSError, ValueError):
            stdout_buf["data"] = b""

    t_err = threading.Thread(target=_drain_err, daemon=True)
    t_out = threading.Thread(target=_drain_out, daemon=True)
    t_err.start()
    t_out.start()

    deadline = time.time() + timeout
    while proc.poll() is None and time.time() < deadline:
        time.sleep(0.2)
    if proc.poll() is None:
        proc.kill()
        proc.wait()
        return {"success": False, "error": f"CLI 调用超时 ({timeout}s)"}
    t_out.join(timeout=5)
    t_err.join(timeout=5)

    out = (stdout_buf.get("data") or b"").decode("utf-8", errors="replace").strip()
    if not out:
        err_tail = "\n".join(stderr_lines[-3:])[-300:]
        return {"success": False,
                "error": f"CLI 无输出 ({tool_name}, exit={proc.returncode}): {err_tail}"}
    try:
        return {"success": True, "data": json.loads(out)}
    except json.JSONDecodeError as exc:
        # 读工具若漏了 format=json，exe 会回紧凑树文本，这里要看得见是哪个工具
        return {"success": False,
                "error": f"CLI 输出不是 JSON ({tool_name}): {exc}；"
                         f"输出开头：{out[:120]}"}


async def cbm_cli(tool_name: str, args: dict, timeout: float = _CBM_TIMEOUT,
                  on_log=None, *, use_breaker: bool = True) -> dict:
    """exe 一锤子调用。

    ``use_breaker=False`` 给**长任务**用（全量索引 1800s）：它本来就要跑很久，失败
    一次也不能说明 exe 不可用，挂熔断会误伤。短查询走默认值，服务不在时立刻返回。
    """
    if use_breaker:
        if (reason := _cbm_guard.blocked()) is not None:
            return {"success": False, "error": reason}
    result = await asyncio.to_thread(cbm_cli_sync, tool_name, args, timeout, on_log)
    if use_breaker:
        if result.get("success"):
            _cbm_guard.ok()
        else:
            _cbm_guard.fail()
    return result


# ===========================================================================
# Project naming + exe operations
# ===========================================================================

def _normalize_project_path(path: str) -> str:
    """路径 → 项目名的纯字符串规则（拆出来是为了能在任意平台上测 Windows 盘符）。"""
    p = path.replace("\\", "/")
    p = re.sub(r"^([A-Za-z]):/", r"\1-", p)  # Windows 盘符 E:/ → E-
    return p.lstrip("/").replace("/", "-")


def project_name(repo_path: str) -> str:
    """exe 的项目名规则（官方 v0.11.0 实测）：realpath → 去首分隔符 → 分隔符换 '-'。

    ``/private/tmp/demo`` → ``private-tmp-demo``；``E:/a/b`` → ``E-a-b``。
    两个易错点：exe 先做 realpath（macOS 上 ``/tmp`` 会变成 ``/private/tmp``，
    所以必须同样 realpath 才能对上），且 POSIX 下首位斜杠不留下前导 '-'（旧
    GS 定制版的 ``replace("/", "-")`` 会得到 ``-private-...``）。

    真实名字以 exe 为准：索引完成后 exe 会回传 project，与这里不一致会记 warning
    （见 index_repository），免得上游改了归一化规则后平台静默查错项目。
    """
    return _normalize_project_path(os.path.realpath(repo_path))


async def exe_projects() -> list[dict]:
    """Indexed projects from the exe (CLI mode); [] when unreachable."""
    result = await cbm_cli("list_projects", {})
    if not result.get("success"):
        return []
    data = result.get("data") or {}
    raw = data.get("projects") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for p in raw:
        if isinstance(p, dict):
            out.append({"name": p.get("name") or p.get("project") or "",
                        "root_path": p.get("root_path") or "",
                        "nodes": p.get("nodes"), "edges": p.get("edges"),
                        "size_bytes": p.get("size_bytes")})
        elif p:
            out.append({"name": str(p), "root_path": "", "nodes": None,
                        "edges": None, "size_bytes": None})
    return out


async def install_info() -> dict:
    """平台自管安装的状态：装没装、什么版本、要不要升级（给就绪中心/页面用）。"""
    from src.app.services import cbm_install  # 局部导入：拉 httpx 不构成本模块的必需依赖

    try:
        asset = cbm_install.asset_tag()
        supported = True
    except cbm_install.InstallError:
        asset, supported = "", False
    installed = cbm_install.installed_version()
    target = settings.codebase_version
    return {
        "managed_dir": str(cbm_install.CBM_MANAGED_DIR),
        "installed_version": installed,
        "target_version": target,
        "asset": asset,
        "supported": supported,
        # 只有"记录了版本且与目标不同"才算能升级；没装过（None）是"该安装"
        "upgradable": bool(installed and installed != target),
        # .env 的 CODEBASE_MEMORY_EXE 优先级高于默认值：老配置还指着 GS 版时，平台会
        # 把新版装进 tools/codebase-memory/ 却依然去用旧路径 —— 这两个字段让界面能
        # 说清"装是装好了，但你指的地方不是这儿"。
        "configured_exe": settings.codebase_memory_exe,
        "using_managed": Path(settings.codebase_memory_exe) == cbm_install.managed_exe(),
    }


async def status() -> dict:
    """exe 可用性 + 已索引项目 + 图守护进程状态 + 自管安装状态。"""
    # daemon 空闲几分钟后会自己退出，下一次调用要付约一个 _DAEMON_BOOT_TIMEOUT
    # 的冷启动成本；机器忙或多个调用并发抢冷启动时，默认 45s 会被冲破——就绪中心
    # 隔一阵子探一次，恰好每次都撞冷启动。这里给 3 倍余量，冷启动永远兜得住。
    result = await cbm_cli("list_projects", {}, timeout=_DAEMON_BOOT_TIMEOUT * 3)
    available = bool(result.get("success"))
    projects: list[dict] = []
    if available:
        data = result.get("data") or {}
        raw = data.get("projects") if isinstance(data, dict) else data
        if isinstance(raw, list):
            for p in raw:
                if isinstance(p, dict):
                    projects.append({"name": p.get("name") or p.get("project") or "",
                                     "root_path": p.get("root_path") or "",
                                     "nodes": p.get("nodes"), "edges": p.get("edges"),
                                     "size_bytes": p.get("size_bytes")})
                elif p:
                    projects.append({"name": str(p), "root_path": "", "nodes": None,
                                     "edges": None, "size_bytes": None})
    return {
        "success": True,
        "available": available,
        # 用底层返回的原始错误：它区分得开"exe 不存在"、"调用超时"和"熔断中，
        # 30 秒内不再尝试"。之前这里一律改写成"不可达"，把原因吞掉了——
        # 前端只能反复看到一个笼统结论，也不知道平台其实已经停止重试。
        "error": None if available else (
            result.get("error") or f"codebase-memory 不可达 ({settings.codebase_memory_exe})"
        ),
        "exe": settings.codebase_memory_exe,
        "exe_present": Path(settings.codebase_memory_exe).is_file(),
        "projects": projects,
        "graph_daemon": await graph_daemon_status(),
        "install": await install_info(),
    }


# ===========================================================================
# Graph daemon (exe --ui=true HTTP server) + layout proxy
# ===========================================================================

_graph_proc: subprocess.Popen | None = None
_graph_started_at: float | None = None


def _daemon_url(path: str = "/") -> str:
    return f"http://127.0.0.1:{settings.codebase_graph_port}{path}"


async def _daemon_up() -> bool:
    """探活根路径（图 UI 首页，v0.11.0 实测 200）。<500 即视为"活着"，
    这样端口被别的服务占着也不至于误判为已就绪而不再拉起。"""
    try:
        async with local_client(timeout=3.0) as client:
            resp = await client.get(_daemon_url("/"))
            return resp.status_code < 500
    except httpx.HTTPError:
        return False


async def graph_daemon_status() -> dict:
    return {"up": await _daemon_up(), "port": settings.codebase_graph_port}


async def ensure_graph_daemon() -> dict:
    """确保 exe 的 HTTP 图服务在跑：先探活（含外部已启动的实例），不通则拉起。"""
    global _graph_proc, _graph_started_at
    if await _daemon_up():
        return {"success": True, "up": True, "spawned": False}

    exe = settings.codebase_memory_exe
    if not Path(exe).is_file():
        return {"success": False, "error": f"图服务 exe 不存在: {exe}（代码图谱页可一键安装）"}

    # 与 MCP/CLI 用的是**同一个二进制**：官方 v0.11.0 起图 UI 内嵌在每次构建里，
    # 不再需要旧的双 exe（GS 版索引 + 官方版出图）。
    # DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP:脱离 FastAPI 生命周期常驻。
    # 注意 stdin 必须保持打开(PIPE)：exe 默认是 stdio MCP 服务，stdin EOF(如
    # DEVNULL)会让它直接退出（v0.11.0 实测），--ui 的 HTTP 服务也随之关闭。
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        _graph_proc = subprocess.Popen(
            [exe, "--ui=true", f"--port={settings.codebase_graph_port}"],
            stdin=subprocess.PIPE,  # 保持打开：写端由本进程持有，不写入不关闭
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=flags, close_fds=True,
        )
        _graph_started_at = time.time()
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"图守护进程启动失败: {exc}"}

    deadline = time.time() + _DAEMON_BOOT_TIMEOUT
    while time.time() < deadline:
        if await _daemon_up():
            return {"success": True, "up": True, "spawned": True}
        await asyncio.sleep(1.0)
    return {"success": False,
            "error": f"图守护进程启动后未就绪 (:{settings.codebase_graph_port})"}


async def graph_layout(project: str, max_nodes: int = 2000) -> dict:
    """代理 exe 的 /api/layout：预计算坐标/颜色/状态的 nodes+edges。"""
    ensured = await ensure_graph_daemon()
    if not ensured.get("success"):
        return ensured
    try:
        async with local_client(timeout=_LAYOUT_TIMEOUT) as client:
            resp = await client.get(_daemon_url("/api/layout"),
                                    params={"project": project, "max_nodes": max_nodes})
            resp.raise_for_status()
            return {"success": True, "data": resp.json()}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"获取图数据失败: {exc}"}


# ===========================================================================
# 范围视图(大图专用):目录子图 / 符号邻域 — 经 query_graph(CLI)组装
# ===========================================================================
# /api/layout 对超大图(几十万节点)只能随机采样,采出来的节点彼此几乎没有
# 边,没法看。范围视图按需取真实子图:目录前缀(看一个模块)或符号名
# (看直接上下游),200 行/查询的上限正好控制规模。

def _parse_labels(raw) -> str:
    """labels(n) 返回 '["Function"]' 这样的 JSON 字符串,取出第一个。"""
    if isinstance(raw, str):
        try:
            arr = json.loads(raw)
            return str(arr[0]) if arr else ""
        except (json.JSONDecodeError, IndexError):
            return raw.strip('[]"')
    if isinstance(raw, list) and raw:
        return str(raw[0])
    return ""


async def _run_query(project: str, cypher: str) -> list[list]:
    result = await cbm_cli("query_graph", {"project": project, "query": cypher},
                           timeout=120)
    if not result.get("success"):
        raise RuntimeError(str(result.get("error")))
    data = result.get("data") or {}
    rows = data.get("rows") or []
    return rows if isinstance(rows, list) else []


def _compose_graph(node_rows: list[list], edge_rows: list[list],
                   node_cols: list[str], edge_cols: list[str]) -> dict:
    """由 query_graph 行组装前端可用的 {nodes, edges}(按 qualified_name 去重)。"""
    def col(name: str, cols: list[str]) -> int:
        return cols.index(name) if name in cols else -1

    nodes: list[dict] = []
    index: dict[str, int] = {}

    def add_node(name, label, file_path, qn, start_line) -> int:
        key = qn or f"{file_path}::{name}"
        if key in index:
            return index[key]
        idx = len(nodes)
        index[key] = idx
        nodes.append({"id": idx, "x": 0.0, "y": 0.0, "z": 0.0,
                      "label": label or "?", "name": name or "",
                      "file_path": file_path, "qualified_name": qn,
                      "start_line": start_line, "end_line": None,
                      "size": 8.0, "color": "", "in_calls": 0})
        return idx

    ni = {c: col(c, node_cols) for c in ("name", "label", "fp", "qn", "line")}
    for row in node_rows:
        add_node(row[ni["name"]] if ni["name"] >= 0 else "",
                 _parse_labels(row[ni["label"]]) if ni["label"] >= 0 else "",
                 row[ni["fp"]] if ni["fp"] >= 0 else None,
                 row[ni["qn"]] if ni["qn"] >= 0 else None,
                 row[ni["line"]] if ni["line"] >= 0 else None)

    edges: list[dict] = []
    ei = {c: col(c, edge_cols) for c in ("s", "t", "rel",
                                         "s_name", "s_label", "s_fp", "s_qn",
                                         "t_name", "t_label", "t_fp", "t_qn")}

    def add_edge_stub(qn: str) -> int:
        # 边端点只有 qualified_name 时(目录模式 CALLS 查询),名字取尾段
        return add_node(str(qn).rsplit(".", 1)[-1], "Function", None, qn, None)

    for row in edge_rows:
        src = add_node(row[ei["s_name"]], _parse_labels(row[ei["s_label"]]),
                       row[ei["s_fp"]], row[ei["s_qn"]], None) \
            if ei["s_name"] >= 0 else add_edge_stub(row[ei["s"]])
        tgt = add_node(row[ei["t_name"]], _parse_labels(row[ei["t_label"]]),
                       row[ei["t_fp"]], row[ei["t_qn"]], None) \
            if ei["t_name"] >= 0 else add_edge_stub(row[ei["t"]])
        edges.append({"source": src, "target": tgt,
                      "type": row[ei["rel"]] if ei["rel"] >= 0 else "RELATED"})
        nodes[tgt]["in_calls"] = nodes[tgt].get("in_calls", 0) + 1
    return {"nodes": nodes, "edges": edges, "total_nodes": len(nodes)}


def _cy(text: str) -> str:
    """Cypher 字符串字面量转义。"""
    return text.replace("\\", "\\\\").replace("'", "\\'")


async def graph_subgraph(project: str, mode: str, value: str) -> dict:
    """范围视图:mode=dir(目录前缀子图) / symbol(符号直接上下游)。

    所有查询必须带节点标签限定(:Function 等)——93 万节点的图上不带标签
    的属性过滤是全图扫描(实测 100s+),带标签走索引(~1s)。
    """
    value = (value or "").strip().replace("\\", "/")
    if not value:
        return {"success": False, "error": "范围值不能为空"}

    if mode == "dir":
        rx = _cy(re.escape(value) + ".*")
        # 节点:按标签分查(每次都走标签索引),代码符号优先
        node_rows: list[list] = []
        for label, cap in (("Function", 150), ("Method", 50), ("Class", 40),
                           ("Route", 20), ("File", 30)):
            if len(node_rows) >= 280:
                break
            try:
                rows = await _run_query(
                    project,
                    f"MATCH (n:{label}) WHERE n.file_path =~ '{rx}' "
                    f"RETURN n.name AS name, labels(n) AS label, n.file_path AS fp, "
                    f"n.qualified_name AS qn, n.start_line AS line LIMIT {cap}")
            except Exception:  # noqa: BLE001 — 单标签失败不阻断
                rows = []
            node_rows.extend(rows)
        # 边:标签必须跟节点查询同一套。**不能写死 :Function** —— 调用关系的主力标签
        # 随语言而变，实测 ruoyi(Java) 的 CALLS 有 64588 条在 (Method)->(Method)、
        # (Function)->(Function) 只有 17 条；jynew(C#) 是 33965 对 249。写死 Function
        # 会让目录子图取到节点却一条边都没有，前端"不画度数为 0 的节点"于是画布空白。
        edge_rows: list[list] = []
        for label in ("Method", "Function", "Class"):
            if len(edge_rows) >= 200:
                break
            try:
                rows = await _run_query(
                    project,
                    f"MATCH (a:{label})-[r:CALLS]->(b:{label}) "
                    f"WHERE a.file_path =~ '{rx}' AND b.file_path =~ '{rx}' "
                    f"RETURN a.qualified_name AS s, b.qualified_name AS t, type(r) AS rel LIMIT 200")
            except Exception:  # noqa: BLE001 — 单标签失败不阻断（与节点查询同款）
                rows = []
            edge_rows.extend(rows)
        data = _compose_graph(node_rows, edge_rows,
                              ["name", "label", "fp", "qn", "line"], ["s", "t", "rel"])

    elif mode == "symbol":
        sym = _cy(value)
        rows: list = []
        # 依次在常见标签下找(带标签 = 走索引);Function 命中最常见
        for label in ("Function", "Method", "Class"):
            try:
                rows = await _run_query(
                    project,
                    f"MATCH (a:{label})-[r]->(b:{label}) WHERE a.name = '{sym}' OR b.name = '{sym}' "
                    f"RETURN a.name AS s_name, labels(a) AS s_label, a.file_path AS s_fp, "
                    f"a.qualified_name AS s_qn, type(r) AS rel, "
                    f"b.name AS t_name, labels(b) AS t_label, b.file_path AS t_fp, "
                    f"b.qualified_name AS t_qn LIMIT 200")
            except Exception as exc:  # noqa: BLE001
                return {"success": False, "error": f"符号邻域查询失败: {exc}"}
            if rows:
                break
        if not rows:
            return {"success": False,
                    "error": f"没有找到名为「{value}」的符号(或它没有任何连线)。试试精确的函数名,如 create / start。"}
        data = _compose_graph(
            [], rows, [],
            ["s_name", "s_label", "s_fp", "s_qn", "rel", "t_name", "t_label", "t_fp", "t_qn"])
    else:
        return {"success": False, "error": f"无效 mode: {mode}(可选 dir/symbol)"}

    if not data["nodes"]:
        return {"success": False, "error": f"范围「{value}」下没有任何节点,换个目录前缀试试。"}
    return {"success": True, "data": data}


# ===========================================================================
# .cbmignore managed block (file-type rules)
# ===========================================================================

_BEGIN = "# BEGIN smart-test-platform (managed — 修改文件类型配置会重写此块)"
_END = "# END smart-test-platform (managed)"
_BLOCK_RE = re.compile(
    re.escape(_BEGIN) + r".*?" + re.escape(_END) + r"\r?\n?", re.DOTALL)


def normalize_extensions(exts: list) -> list[str]:
    """['gs', '.LUA'] -> ['.gs', '.lua']（去重保序）。"""
    seen: dict[str, None] = {}
    for raw in exts or []:
        ext = str(raw).strip().lower()
        if not ext:
            continue
        if not ext.startswith("."):
            ext = "." + ext
        if re.fullmatch(r"\.[a-z0-9_+-]+", ext):
            seen[ext] = None
    return list(seen)


def _build_block(mode: str, exts: list[str]) -> str:
    lines = [_BEGIN]
    if mode == "include":
        # gitignore 反选：先排除一切，再放行目录（否则不向下遍历）与目标扩展名
        lines.append("*")
        lines.append("!*/")
        lines.extend(f"!*{ext}" for ext in exts)
    elif mode == "exclude":
        lines.extend(f"*{ext}" for ext in exts)
    lines.append(_END)
    return "\n".join(lines) + "\n"


def write_cbmignore_block(repo_path: str, mode: str, exts: list[str]) -> str | None:
    """把文件类型规则写进 <repo>/.cbmignore 的代管块，保留用户自有内容。

    mode=all 时移除代管块。返回 None 表示成功，否则为错误信息。
    """
    try:
        path = Path(repo_path) / ".cbmignore"
        existing = ""
        if path.is_file():
            existing = path.read_text(encoding="utf-8", errors="replace")

        stripped = _BLOCK_RE.sub("", existing).lstrip("\n")
        if mode == "all":
            new_content = stripped
        else:
            block = _build_block(mode, normalize_extensions(exts))
            new_content = (stripped + "\n" + block) if stripped.strip() else block

        tmp = path.with_suffix(".cbmignore.tmp")
        tmp.write_text(new_content, encoding="utf-8")
        os.replace(tmp, path)
        return None
    except Exception as exc:  # noqa: BLE001
        return f"写入 .cbmignore 失败: {exc}"


# ===========================================================================
# Repo CRUD (DB) — managed repository registry
# ===========================================================================

def _repo_payload(repo: CodebaseRepo, indexed: dict | None) -> dict:
    return {
        "id": str(repo.id),
        "repo_path": repo.repo_path,
        "display_name": repo.display_name,
        "project": project_name(repo.repo_path),
        "indexed": bool(indexed),
        "nodes": (indexed or {}).get("nodes"),
        "edges": (indexed or {}).get("edges"),
        "file_type_mode": repo.file_type_mode,
        "file_types": repo.file_types or [],
        "auto_increment": repo.auto_increment,
        "auto_analyze": repo.auto_analyze,
        "last_commit": repo.last_commit,
        "last_index_at": repo.last_index_at.isoformat() if repo.last_index_at else None,
        "last_index_mode": repo.last_index_mode,
    }


#: index_status 探测结果缓存：project -> (monotonic 时间戳, info|None)。
#: 为什么要缓存：list_repos 对**每个**受管仓库都可能探一次（见下），而每次探测是
#: 一次 exe 子进程调用（45s 超时）。仓库一多，刷新一次列表就是 N 次 spawn。
#: 索引只在“索引完成”那一刻变化，所以 TTL 只需要覆盖页面连续刷新的窗口——
#: 索引成功与删库都会显式失效（invalidate_probe_cache），不靠 TTL 兜正确性。
_probe_cache: dict[str, tuple[float, dict | None]] = {}
_PROBE_TTL = 30.0


def invalidate_probe_cache(project: str | None = None) -> None:
    """丢弃探测缓存（project 为 None 时清空）。索引完成 / 删库后调用。"""
    if project is None:
        _probe_cache.clear()
    else:
        _probe_cache.pop(project, None)


async def _probe_project_cached(project: str) -> dict | None:
    hit = _probe_cache.get(project)
    if hit is not None and (time.monotonic() - hit[0]) < _PROBE_TTL:
        return hit[1]
    info = await _probe_project(project)
    _probe_cache[project] = (time.monotonic(), info)
    return info


async def _probe_project(project: str) -> dict | None:
    """按项目名探测索引是否存在（返回 nodes/edges 等信息；不存在返回 None）。

    这是**唯一**能拿到 nodes/edges 的路径：exe 的 ``list_projects`` 只回
    name/root_path/branch（实测 v0.11.0），计数只在 ``index_status`` 里。
    受管仓库必须用它补全，否则前端拿不到图规模。
    """
    result = await cbm_cli("index_status", {"project": project})
    if not result.get("success"):
        return None
    data = result.get("data")
    if not isinstance(data, dict):
        return None
    # 索引不存在时 exe 会返回错误/错误型负载；有 nodes 即视为有效索引
    if data.get("error") or (data.get("nodes") is None and not data.get("status")):
        return None
    return {"name": project, "root_path": data.get("root_path") or "",
            "nodes": data.get("nodes"), "edges": data.get("edges"),
            "size_bytes": data.get("size_bytes")}


async def list_repos() -> dict:
    projects = {p["name"]: p for p in await exe_projects()}
    async with async_session_factory() as db:
        rows = (await db.execute(select(CodebaseRepo).order_by(CodebaseRepo.created_at))).scalars().all()
        repos = []
        for r in rows:
            name = project_name(r.repo_path)
            info = projects.get(name)
            # 「枚举到了」不等于「拿到计数」：list_projects 的条目没有 nodes/edges，
            # 只有 index_status 有。缺计数时必须补探 —— 否则前端拿到 nodes=null，
            # 大图会被当成小图走全量采样（/api/layout 随机采样巨型图只剩结构节点、
            # 且边为 0），表现为“图谱一片空白”。
            if info is None or info.get("nodes") is None:
                probed = await _probe_project_cached(name)
                # 探测失败（exe 不可达/索引不存在）时保留 list_projects 的条目，
                # 至少还能显示 root_path；探测成功则用带计数的覆盖。
                info = probed or info
            repos.append(_repo_payload(r, info))
        return {"success": True, "repos": repos}


async def add_repo(repo_path: str, display_name: str | None = None,
                   file_type_mode: str = "all", file_types: list | None = None,
                   auto_increment: bool = True, auto_analyze: bool = False) -> dict:
    path = (repo_path or "").strip().replace("\\", "/")
    if not path:
        return {"success": False, "error": "仓库路径不能为空"}
    if file_type_mode not in FILE_TYPE_MODES:
        return {"success": False, "error": f"无效 file_type_mode: {file_type_mode}"}
    exts = normalize_extensions(file_types or [])
    if file_type_mode == "include" and not exts:
        return {"success": False, "error": "include 模式必须指定至少一个扩展名"}
    if not Path(path).is_dir():
        return {"success": False, "error": f"目录不存在: {path}"}

    async with async_session_factory() as db:
        exists = (await db.execute(select(CodebaseRepo)
                                   .where(CodebaseRepo.repo_path == path))).scalars().first()
        if exists:
            return {"success": False, "error": f"仓库已存在: {path}"}
        repo = CodebaseRepo(repo_path=path, display_name=display_name or None,
                            file_type_mode=file_type_mode, file_types=exts,
                            auto_increment=auto_increment, auto_analyze=auto_analyze)
        db.add(repo)
        await db.commit()
        return {"success": True, "repo": _repo_payload(repo, None)}


async def update_repo(repo_id: str, **fields) -> dict:
    async with async_session_factory() as db:
        repo = (await db.execute(select(CodebaseRepo)
                                 .where(CodebaseRepo.id == UUID(str(repo_id))))).scalars().first()
        if repo is None:
            return {"success": False, "error": "仓库不存在"}
        if "display_name" in fields and fields["display_name"] is not None:
            repo.display_name = fields["display_name"] or None
        if "file_type_mode" in fields and fields["file_type_mode"] is not None:
            mode = fields["file_type_mode"]
            if mode not in FILE_TYPE_MODES:
                return {"success": False, "error": f"无效 file_type_mode: {mode}"}
            exts = normalize_extensions(fields.get("file_types") or [])
            if mode == "include" and not exts:
                return {"success": False, "error": "include 模式必须指定至少一个扩展名"}
            repo.file_type_mode = mode
            repo.file_types = exts
        elif fields.get("file_types") is not None:
            repo.file_types = normalize_extensions(fields["file_types"])
        if "auto_increment" in fields and fields["auto_increment"] is not None:
            repo.auto_increment = bool(fields["auto_increment"])
        if "auto_analyze" in fields and fields["auto_analyze"] is not None:
            repo.auto_analyze = bool(fields["auto_analyze"])
        await db.commit()
        return {"success": True}


async def delete_repo(repo_id: str, delete_index: bool = False) -> dict:
    async with async_session_factory() as db:
        repo = (await db.execute(select(CodebaseRepo)
                                 .where(CodebaseRepo.id == UUID(str(repo_id))))).scalars().first()
        if repo is None:
            return {"success": False, "error": "仓库不存在"}
        path = repo.repo_path
        await db.execute(sa_delete(CodebaseIndexRun)
                         .where(CodebaseIndexRun.repo_id == repo.id))
        # 影响报告同样要清：FK 的 ondelete 在 SQLite 上要 PRAGMA foreign_keys=ON
        # 才生效，本平台的库没开，所以级联一律显式写。
        await db.execute(sa_delete(CodebaseImpactReport)
                         .where(CodebaseImpactReport.repo_id == repo.id))
        await db.delete(repo)
        await db.commit()
    # 变更基线随仓库一起删，否则同一路径重新注册会拿旧清单做对比
    try:
        from src.app.services.codebase_analysis_service import _manifest_path
        _manifest_path(repo_id).unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass
    if delete_index:
        result = await cbm_cli("delete_project", {"project": project_name(path)})
        if not result.get("success"):
            return {"success": True, "index_deleted": False,
                    "index_error": result.get("error") or "索引删除失败"}
    # 索引没了，探测缓存里那条「已建库 + 计数」立刻作废
    invalidate_probe_cache(project_name(path))
    return {"success": True, "index_deleted": True}


# ===========================================================================
# Index orchestration — global single-flight lock + run history
# ===========================================================================

_index_lock = asyncio.Lock()
_indexing_repo: str | None = None  # 当前正在索引的仓库路径（UI 展示用）
_index_progress: dict = {}        # repo_path → {phase, last_line, started_at, live}

# exe 日志行如 `level=info msg=pipeline.discover files=601 elapsed_ms=120`
_LOG_MSG_RE = re.compile(r"msg=([A-Za-z0-9_.-]+)")


def _progress_snapshot() -> dict | None:
    """当前索引的进度快照（含已运行秒数）；无任务时 None。"""
    if not _index_progress.get("live"):
        return None
    snap = dict(_index_progress)
    snap["elapsed_s"] = round(time.time() - snap.get("started_at", time.time()), 1)
    return snap


def _make_progress_callback(repo_path: str):
    def _on_log(line: str) -> None:
        m = _LOG_MSG_RE.search(line)
        _index_progress.update({
            "repo_path": repo_path,
            "phase": m.group(1) if m else "",
            "last_line": line[:200],
            "started_at": _index_progress.get("started_at") or time.time(),
            "live": True,
        })
    return _on_log


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _record_run(repo_id, trigger: str, mode: str, status: str,
                      detail: dict | None = None, error: str | None = None) -> UUID | None:
    async with async_session_factory() as db:
        run = CodebaseIndexRun(repo_id=repo_id, trigger=trigger, mode=mode,
                               status=status, detail=detail, error=error,
                               finished_at=_now() if status != "running" else None)
        db.add(run)
        await db.commit()
        return run.id


async def _finish_run(run_id: UUID | None, status: str,
                      detail: dict | None = None, error: str | None = None) -> None:
    if run_id is None:
        return
    async with async_session_factory() as db:
        await db.execute(
            sa_update(CodebaseIndexRun)
            .where(CodebaseIndexRun.id == run_id)
            .values(status=status, detail=detail, error=error, finished_at=_now()))
        await db.commit()


async def _index_repo_locked(repo: CodebaseRepo, mode: str, trigger: str) -> dict:
    """执行一次索引（调用方必须已持有 _index_lock）。run 历史全程落库。"""
    global _indexing_repo
    _indexing_repo = repo.repo_path
    _index_progress.clear()
    _index_progress.update({"repo_path": repo.repo_path, "phase": "starting",
                            "last_line": "", "started_at": time.time(), "live": True})
    run_id = await _record_run(repo.id, trigger, mode, "running")
    # run_id 回传给调用方：定时轮次结束后要拿它把影响报告挂到这次索引上。
    run_ref = str(run_id) if run_id else None
    t0 = time.time()
    try:
        if not Path(repo.repo_path).is_dir():
            await _finish_run(run_id, "failed", error=f"仓库目录不存在: {repo.repo_path}")
            return {"success": False, "run_id": run_ref,
                    "error": f"仓库目录不存在: {repo.repo_path}"}

        if repo.file_type_mode != "all":
            _index_progress.update({"phase": "write_cbmignore"})
            err = write_cbmignore_block(repo.repo_path, repo.file_type_mode,
                                        repo.file_types or [])
            if err:
                await _finish_run(run_id, "failed", error=err)
                return {"success": False, "run_id": run_ref, "error": err}

        result = await cbm_cli("index_repository",
                               {"repo_path": repo.repo_path, "mode": mode},
                               timeout=_INDEX_TIMEOUT,
                               on_log=_make_progress_callback(repo.repo_path),
                               use_breaker=False)  # 长任务：失败一次不代表 exe 不可用
        duration = round(time.time() - t0, 1)
        if result.get("success"):
            data = result.get("data") if isinstance(result.get("data"), dict) else {}
            # 名字以 exe 为准：上游改了归一化规则时，这里会第一时间喊出来，
            # 否则表现为"所有图谱查询都查不到东西"，极难定位。
            actual = data.get("project")
            derived = project_name(repo.repo_path)
            if actual and actual != derived:
                logger.warning(
                    "codebase-memory 项目名与平台推导不一致：exe=%s 平台=%s（repo=%s）；"
                    "project_name() 的规则需要跟着上游更新", actual, derived, repo.repo_path)
            # index_repository 的响应含覆盖率等长列表，截断后存入 detail
            raw = json.dumps(data, ensure_ascii=False, default=str)
            await _finish_run(run_id, "success",
                              detail={"duration_s": duration, "raw": raw[:4000],
                                      "project": actual, "project_derived": derived})
            async with async_session_factory() as db:
                await db.execute(
                    sa_update(CodebaseRepo).where(CodebaseRepo.id == repo.id)
                    .values(last_index_at=_now(), last_index_mode=mode))
                await db.commit()
            # 计数变了：让下一次 list_repos 重新探一次，页面立刻看到新节点数
            invalidate_probe_cache(derived)
            return {"success": True, "run_id": run_ref, "duration_s": duration,
                    "project": actual or derived,
                    "project_mismatch": bool(actual and actual != derived)}
        error = str(result.get("error"))
        await _finish_run(run_id, "failed", detail={"duration_s": duration}, error=error)
        return {"success": False, "run_id": run_ref, "error": error}
    finally:
        _indexing_repo = None
        _index_progress["live"] = False


async def mark_stale_runs_failed() -> int:
    """服务启动时调用：把上次进程生命周期里遗留的 running 记录标记为失败。

    索引任务随进程死掉后不会有人回写状态，不清就永远挂在「进行中」。
    """
    async with async_session_factory() as db:
        result = await db.execute(
            sa_update(CodebaseIndexRun)
            .where(CodebaseIndexRun.status == "running")
            .values(status="failed", error="服务重启，任务中断",
                    finished_at=_now()))
        await db.commit()
        return result.rowcount or 0


async def read_cbmignore(repo_id: str) -> dict:
    """读取仓库根 .cbmignore 实际内容（配置值透明化）。"""
    async with async_session_factory() as db:
        repo = (await db.execute(select(CodebaseRepo)
                                 .where(CodebaseRepo.id == UUID(str(repo_id))))).scalars().first()
    if repo is None:
        return {"success": False, "error": "仓库不存在"}
    path = Path(repo.repo_path) / ".cbmignore"
    if not path.is_file():
        return {"success": True, "exists": False, "content": "",
                "managed_present": False}
    content = path.read_text(encoding="utf-8", errors="replace")
    return {"success": True, "exists": True, "content": content,
            "managed_present": "BEGIN smart-test-platform" in content}


async def start_index(repo_id: str, mode: str = "fast") -> dict:
    """手动索引：后台任务执行，立即返回。忙时明确报错。"""
    if mode not in INDEX_MODES:
        return {"success": False, "error": f"无效 mode: {mode}，可选 {INDEX_MODES}"}
    if _index_lock.locked():
        return {"success": False,
                "error": f"已有索引任务在运行（{_indexing_repo or '未知仓库'}），请稍后再试"}

    async with async_session_factory() as db:
        repo = (await db.execute(select(CodebaseRepo)
                                 .where(CodebaseRepo.id == UUID(str(repo_id))))).scalars().first()
        if repo is None:
            return {"success": False, "error": "仓库不存在"}
        repo_id_val, trigger = repo.id, "manual"

    async def _task() -> None:
        async with _index_lock:
            async with async_session_factory() as db:
                fresh = (await db.execute(select(CodebaseRepo)
                                          .where(CodebaseRepo.id == repo_id_val))).scalars().first()
            if fresh is not None:
                await _index_repo_locked(fresh, mode, trigger)

    asyncio.create_task(_task())
    return {"success": True, "started": True, "mode": mode}


async def list_runs(repo_id: str | None = None, limit: int = 30) -> dict:
    query = (select(CodebaseIndexRun, CodebaseRepo)
             .join(CodebaseRepo, CodebaseIndexRun.repo_id == CodebaseRepo.id)
             .order_by(CodebaseIndexRun.started_at.desc())
             .limit(max(1, min(limit, 200))))
    if repo_id:
        query = query.where(CodebaseIndexRun.repo_id == UUID(str(repo_id)))
    async with async_session_factory() as db:
        rows = (await db.execute(query)).all()
        runs = [{
            "id": str(run.id),
            "repo_id": str(run.repo_id),
            "repo_path": repo.repo_path,
            "display_name": repo.display_name,
            "trigger": run.trigger,
            "mode": run.mode,
            "status": run.status,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "detail": run.detail,
            "error": run.error,
        } for run, repo in rows]
        return {"success": True, "runs": runs, "indexing": _indexing_repo,
                "progress": _progress_snapshot()}


async def run_incremental_round(trigger: str = "scheduled") -> dict:
    """定时增量索引一轮：只处理已建库且 auto_increment 的仓库；未建库记 skipped。

    exe 对已建库仓库重跑 index_repository 即增量（内容哈希，只重解析变更文件）。
    """
    repos_result = await list_repos()
    repos = [r for r in repos_result.get("repos", []) if r.get("auto_increment")]
    if not repos:
        return {"success": True, "summary": "没有启用定时增量的仓库", "results": []}

    if _index_lock.locked():
        for r in repos:
            await _record_run(UUID(r["id"]), trigger, r.get("last_index_mode") or "fast",
                              "skipped", detail={"reason": "索引进程忙（手动索引进行中）"})
        return {"success": True, "summary": "手动索引进行中，本轮跳过", "results": []}

    results: list[dict] = []
    async with _index_lock:
        for r in repos:
            if not r.get("indexed"):
                await _record_run(UUID(r["id"]), trigger, "incremental", "skipped",
                                  detail={"reason": "未建全量索引，跳过增量"})
                results.append({"repo": r["repo_path"], "repo_id": r["id"],
                                "auto_analyze": False, "status": "skipped"})
                continue
            async with async_session_factory() as db:
                repo = (await db.execute(select(CodebaseRepo)
                                         .where(CodebaseRepo.id == UUID(r["id"])))) \
                    .scalars().first()
            if repo is None:
                continue
            outcome = await _index_repo_locked(
                repo, r.get("last_index_mode") or "fast", trigger)
            results.append({"repo": r["repo_path"], "repo_id": r["id"],
                            "auto_analyze": bool(r.get("auto_analyze")), **outcome})

    # 影响分析刻意放在索引锁**之外**：LLM 调用慢，占着锁会让手动索引排不进来。
    # 它失败也不影响上面的索引结果（run_impact_analysis 内部自己兜异常）。
    analyses: list[dict] = []
    if any(item.get("success") and item.get("auto_analyze") for item in results):
        try:
            from src.app.services.codebase_analysis_service import analyze_after_round
            analyses = await analyze_after_round(results, trigger=trigger)
        except Exception as exc:  # noqa: BLE001
            logger.warning("impact analysis round failed: %s", exc)

    summary = f"本轮处理 {len(results)} 个仓库"
    if analyses:
        done = sum(1 for a in analyses if a.get("status") == "success")
        summary += f"，影响分析 {done}/{len(analyses)} 份"
    return {"success": True, "summary": summary,
            "results": results, "analyses": analyses}


# ===========================================================================
# Schedule config (interval-based, persisted in settings_kv)
# ===========================================================================

async def get_schedule() -> dict:
    async with async_session_factory() as db:
        stored = await SettingsService(db).get_namespace(
            "platform", {"codebase_schedule_enabled": "", "codebase_interval_hours": "",
                         "codebase_analyze_enabled": ""})
    try:
        enabled = str(stored.get("codebase_schedule_enabled") or
                      settings.codebase_schedule_enabled).lower() in ("1", "true", "yes")
    except Exception:  # noqa: BLE001
        enabled = bool(settings.codebase_schedule_enabled)
    try:
        hours = int(str(stored.get("codebase_interval_hours") or
                        settings.codebase_interval_hours))
    except (TypeError, ValueError):
        hours = settings.codebase_interval_hours
    try:
        analyze = str(stored.get("codebase_analyze_enabled") or
                      settings.codebase_analyze_enabled).lower() in ("1", "true", "yes")
    except Exception:  # noqa: BLE001
        analyze = bool(settings.codebase_analyze_enabled)

    from src.app.services.scheduler import scheduler_info
    info = scheduler_info()
    job = next((j for j in info.get("jobs", [])
                if j.get("id") == "codebase_incremental_index"), None)
    return {"success": True, "enabled": enabled, "interval_hours": hours,
            "analyze_enabled": analyze,
            "next_run": job.get("next_run") if job else None}


async def save_schedule(enabled: bool, interval_hours: int,
                        analyze_enabled: bool | None = None) -> dict:
    if not 1 <= interval_hours <= 720:
        return {"success": False, "error": "间隔小时数需在 1-720 之间"}
    async with async_session_factory() as db:
        svc = SettingsService(db)
        values = {
            "codebase_schedule_enabled": "true" if enabled else "false",
            "codebase_interval_hours": str(interval_hours),
        }
        if analyze_enabled is not None:
            values["codebase_analyze_enabled"] = "true" if analyze_enabled else "false"
        await svc.set_many("platform", values)
        await db.commit()

    settings.codebase_schedule_enabled = enabled
    settings.codebase_interval_hours = interval_hours
    if analyze_enabled is not None:
        settings.codebase_analyze_enabled = analyze_enabled

    from src.app.services.scheduler import reschedule_codebase
    reschedule_codebase(enabled, interval_hours)
    return {"success": True, "enabled": enabled, "interval_hours": interval_hours,
            "analyze_enabled": bool(settings.codebase_analyze_enabled)}
