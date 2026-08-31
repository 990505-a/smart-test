"""MCP client configuration for external tool services.

Active servers:
- rag / codebase-memory: transformation modules (stdio, spawned on demand)
"""
import sys

from langchain_mcp_adapters.client import MultiServerMCPClient
from ..core.config import settings


def _cbm_entry() -> dict:
    """codebase-memory stdio 配置（经垫片，见 codebase_memory_shim.py）。"""
    from ..services.codebase_service import shim_command

    command, env = shim_command()
    return {"transport": "stdio",
            "command": command[0], "args": command[1:], "env": env}


async def get_mcp_client() -> MultiServerMCPClient:
    """Create and return an MCP client configured with all tool servers.

    Services are configured but not required to be running.
    The client handles connection failures gracefully.
    """
    client = MultiServerMCPClient(
        {
            # RAG MCP → LightRAG server (:5014, 启动器常驻)
            "rag": {
                "transport": "stdio",
                "command": sys.executable,
                "args": ["-m", "src.app.mcp_servers.rag_server"],
            },
            # codebase-memory MCP → stdio 经 python 垫片直连 exe（按需拉起；
            # 垫片解决 exe 在 asyncio overlapped 管道下无响应的兼容问题）
            "codebase-memory": _cbm_entry(),
        }
    )
    return client
