from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    deepseek_api_key: str = ""
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
    wiki_mcp_args: str = "tsx D:/llm-wiki/wiki-mcp/src/index.ts --config=D:/llm-wiki/wiki-mcp/wiki-mcp-config.json"
    wiki_mcp_config_path: str = "D:/llm-wiki/wiki-mcp/wiki-mcp-config.json"

    # Graphify MCP (Phase 5 - Web Agent component-aware mode)
    graphify_mcp_command: str = "npx"
    graphify_mcp_args: str = "graphify serve"

    # GitNexus MCP (Phase 6 - API Agent code knowledge graph)
    gitnexus_mcp_command: str = "node"
    gitnexus_mcp_args: str = "D:/prpm/72codegraph/gitnexus/dist/cli/index.js mcp"

    # PostgreSQL (Phase 8) -- per D-01, D-02
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "smart_test_platform"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
