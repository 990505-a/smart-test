"""Codebase graph search tools for TestCase Agent.

Wraps the codebase-memory MCP exe (via services.codebase_service.cbm_call)
so the agent can query the indexed code knowledge graph of the repo mounted
for the current conversation (/repo/, configurable.repo_path).

Project naming rule matches codebase-memory's default (drive + path
segments joined by '-'): "E:/m72-publish/m72" -> "E-m72-publish-m72".
"""

import json

from langchain.tools import tool
from langgraph.config import get_config

_MAX_RESULT_CHARS = 12000


def _project_and_repo() -> tuple[str, str]:
    """Return (project, repo_path) for the repo mounted on this run."""
    try:
        config = get_config()
    except RuntimeError:
        return "", ""
    repo = (config.get("configurable") or {}).get("repo_path", "") or ""
    if not repo:
        return "", ""
    project = repo.replace(":/", "-").replace("/", "-")
    return project, repo


def _format(payload: dict) -> str:
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if len(text) > _MAX_RESULT_CHARS:
        text = text[:_MAX_RESULT_CHARS] + "\n...(结果过长已截断，请用更精确的 pattern 或 file_pattern 缩小范围)"
    return text


@tool
async def search_codebase(pattern: str, file_pattern: str = "", semantic: bool = False) -> str:
    """Search the indexed code knowledge graph of the mounted repository.

    Graph-augmented code search: finds text matches then enriches them with
    definitions, callers and structural ranking — much better than plain grep
    when you need "where is this defined / who calls this".

    Requires the repo to be indexed first (代码图谱页); if not indexed, an
    error will tell you — fall back to grep/glob/read_file on /repo/ instead.

    Args:
        pattern: Search pattern (function/class/keyword name).
        file_pattern: Optional glob to restrict files (e.g. "*.lua", "*.cs").
        semantic: When true, use vector similarity search instead of literal
            matching — useful when the exact identifier name is unknown.
    """
    from src.app.services import codebase_service

    project, repo = _project_and_repo()
    if not repo:
        return ("Error: 未挂载代码仓库，无法查询代码图谱。"
                "请让用户在聊天页选择仓库后重新发送。")

    if semantic:
        keywords = [k for k in pattern.replace(",", " ").split() if k]
        result = await codebase_service.cbm_call(
            "search_graph",
            {"project": project, "semantic_query": keywords or [pattern], "limit": 20},
        )
    else:
        args: dict = {"project": project, "pattern": pattern, "limit": 20}
        if file_pattern:
            args["file_pattern"] = file_pattern
        result = await codebase_service.cbm_call("search_code", args)

    if not result.get("success"):
        return (f"Error: 代码图谱查询失败（仓库 {repo}）：{result.get('error')}\n"
                "可能原因：该仓库尚未建立索引。请改用 grep/glob/read_file 直接检索 /repo/，"
                "并建议用户在「代码图谱」页为该仓库建库。")
    return _format(result.get("data", {}))
