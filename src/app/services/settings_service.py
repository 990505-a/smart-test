"""Settings service (设置模块): namespaced KV with env fallback and .env sync."""

from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.config import settings as env_settings
from src.app.db.models.setting import SettingKV

# Model settings keys -> env var names used by the agent processes.
# The settings page renders only the main model fields; the remaining keys stay
# in the map so their values round-trip untouched and keep syncing to .env
# (LLM_PROVIDER is derived from LLM_BASE_URL in model_factory).
MODEL_KEYS: dict[str, str] = {
    "llm_model": "LLM_MODEL",
    "llm_base_url": "LLM_BASE_URL",
    "llm_api_key": "LLM_API_KEY",
    "llm_context_window": "LLM_CONTEXT_WINDOW",
    "llm_max_output_tokens": "LLM_MAX_OUTPUT_TOKENS",
    "llm_supports_vision": "LLM_SUPPORTS_VISION",
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
    "lightrag_working_dir": "LIGHTRAG_WORKING_DIR",
    # LightRAG 的 LLM 绑定（实体抽取/生成用）。留空各自回退平台主模型——
    # 过去启动器把它写死成 api.deepseek.com，配的却是别家的 key，入库/检索必 401。
    "lightrag_llm_base_url": "LIGHTRAG_LLM_BASE_URL",
    "lightrag_llm_model": "LIGHTRAG_LLM_MODEL",
    "lightrag_llm_api_key": "LIGHTRAG_LLM_API_KEY",
    "lightrag_embedding_base_url": "LIGHTRAG_EMBEDDING_BASE_URL",
    "lightrag_embedding_model": "LIGHTRAG_EMBEDDING_MODEL",
    "lightrag_embedding_api_key": "LIGHTRAG_EMBEDDING_API_KEY",
    "lightrag_embedding_dim": "LIGHTRAG_EMBEDDING_DIM",
    "codebase_memory_exe": "CODEBASE_MEMORY_EXE",
    "codebase_graph_port": "CODEBASE_GRAPH_PORT",
    "codebase_schedule_enabled": "CODEBASE_SCHEDULE_ENABLED",
    "codebase_interval_hours": "CODEBASE_INTERVAL_HOURS",
    "codebase_analyze_enabled": "CODEBASE_ANALYZE_ENABLED",
    "unity_mcp_url": "UNITY_MCP_URL",
    "unity_mcp_transport": "UNITY_MCP_TRANSPORT",
    "unity_mcp_command": "UNITY_MCP_COMMAND",
    "unity_mcp_server": "UNITY_MCP_SERVER",
    # Lua 复位钩子（见 core/config.py 的说明）：游戏自带 Lua 热更时用它做秒级复位
    "memory_enabled": "MEMORY_ENABLED",
    "api_auto_max_repair": "API_AUTO_MAX_REPAIR",
}

# Langfuse（测评追踪）-> env var names。自建实例的 key 对是程序进出
# Langfuse 的凭证；public key 不脱敏（Langfuse 界面上本来就可见，方便核对
# 是哪个项目），secret key 必须脱敏。
LANGFUSE_KEYS: dict[str, str] = {
    "langfuse_enabled": "LANGFUSE_ENABLED",
    "langfuse_base_url": "LANGFUSE_BASE_URL",
    "langfuse_public_key": "LANGFUSE_PUBLIC_KEY",
    "langfuse_secret_key": "LANGFUSE_SECRET_KEY",
    "langfuse_environment": "LANGFUSE_ENVIRONMENT",
}

SECRET_KEYS = {"llm_api_key", "deepseek_api_key",
               "lightrag_llm_api_key", "lightrag_embedding_api_key",
               "langfuse_secret_key", "langfuse_monitor_secret_key", "judge_api_key"}

# LLM 裁判（测评打分）-> env var names。三个都可以留空：留空表示**继承主 LLM**
# （见 eval/scorers.py 的 judge_endpoint_from_values），界面上必须把这件事说清楚，
# 否则用户看到"judge：glm-4.7"会以为自己配过。
JUDGE_KEYS: dict[str, str] = {
    "judge_model": "JUDGE_MODEL",
    "judge_base_url": "JUDGE_BASE_URL",
    "judge_api_key": "JUDGE_API_KEY",
}

# Langfuse 监控（日常智能体使用链路）-> env var names。
# 与测评用的 LANGFUSE_* **分开**：日常排查看监控组织，跑测评只看测评组织，
# 两边的 trace 不混在一起。见 monitoring/tracing.py。
LANGFUSE_MONITOR_KEYS: dict[str, str] = {
    "langfuse_monitor_enabled": "LANGFUSE_MONITOR_ENABLED",
    "langfuse_monitor_base_url": "LANGFUSE_MONITOR_BASE_URL",
    "langfuse_monitor_public_key": "LANGFUSE_MONITOR_PUBLIC_KEY",
    "langfuse_monitor_secret_key": "LANGFUSE_MONITOR_SECRET_KEY",
    "langfuse_monitor_environment": "LANGFUSE_MONITOR_ENVIRONMENT",
}

_ENV_PATH = Path(__file__).parent.parent.parent.parent / ".env"


def read_env_file(env_names: list[str]) -> dict[str, str]:
    """从仓库 .env 里读原始值。

    为什么设置页要用它而不是 `env_settings`：容器里的环境变量被 compose 覆盖过
    （比如 LANGFUSE_BASE_URL 在容器内是 host.docker.internal，而 .env 里是人能用的
    127.0.0.1）。设置页是给人看的、也是往 .env 里写的，两边保持同一视角才不会
    「显示一个地址、保存成另一个地址」。
    """
    values: dict[str, str] = {}
    if not _ENV_PATH.exists():
        return values
    wanted = set(env_names)
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        name = name.strip()
        if name in wanted:
            values[name] = value.strip()
    return values


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
                raw = getattr(env_settings, key, "")
                # 布尔归一化为小写：前端下拉框的值是 "true"/"false"，
                # str(False) 的 "False" 匹配不上会显示成空。
                if raw is True:
                    merged[key] = "true"
                elif raw is False:
                    merged[key] = "false"
                else:
                    merged[key] = str(raw or "")
        return merged

    async def _effective(self, namespace: str, keys: dict[str, str]) -> dict[str, str]:
        """设置页保存的值优先，其次 .env 文件，最后进程环境。

        评测/裁判/监控都**必须**走这里而不是直接读 ``settings.*``：设置页存的是
        DB + .env，进程环境变量在重启前不会变，直接读进程环境就会出现
        「设置页改完不生效，必须重启容器」这种坑；容器部署里进程环境还可能是
        更早的一份 .env（compose 只在创建容器时注入），于是页面显示的模型名和
        agent 实际在跑的模型不是同一个——这正是「judge：glm-4.7」的成因。
        """
        merged = await self.get_namespace(namespace, keys)
        from_file = read_env_file(list(keys.values()))
        result: dict[str, str] = {}
        for key, env_name in keys.items():
            stored = await self.get(namespace, key)
            if stored is not None:
                result[key] = stored.strip()
            elif env_name in from_file:
                result[key] = from_file[env_name].strip()
            else:
                result[key] = str(merged.get(key) or "").strip()
        return result

    async def langfuse_values(self) -> dict[str, str]:
        """生效中的 Langfuse（测评）配置。"""
        return await self._effective("langfuse", LANGFUSE_KEYS)

    async def monitor_langfuse_values(self) -> dict[str, str]:
        """生效中的 Langfuse（监控）配置——日常智能体使用链路专用。"""
        return await self._effective("langfuse_monitor", LANGFUSE_MONITOR_KEYS)

    async def model_values(self) -> dict[str, str]:
        """生效中的主 LLM 配置（与 agent 进程 model_factory 同一优先级）。

        裁判/监控在「继承主 LLM」时必须读这里，而不是 ``settings.llm_model``：
        进程环境可能是过期的一份（容器只在创建时注入 .env），那样解析出来的
        模型名和 agent 实际在跑的模型就会分叉。
        """
        return await self._effective("model", MODEL_KEYS)

    async def judge_values(self) -> dict[str, str]:
        """生效中的 LLM 裁判配置（设置页保存的值优先，其次 .env）。

        和 langfuse_values 同样的理由：网页触发的测评要立刻按新配置打分，
        不能等容器重启。留空的项表示"继承主 LLM"，由调用方回退。
        """
        return await self._effective("judge", JUDGE_KEYS)

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
