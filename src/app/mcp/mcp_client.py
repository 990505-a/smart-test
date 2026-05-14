"""MCP client configuration for external tool services.

Phase 1 configures connection strings but agents don't use MCP tools yet.
MCP services (Docling, Graphify, Playwright) are non-blocking dependencies.
"""
from langchain_mcp_adapters.client import MultiServerMCPClient
from ..core.config import settings


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
            "wiki-mcp": {
                "transport": "stdio",
                "command": settings.wiki_mcp_command,
                "args": settings.wiki_mcp_args.split(),
            },
            # Graphify MCP (Phase 5 - Web Agent component-aware mode)
            "graphify": {
                "transport": "stdio",
                "command": settings.graphify_mcp_command,
                "args": settings.graphify_mcp_args.split(),
            },
            # GitNexus MCP (Phase 6 - API Agent code knowledge graph)
            "gitnexus": {
                "transport": "stdio",
                "command": settings.gitnexus_mcp_command,
                "args": settings.gitnexus_mcp_args.split(),
            },
            # Playwright uses CLI mode (not MCP) per D-04 decision.
            # "playwright": {
            #     "transport": "stdio",
            #     "command": "npx",
            #     "args": ["@anthropic/mcp-playwright"],
            # },
        }
    )
    return client
