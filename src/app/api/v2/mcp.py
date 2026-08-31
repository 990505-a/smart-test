"""MCP module routes: configured MCP servers, live health checks, tool lists.

The MCP servers themselves are agent infrastructure (stdio FastMCP
processes spawned per connection); these routes make them observable
from the UI.
"""

import asyncio
import sys

from fastapi import APIRouter, HTTPException

from src.app.api.v2.auth import CurrentUserDep
from src.app.db.schemas.common import SuccessResponse
from src.app.mcp.mcp_client import get_mcp_client

router = APIRouter(prefix="/mcp")

_CHECK_TIMEOUT = 20.0


def _server_registry() -> dict[str, dict]:
    """Static view of the configured MCP servers."""
    from src.app.core.config import settings

    return {
        "rag": {
            "transport": "stdio",
            "endpoint": f"{sys.executable} -m src.app.mcp_servers.rag_server",
            "purpose": "LightRAG 检索/知识库入库（RAG 模块，依赖启动器中的 lightrag :5014）",
        },
        "codebase-memory": {
            "transport": "stdio",
            "endpoint": f"{sys.executable} -m src.app.mcp_servers.codebase_memory_shim → {settings.codebase_memory_exe}",
            "purpose": "代码知识图谱（stdio 直连，经 python 垫片兼容 asyncio 管道；图谱管理见 /codebase 页）",
        },
    }


@router.get("/servers", response_model=SuccessResponse, summary="MCP 服务配置列表")
async def list_servers(user: CurrentUserDep):
    return SuccessResponse(success=True, data=[
        {"name": name, **info} for name, info in _server_registry().items()
    ])


@router.get("/servers/{name}/check", response_model=SuccessResponse,
            summary="连通性检测：尝试连接并列出该服务的工具")
async def check_server(name: str, user: CurrentUserDep):
    registry = _server_registry()
    if name not in registry:
        raise HTTPException(status_code=404, detail=f"未知 MCP 服务: {name}")

    async def _check() -> dict:
        client = await get_mcp_client()
        tools = await asyncio.wait_for(client.get_tools(server_name=name), timeout=_CHECK_TIMEOUT)
        return {"ok": True, "tool_count": len(tools),
                "tools": sorted(t.name for t in tools), "error": None}

    try:
        result = await _check()
    except TimeoutError:
        result = {"ok": False, "tool_count": 0, "tools": [],
                  "error": f"连接超时（{_CHECK_TIMEOUT:.0f}s），服务未启动或不可达"}
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "tool_count": 0, "tools": [], "error": str(exc)[:500]}
    return SuccessResponse(success=True, data={"name": name, **result,
                                               "endpoint": registry[name]["endpoint"]})
