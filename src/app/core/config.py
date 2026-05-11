from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    deepseek_api_key: str = ""
    doubao_api_key: str = ""
    langgraph_api_url: str = "http://localhost:2026"
    workspace_dir: Path = Path(__file__).parent.parent.parent.parent / "workspace"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
