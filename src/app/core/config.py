from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    deepseek_api_key: str = ""
    doubao_api_key: str = ""
    langgraph_api_url: str = "http://localhost:2026"
    workspace_dir: Path = Path(__file__).parent.parent.parent.parent / "workspace"

    # LightRAG
    lightrag_port: int = 9621
    lightrag_llm_binding: str = "openai"
    lightrag_llm_model: str = "deepseek-chat"
    lightrag_llm_binding_host: str = "https://api.deepseek.com/v1"
    lightrag_embedding_binding: str = "ollama"
    lightrag_embedding_binding_host: str = "http://localhost:11434"
    lightrag_embedding_model: str = "qwen3-embedding:0.6b"
    lightrag_embedding_dim: int = 1024

    # MCP
    docling_mcp_url: str = "http://localhost:8976/sse"

    # wiki-mcp (Phase 3)
    wiki_mcp_command: str = "npx"
    wiki_mcp_args: str = "tsx D:/llm-wiki/wiki-mcp/src/index.ts --config=D:/llm-wiki/wiki-mcp/wiki-mcp-config.json"
    wiki_mcp_config_path: str = "D:/llm-wiki/wiki-mcp/wiki-mcp-config.json"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
