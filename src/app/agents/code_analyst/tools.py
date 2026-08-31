"""Code-analysis agent tools: codebase-memory graph queries.

与用例生成智能体共用一条 stdio MCP 会话路径（cbm_call）。工具面向代码
分析场景：定位符号、追调用链、按全名读源码；grep/glob/read_file 等文件
工具由 DeepAgents 后端直接提供（/repo/ 只读挂载），不在此重复。

未挂载仓库或仓库未建图谱时给出降级提示（改用 grep /repo/）。
"""

import json

from langchain.tools import tool
from langgraph.config import get_config

_MAX_RESULT_CHARS = 12000


def _project() -> str:
    """当前会话挂载仓库对应的图谱项目名；未挂载返回空串。"""
    try:
        config = get_config()
    except RuntimeError:
        return ""
    repo = (config.get("configurable") or {}).get("repo_path", "") or ""
    return repo.replace(":/", "-").replace("/", "-") if repo else ""


def _degraded(kind: str) -> str:
    return (f"Error: 无法使用代码图谱{kind}。可能原因：会话未挂载仓库，或该仓库尚未建索引。"
            "请改用 grep/glob/read_file 直接检索 /repo/；如需建库，"
            "建议用户在平台「代码图谱」页为该仓库完成一次索引。")


def _format(payload: dict) -> str:
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if len(text) > _MAX_RESULT_CHARS:
        text = text[:_MAX_RESULT_CHARS] + "\n...(结果过长已截断,请缩小范围或减小 depth/limit)"
    return text


@tool
async def trace_symbol(function_name: str, direction: str = "both", depth: int = 2) -> str:
    """Trace callers/callees of a symbol in the code knowledge graph.

    Answers "who calls X" / "what does X call" structurally — far more
    reliable than grep for call-chain and impact analysis.

    Args:
        function_name: Exact symbol name (short name, e.g. "create").
            If ambiguous, results are grouped per match.
        direction: "inbound" (谁调用它) | "outbound" (它调用谁) | "both".
        depth: 1-3 hops; keep small on huge repos.
    """
    from src.app.services import codebase_service

    project = _project()
    if not project:
        return _degraded("调用链追踪")
    depth = max(1, min(int(depth), 3))
    result = await codebase_service.cbm_call(
        "trace_path",
        {"project": project, "function_name": function_name,
         "direction": direction if direction in ("inbound", "outbound", "both") else "both",
         "depth": depth, "limit": 60},
        timeout=90,
    )
    if not result.get("success"):
        return f"Error: 调用链查询失败：{result.get('error')}\n{_degraded('调用链追踪')}"
    return _format(result.get("data", {}))


@tool
async def read_symbol(qualified_name: str) -> str:
    """Read the source code of a symbol by its qualified name from the graph.

    Use after search/trace gave you a `qualified_name` (e.g.
    "E-m72-publish-m72.server.pkg.grpc.route_server.start") — returns the
    definition source without guessing file paths.
    """
    from src.app.services import codebase_service

    project = _project()
    if not project:
        return _degraded("源码读取")
    result = await codebase_service.cbm_call(
        "get_code_snippet",
        {"project": project, "qualified_name": qualified_name},
        timeout=60,
    )
    if not result.get("success"):
        return f"Error: 源码读取失败：{result.get('error')}\n{_degraded('源码读取')}"
    return _format(result.get("data", {}))


@tool
async def repo_architecture(aspects: str = "overview") -> str:
    """Get the indexed repo's architecture overview from the code graph.

    Best FIRST tool for "看一下这个仓库/整体架构/模块划分" style questions:
    returns structure, packages, entry points, hotspots and (with
    aspects="clusters") de-facto module communities. Needs the repo indexed
    (代码图谱页); falls back to reading README files otherwise.
    """
    from src.app.services import codebase_service

    project = _project()
    if not project:
        return _degraded("架构总览")
    valid = {"overview", "structure", "hotspots", "clusters", "all"}
    aspect = aspects if aspects in valid else "overview"
    result = await codebase_service.cbm_call(
        "get_architecture", {"project": project, "aspects": [aspect]}, timeout=90)
    if not result.get("success"):
        return f"Error: 架构总览失败：{result.get('error')}\n{_degraded('架构总览')}"
    return _format(result.get("data", {}))


@tool
async def graph_search(query: str, semantic: bool = False, limit: int = 20) -> str:
    """Search symbols in the code knowledge graph (functions/classes/routes).

    Literal mode matches identifier names (supports regex); semantic mode
    finds symbols by meaning when the exact name is unknown (e.g. Chinese
    business terms). Returns qualified names for use with read_symbol /
    trace_symbol. The repo must be indexed first (代码图谱页).
    """
    from src.app.services import codebase_service

    project = _project()
    if not project:
        return _degraded("符号检索")
    limit = max(1, min(int(limit), 50))
    if semantic:
        keywords = [k for k in query.replace(",", " ").split() if k]
        result = await codebase_service.cbm_call(
            "search_graph",
            {"project": project, "semantic_query": keywords or [query], "limit": limit},
            timeout=90,
        )
    else:
        result = await codebase_service.cbm_call(
            "search_graph",
            {"project": project, "name_pattern": query, "limit": limit},
            timeout=60,
        )
    if not result.get("success"):
        return f"Error: 图谱检索失败：{result.get('error')}\n{_degraded('符号检索')}"
    return _format(result.get("data", {}))
