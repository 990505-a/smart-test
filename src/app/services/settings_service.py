"""Settings service (设置模块): namespaced KV with env fallback and .env sync."""

from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.config import settings as env_settings
from src.app.db.models.setting import SettingKV

# Model settings keys -> env var names used by the agent processes.
# The settings page renders only the text/vision model fields; the remaining
# keys stay in the map so their values round-trip untouched and keep syncing
# to .env (LLM_PROVIDER is derived from LLM_BASE_URL in model_factory).
MODEL_KEYS: dict[str, str] = {
    "llm_model": "LLM_MODEL",
    "llm_base_url": "LLM_BASE_URL",
    "llm_api_key": "LLM_API_KEY",
    "vision_model": "VISION_MODEL",
    "vision_base_url": "VISION_BASE_URL",
    "vision_api_key": "VISION_API_KEY",
    "llm_context_window": "LLM_CONTEXT_WINDOW",
    "llm_reasoning_effort": "LLM_REASONING_EFFORT",
    "deepseek_api_key": "DEEPSEEK_API_KEY",
    "deepseek_model": "DEEPSEEK_MODEL",
}

# Platform integration keys -> env var names
PLATFORM_KEYS: dict[str, str] = {
    "lark_cli_bin": "LARK_CLI_BIN",
    "lark_cli_identity": "LARK_CLI_IDENTITY",
    "feishu_mindnote_id": "FEISHU_MINDNOTE_ID",
    "feishu_mindnote_parent_node": "FEISHU_MINDNOTE_PARENT_NODE",
    "feishu_folder_token": "FEISHU_FOLDER_TOKEN",
    "feishu_template_mindnote_id": "FEISHU_TEMPLATE_MINDNOTE_ID",
    "lightrag_base_url": "LIGHTRAG_BASE_URL",
    "lightrag_embedding_base_url": "LIGHTRAG_EMBEDDING_BASE_URL",
    "lightrag_embedding_model": "LIGHTRAG_EMBEDDING_MODEL",
    "lightrag_embedding_api_key": "LIGHTRAG_EMBEDDING_API_KEY",
    "codebase_memory_exe": "CODEBASE_MEMORY_EXE",
    "codebase_graph_port": "CODEBASE_GRAPH_PORT",
    "codebase_schedule_enabled": "CODEBASE_SCHEDULE_ENABLED",
    "codebase_interval_hours": "CODEBASE_INTERVAL_HOURS",
    "game_repo_path": "GAME_REPO_PATH",
    "game_client_repo": "GAME_CLIENT_REPO",
    "unity_host": "UNITY_HOST",
    "unity_port": "UNITY_PORT",
    "everos_enabled": "EVEROS_ENABLED",
    "everos_port": "EVEROS_PORT",
    "everos_embedding_api_key": "EVEROS_EMBEDDING_API_KEY",
    "everos_embedding_base_url": "EVEROS_EMBEDDING_BASE_URL",
    "everos_embedding_model": "EVEROS_EMBEDDING_MODEL",
    "api_auto_max_repair": "API_AUTO_MAX_REPAIR",
}

SECRET_KEYS = {"llm_api_key", "vision_api_key", "deepseek_api_key",
               "lightrag_embedding_api_key", "everos_embedding_api_key"}

_ENV_PATH = Path(__file__).parent.parent.parent.parent / ".env"


class SettingsService:
    """Read/write namespaced settings; env values serve as defaults."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, namespace: str, key: str) -> str | None:
        result = await self.db.execute(
            select(SettingKV).where(SettingKV.namespace == namespace, SettingKV.key == key)
        )
        row = result.scalars().first()
        return row.value if row else None

    async def set(self, namespace: str, key: str, value: str | None) -> SettingKV:
        result = await self.db.execute(
            select(SettingKV).where(SettingKV.namespace == namespace, SettingKV.key == key)
        )
        row = result.scalars().first()
        if row is None:
            row = SettingKV(
                namespace=namespace, key=key, value=value,
                is_secret="true" if key in SECRET_KEYS else "false",
            )
            self.db.add(row)
        else:
            row.value = value
        await self.db.flush()
        return row

    async def get_namespace(self, namespace: str, defaults: dict[str, str]) -> dict[str, str | None]:
        """Return every known key with DB override falling back to env default."""
        result = await self.db.execute(select(SettingKV).where(SettingKV.namespace == namespace))
        stored = {row.key: row.value for row in result.scalars().all()}
        merged: dict[str, str | None] = {}
        for key, env_name in defaults.items():
            if key in stored:
                merged[key] = stored[key]
            else:
                merged[key] = str(getattr(env_settings, key, "") or "")
        return merged

    async def set_many(self, namespace: str, values: dict[str, str]) -> None:
        for key, value in values.items():
            if value is None:
                continue
            # Masked secrets (****) mean "keep the current value"
            if key in SECRET_KEYS and set(value) == {"*"}:
                continue
            await self.set(namespace, key, str(value))

    # -- .env sync so LangGraph agent processes pick up changes on restart ---

    @staticmethod
    def sync_env_file(values: dict[str, str], key_map: dict[str, str]) -> list[str]:
        """Persist settings into the repo .env; returns the env names written."""
        lines: list[str] = []
        if _ENV_PATH.exists():
            lines = _ENV_PATH.read_text(encoding="utf-8").splitlines()
        written: list[str] = []
        for key, value in values.items():
            env_name = key_map.get(key)
            if not env_name or value is None:
                continue
            if key in SECRET_KEYS and set(value) == {"*"}:
                continue
            pattern = re.compile(rf"^\s*#?\s*{re.escape(env_name)}\s*=")
            new_line = f"{env_name}={value}"
            for i, line in enumerate(lines):
                if pattern.match(line):
                    lines[i] = new_line
                    break
            else:
                lines.append(new_line)
            written.append(env_name)
        if written:
            _ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return written

    # -- secret resolution (masked form values -> real values) ----------------

    async def _real_value(self, namespace: str, key: str) -> str:
        """Current real value for a settings key: DB row first, env fallback."""
        stored = await self.get(namespace, key)
        if stored:
            return stored
        return str(getattr(env_settings, key, "") or "")

    async def resolve_masked(self, namespace: str, values: dict[str, str]) -> dict[str, str]:
        """Replace masked secrets (********) with their real stored values.

        Used by preset-save and connectivity-test endpoints: the form only
        ever holds masked secrets for unchanged keys, but those operations
        need the real key server-side. Non-secret and non-masked values pass
        through untouched.
        """
        resolved: dict[str, str] = {}
        for key, value in values.items():
            if key in SECRET_KEYS and value and set(value) == {"*"}:
                resolved[key] = await self._real_value(namespace, key)
            else:
                resolved[key] = str(value)
        return resolved

    # -- model presets (模型预设): one JSON list in the model_presets namespace --

    PRESET_NAMESPACE = "model_presets"
    PRESET_KEY = "list"

    async def list_presets(self) -> list[dict]:
        """Return [{name, values, saved_at}]; values carry REAL secrets —
        callers must mask_secrets() before returning them to the frontend."""
        import json

        result = await self.db.execute(
            select(SettingKV).where(
                SettingKV.namespace == self.PRESET_NAMESPACE,
                SettingKV.key == self.PRESET_KEY,
            )
        )
        row = result.scalars().first()
        if not row or not row.value:
            return []
        try:
            data = json.loads(row.value)
            return data if isinstance(data, list) else []
        except (ValueError, TypeError):
            return []

    async def save_preset(self, name: str, values: dict[str, str]) -> dict:
        """Upsert a preset by name. values must already be secret-resolved."""
        import json
        from datetime import datetime

        name = name.strip()
        if not name:
            raise ValueError("预设名称不能为空")
        presets = await self.list_presets()
        entry = {
            "name": name,
            "values": {k: str(v) for k, v in values.items() if v is not None},
            "saved_at": datetime.now().isoformat(timespec="seconds"),
        }
        kept = [p for p in presets if p.get("name") != name]
        kept.append(entry)
        kept.sort(key=lambda p: p.get("saved_at", ""))
        await self.set(self.PRESET_NAMESPACE, self.PRESET_KEY, json.dumps(kept, ensure_ascii=False))
        return entry

    async def get_preset(self, name: str) -> dict | None:
        for preset in await self.list_presets():
            if preset.get("name") == name:
                return preset
        return None

    async def delete_preset(self, name: str) -> bool:
        import json

        presets = await self.list_presets()
        kept = [p for p in presets if p.get("name") != name]
        if len(kept) == len(presets):
            return False
        await self.set(self.PRESET_NAMESPACE, self.PRESET_KEY, json.dumps(kept, ensure_ascii=False))
        return True


def mask_secrets(values: dict[str, str | None]) -> dict[str, str | None]:
    """Mask secret values for display."""
    masked = dict(values)
    for key in SECRET_KEYS:
        if masked.get(key):
            masked[key] = "********"
    return masked
