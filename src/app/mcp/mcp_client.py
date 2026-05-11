"""MCP client configuration for external tool services.

Phase 1 configures connection strings but agents don't use MCP tools yet.
MCP services (Docling, Graphify, Playwright) are non-blocking dependencies.
"""
from langchain_mcp_adapters.client import MultiServerMCPClient
from app.core.config import settings


async def get_mcp_client() -> MultiServerMCPClient:
    """Create and return an MCP client configured with all tool servers.

    Services are configured but not required to be running in Phase 1.
    The client handles connection failures gracefully.
    """
    client = MultiServerMCPClient(
        {
            "docling": {
                "transport": "sse",
                "url": settings.docling_mcp_url,
            },
            # Graphify and Playwright use stdio transport.
            # They will be configured with actual command paths when installed.
            # For Phase 1, only Docling (SSE) is configured.
            # "graphify": {
            #     "transport": "stdio",
            #     "command": "graphify",
            #     "args": ["serve"],
            # },
            # "playwright": {
            #     "transport": "stdio",
            #     "command": "npx",
            #     "args": ["@anthropic/mcp-playwright"],
            # },
        }
    )
    return client
