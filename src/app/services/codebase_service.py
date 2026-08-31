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

from src.app.core.config import settings
from src.app.db.database import async_session_factory
from src.app.db.models.codebase import CodebaseIndexRun, CodebaseRepo
from src.app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

_CBM_TIMEOUT = 45.0
_INDEX_TIMEOUT = 1800.0  # 大仓库全量索引可能很慢
_LAYOUT_TIMEOUT = 90.0
_DAEMON_BOOT_TIMEOUT = 20.0

INDEX_MODES = ("fast", "moderate", "full")
FILE_TYPE_MODES = ("all", "include", "exclude")


# ===========================================================================
# stdio MCP core (unchanged behavior from the previous version)
# ===========================================================================

_client = None
_tools: dict | None = None


def shim_command() -> tuple[list[str], dict[str, str]]:
    """stdio 连接命令：经 python 垫片拉起 exe（见 codebase_memory_shim.py 的兼容性说明）。"""
    root = Path(__file__).resolve().parents[3]
    return (
        [sys.executable, "-m", "src.app.mcp_servers.codebase_memory_shim"],
        {"CODEBASE_MEMORY_EXE": settings.codebase_memory_exe,
         "PYTHONPATH": str(root)},
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
    try:
        tools = await _tools_map()
        tool = tools.get(tool_name)
        if tool is None:
            return {"success": False, "error": f"codebase-memory 无工具 {tool_name}"}
        result = await asyncio.wait_for(tool.ainvoke(args), timeout=timeout)
        data = _unwrap(result)
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
        return {"success": False,
                "error": f"codebase-memory 调用失败 ({settings.codebase_memory_exe}): {exc}"}


def _reset_client() -> None:
    global _client, _tools
    _client = None
    _tools = None


# ===========================================================================
# CLI mode (一锤子调用) — 平台模块全部走这条路
# ===========================================================================
# exe 的 `cli <tool> <json>` 模式：stdout 是纯 JSON、stderr 是日志，无会话
# 生命周期问题。stdio MCP 会话（cbm_call，经垫片）偶发在 index_repository
# 长调用上挂起（子进程已退出而客户端不觉察），故平台自身的索引/查询改走
# CLI；cbm_call 仅供 Agent 的 search_codebase 工具继续使用。

def cbm_cli_sync(tool_name: str, args: dict, timeout: float = _CBM_TIMEOUT,
                 on_log=None) -> dict:
    """同步 CLI 调用；永不抛异常。调用方用 asyncio.to_thread 包裹。

    on_log: 可选回调（每行 stderr 日志调用一次），用于索引进度透出。
    stdout/stderr 各由独立线程排水（communicate 会与手动读 stderr 抢管道，
    在 Windows 上引发 NULL buffer 崩溃）；主线程按截止时间看护，超时杀进程。
    """
    import threading
    try:
        proc = subprocess.Popen(
            [settings.codebase_memory_exe, "cli", tool_name,
             json.dumps(args, ensure_ascii=False)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"CLI 启动失败: {exc}"}

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
                "error": f"CLI 无输出 (exit={proc.returncode}): {err_tail}"}
    try:
        return {"success": True, "data": json.loads(out)}
    except json.JSONDecodeError as exc:
        return {"success": False, "error": f"CLI 输出不是 JSON: {exc}"}


async def cbm_cli(tool_name: str, args: dict, timeout: float = _CBM_TIMEOUT,
                  on_log=None) -> dict:
    return await asyncio.to_thread(cbm_cli_sync, tool_name, args, timeout, on_log)


# ===========================================================================
# Project naming + exe operations
# ===========================================================================

def project_name(repo_path: str) -> str:
    """codebase-memory 默认项目名规则：E:/a/b -> E-a-b。"""
    return repo_path.replace(":/", "-").replace("/", "-")


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


async def status() -> dict:
    """exe 可用性 + 已索引项目 + 图守护进程状态。"""
    result = await cbm_cli("list_projects", {})
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
        "error": None if available else f"codebase-memory 不可达 ({settings.codebase_memory_exe})",
        "exe": settings.codebase_memory_exe,
        "projects": projects,
        "graph_daemon": await graph_daemon_status(),
    }


# ===========================================================================
# Graph daemon (exe --ui=true HTTP server) + layout proxy
# ===========================================================================

_graph_proc: subprocess.Popen | None = None
_graph_started_at: float | None = None


def _daemon_url(path: str = "/") -> str:
    return f"http://127.0.0.1:{settings.codebase_graph_port}{path}"


async def _daemon_up() -> bool:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(_daemon_url("/api/project-health"))
            return resp.status_code < 500
    except httpx.HTTPError:
        # /api/project-health 可能随版本变化；根路径兜底判定
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
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

    if not Path(settings.codebase_graph_exe).is_file():
        return {"success": False, "error": f"图守护 exe 不存在: {settings.codebase_graph_exe}"}

    # DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP:脱离 FastAPI 生命周期常驻。
    # 注意 stdin 必须保持打开(PIPE)：exe 默认是 stdio MCP 服务，stdin EOF(如
    # DEVNULL)会让它直接退出，--ui 的 HTTP 服务也随之关闭。
    # 用 graph_exe(官方版，内嵌 UI)而非 GS 定制版——GS 版构建未含 UI 资源，
    # --ui=true 时 HTTP 服务不会启动；两者共享同一份索引存储。
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        _graph_proc = subprocess.Popen(
            [settings.codebase_graph_exe, "--ui=true",
             f"--port={settings.codebase_graph_port}"],
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
        async with httpx.AsyncClient(timeout=_LAYOUT_TIMEOUT) as client:
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
        try:
            edge_rows = await _run_query(
                project,
                f"MATCH (a:Function)-[r:CALLS]->(b:Function) "
                f"WHERE a.file_path =~ '{rx}' AND b.file_path =~ '{rx}' "
                f"RETURN a.qualified_name AS s, b.qualified_name AS t, type(r) AS rel LIMIT 200")
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": f"目录子图查询失败: {exc}"}
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
        "last_index_at": repo.last_index_at.isoformat() if repo.last_index_at else None,
        "last_index_mode": repo.last_index_mode,
    }


async def _probe_project(project: str) -> dict | None:
    """按项目名探测索引是否存在（返回 nodes/edges 等信息；不存在返回 None）。

    exe 的 list_projects 只枚举“已注册”的项目——经 CLI 建立的索引（如
    index_repository 一锤子调用）能按名字访问但不进列表，所以对受管仓库
    必须用 index_status 逐个探测，否则会误判“未建库”。
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
            if info is None:
                info = await _probe_project(name)  # list_projects 未枚举时按名探测
            repos.append(_repo_payload(r, info))
        return {"success": True, "repos": repos}


async def add_repo(repo_path: str, display_name: str | None = None,
                   file_type_mode: str = "all", file_types: list | None = None,
                   auto_increment: bool = True) -> dict:
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
                            auto_increment=auto_increment)
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
        await db.delete(repo)
        await db.commit()
    if delete_index:
        await cbm_cli("delete_project", {"project": project_name(path)})
    return {"success": True}


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
    t0 = time.time()
    try:
        if not Path(repo.repo_path).is_dir():
            await _finish_run(run_id, "failed", error=f"仓库目录不存在: {repo.repo_path}")
            return {"success": False, "error": f"仓库目录不存在: {repo.repo_path}"}

        if repo.file_type_mode != "all":
            _index_progress.update({"phase": "write_cbmignore"})
            err = write_cbmignore_block(repo.repo_path, repo.file_type_mode,
                                        repo.file_types or [])
            if err:
                await _finish_run(run_id, "failed", error=err)
                return {"success": False, "error": err}

        result = await cbm_cli("index_repository",
                               {"repo_path": repo.repo_path, "mode": mode},
                               timeout=_INDEX_TIMEOUT,
                               on_log=_make_progress_callback(repo.repo_path))
        duration = round(time.time() - t0, 1)
        if result.get("success"):
            data = result.get("data") if isinstance(result.get("data"), dict) else {}
            # index_repository 的响应含覆盖率等长列表，截断后存入 detail
            raw = json.dumps(data, ensure_ascii=False, default=str)
            await _finish_run(run_id, "success",
                              detail={"duration_s": duration, "raw": raw[:4000]})
            async with async_session_factory() as db:
                await db.execute(
                    sa_update(CodebaseRepo).where(CodebaseRepo.id == repo.id)
                    .values(last_index_at=_now(), last_index_mode=mode))
                await db.commit()
            return {"success": True, "duration_s": duration}
        error = str(result.get("error"))
        await _finish_run(run_id, "failed", detail={"duration_s": duration}, error=error)
        return {"success": False, "error": error}
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
                results.append({"repo": r["repo_path"], "status": "skipped"})
                continue
            async with async_session_factory() as db:
                repo = (await db.execute(select(CodebaseRepo)
                                         .where(CodebaseRepo.id == UUID(r["id"])))) \
                    .scalars().first()
            if repo is None:
                continue
            outcome = await _index_repo_locked(
                repo, r.get("last_index_mode") or "fast", trigger)
            results.append({"repo": r["repo_path"], **outcome})
    return {"success": True,
            "summary": f"本轮处理 {len(results)} 个仓库",
            "results": results}


# ===========================================================================
# Schedule config (interval-based, persisted in settings_kv)
# ===========================================================================

async def get_schedule() -> dict:
    async with async_session_factory() as db:
        stored = await SettingsService(db).get_namespace(
            "platform", {"codebase_schedule_enabled": "", "codebase_interval_hours": ""})
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

    from src.app.services.scheduler import scheduler_info
    info = scheduler_info()
    job = next((j for j in info.get("jobs", [])
                if j.get("id") == "codebase_incremental_index"), None)
    return {"success": True, "enabled": enabled, "interval_hours": hours,
            "next_run": job.get("next_run") if job else None}


async def save_schedule(enabled: bool, interval_hours: int) -> dict:
    if not 1 <= interval_hours <= 720:
        return {"success": False, "error": "间隔小时数需在 1-720 之间"}
    async with async_session_factory() as db:
        svc = SettingsService(db)
        await svc.set_many("platform", {
            "codebase_schedule_enabled": "true" if enabled else "false",
            "codebase_interval_hours": str(interval_hours),
        })
        await db.commit()

    settings.codebase_schedule_enabled = enabled
    settings.codebase_interval_hours = interval_hours

    from src.app.services.scheduler import reschedule_codebase
    reschedule_codebase(enabled, interval_hours)
    return {"success": True, "enabled": enabled, "interval_hours": interval_hours}
