from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    doubao_api_key: str = ""
    openai_api_key: str = ""  # GPT-4o multimodal model (Phase 4)
    enable_pdf_multimodal: bool = True  # Multimodal mode toggle (Phase 4)
    langgraph_api_url: str = "http://localhost:2026"
    workspace_dir: Path = Path(__file__).parent.parent.parent.parent / "workspace"

    # Resilience settings (Phase 7)
    circuit_breaker_fail_max: int = 5
    circuit_breaker_reset_timeout: int = 30
    retry_max_attempts: int = 3
    retry_initial_delay: float = 1.0
    retry_max_delay: float = 30.0

    # MCP
    docling_mcp_url: str = "http://localhost:8976/sse"

    # wiki-mcp (Phase 3)
    wiki_mcp_command: str = "npx"
    wiki_mcp_args: str = "tsx D:/llm-wiki/wiki-mcp/src/index.ts --config=C:/llm_test2/wiki-mcp-config.json"
    wiki_mcp_config_path: str = "C:/llm_test2/wiki-mcp-config.json"

    # Graphify MCP (Phase 5 - Web Agent component-aware mode)
    graphify_mcp_command: str = "npx"
    graphify_mcp_args: str = "graphify serve"

    # GitNexus MCP (Phase 6 - API Agent code knowledge graph)
    gitnexus_mcp_command: str = "node"
    gitnexus_mcp_args: str = "D:/prpm/72codegraph/gitnexus/dist/cli/index.js mcp"

    # Web MCP (Phase 15 - Playwright Test MCP server)
    web_mcp_root: str = ""  # Directory with package.json for MCP server; computed default in property

    # SQLite (local dev — no PostgreSQL required)
    sqlite_db: str = "smart_test_platform.db"

    @property
    def database_url(self) -> str:
        db_path = Path(__file__).parent.parent.parent.parent / self.sqlite_db
        return f"sqlite+aiosqlite:///{db_path}"

    @property
    def web_mcp_root_resolved(self) -> Path:
        """Resolve web_mcp_root, defaulting to workspace/default/web."""
        if self.web_mcp_root:
            return Path(self.web_mcp_root)
        return self.workspace_dir / "default" / "web"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
