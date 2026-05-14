import asyncio

from langchain_mcp_adapters.client import MultiServerMCPClient

client = MultiServerMCPClient(
    {
        "playwright-api": {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@executeautomation/playwright-mcp-server"],
        },
    }
)

playwright_api_tools = asyncio.new_event_loop().run_until_complete(client.get_tools())
