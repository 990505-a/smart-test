"""Chat-model factory for the agent.

One place that turns settings into a runnable chat model, so the default
model (agent bootstrap) and per-run variants stay consistent — the
reasoning-effort overrides, and the per-conversation model *preset* picked in
the chat page (see ``middleware/run_model.py``).  Provider selection is
derived — no manual switch:

- llm_base_url set  -> ANY OpenAI-compatible endpoint (OpenAI, SiliconFlow,
  OneAPI, OpenRouter, vLLM, Ollama's OpenAI shim, ...) via ChatOpenAI
- llm_base_url empty -> official DeepSeek API via langchain-deepseek

`effort` attaches a `reasoning_effort` model kwarg ("low"/"medium"/"high")
for reasoning-capable models; empty string sends nothing. If an endpoint
rejects the parameter, leave the effort unset.

`build_model_from_values()` is the one construction path that reads a plain
mapping instead of the global settings singleton; both `build_chat_model()`
and the preset/connectivity-test callers go through it.
"""

from __future__ import annotations

import uuid
from functools import lru_cache

from dotenv import dotenv_values
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_openai import ChatOpenAI

# 全仓统一用 "src.app.*" 这一种导入前缀。过去这里是个 try/except 双别名
# （LangGraph 进程插了 src/ 所以 "app.*" 能用，FastAPI 进程只能用 "src.app.*"），
# 结果是**同一进程里存在两个 Settings 对象**：热更改的是 app.core.config.settings，
# 而 case_docs_service 等读的是 src.app.core.config.settings —— 设置页改完不生效
# 且不报错。统一到 "src.app.*" 是因为它在两个进程里都能解析（两边 sys.path 都有
# ROOT），而 "app.*" 只在插了 src/ 的进程里能解析。
from src.app.core.config import settings

VALID_EFFORTS = ("low", "medium", "high")

# OpenCode Go 网关（opencode.ai/zen/go/v1）要求每个请求携带一个稳定的
# x-opencode-session 头用于路由/缓存分片，缺失时返回 400 MissingSessionID。
# 进程级 UUID 满足"稳定"要求（进程重启才变化）。
_GO_SESSION_ID = uuid.uuid4().hex


def _go_session_headers(base_url: str | None) -> dict | None:
    """OpenCode Go 端点需要 x-opencode-session；其他端点不附加多余头。"""
    if base_url and "opencode.ai" in base_url.lower():
        return {"x-opencode-session": _GO_SESSION_ID}
    return None


class ReasoningChatOpenAI(ChatOpenAI):
    """ChatOpenAI that preserves OpenAI-compatible providers' reasoning stream.

    langchain-openai targets the official OpenAI API and deliberately drops
    non-standard response fields: DeepSeek/GLM/Qwen-style endpoints stream
    their chain-of-thought as ``reasoning_content`` deltas, which
    ``_convert_delta_to_message_chunk`` discards — the agent pays for
    reasoning tokens that never reach LangGraph stream events (and thus the
    frontend ThinkingBlock).

    This subclass re-attaches the field to ``AIMessage.additional_kwargs``
    (the same convention langchain-deepseek uses), for both streaming chunks
    and complete responses. Display-only: request building ignores unknown
    additional_kwargs, so the reasoning is never sent back to the API on
    subsequent turns.
    """

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None,
    ):
        generation = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if generation is None:
            return None
        choices = chunk.get("choices") or chunk.get("chunk", {}).get("choices", [])
        delta = choices[0].get("delta") if choices else None
        reasoning = (
            delta.get("reasoning_content")
            if isinstance(delta, dict) and delta.get("reasoning_content")
            else None
        )
        if reasoning and isinstance(generation.message, AIMessageChunk):
            message = generation.message
            merged = message.additional_kwargs.get("reasoning_content", "")
            message.additional_kwargs["reasoning_content"] = merged + reasoning
        return generation

    def _create_chat_result(self, response, generation_info=None):
        result = super()._create_chat_result(response, generation_info)
        try:
            message = response.choices[0].message
            reasoning = getattr(message, "reasoning_content", None)
        except (AttributeError, IndexError):
            reasoning = None
        if reasoning:
            for generation in result.generations:
                if isinstance(generation.message, AIMessage):
                    generation.message.additional_kwargs["reasoning_content"] = (
                        reasoning
                    )
        return result

# ---------------------------------------------------------------------------
# Live reload: the FastAPI settings page persists model changes to .env; the
# LangGraph agent process watches that file and rebuilds models on the fly
# (see middleware/live_model_reload.py), so saves take effect without a
# service restart.
# ---------------------------------------------------------------------------

# settings field -> .env var; refreshed in place on the global Settings object.
# Besides the model fields this also carries the Feishu/lark keys so the
# LangGraph agent process picks up settings-page changes without a restart
# (these are NOT part of _SIG_FIELDS, so they never trigger a model rebuild).
#
# 记忆总闸（MEMORY_ENABLED）也在这里，理由不是模型而是"页面承诺"：中间件每次模型
# 调用现读 settings.memory_enabled，而「Agent 记忆」页的开关只写 .env——不热更新的话
# 用户关掉总闸得重启 LangGraph 才生效，与页面写的"下一轮生效"不符。
_ENV_REFRESH_KEYS: dict[str, str] = {
    "llm_model": "LLM_MODEL",
    "llm_base_url": "LLM_BASE_URL",
    "llm_api_key": "LLM_API_KEY",
    "llm_context_window": "LLM_CONTEXT_WINDOW",
    "llm_reasoning_effort": "LLM_REASONING_EFFORT",
    "deepseek_api_key": "DEEPSEEK_API_KEY",
    "deepseek_model": "DEEPSEEK_MODEL",
    "lark_cli_bin": "LARK_CLI_BIN",
    "lark_cli_identity": "LARK_CLI_IDENTITY",
    "feishu_mindnote_id": "FEISHU_MINDNOTE_ID",
    "feishu_mindnote_parent_node": "FEISHU_MINDNOTE_PARENT_NODE",
    "feishu_folder_token": "FEISHU_FOLDER_TOKEN",
    "memory_enabled": "MEMORY_ENABLED",
}
_INT_FIELDS = {"llm_context_window"}
# 布尔字段要显式转换：pydantic 默认不在赋值时校验，把字符串 "false" 直接 setattr
# 进去会变成**真值**（非空字符串），总闸就永远关不掉。
_BOOL_FIELDS = {"memory_enabled"}

# Fields that produce a different built model (cache signature)
_SIG_FIELDS = (
    "llm_model", "llm_base_url", "llm_api_key",
    "llm_reasoning_effort", "llm_context_window",
    "deepseek_api_key", "deepseek_model",
)

_ENV_FILE = settings.workspace_dir.parent / ".env"


def _current_sig() -> tuple:
    return tuple(getattr(settings, f) for f in _SIG_FIELDS)


# Baseline signature captured at import: the first refresh after startup then
# only reports a change when .env actually diverges from the loaded settings.
_reload_state: dict = {"mtime": None, "sig": _current_sig()}


def refresh_from_env() -> bool:
    """Reload model-related keys from .env into the global settings in place.

    Cheap: stats the file and only re-parses when its mtime changed. Returns
    True when the effective model signature changed (callers should rebuild
    their cached models); also clears the effort-variant cache in that case.
    """
    try:
        mtime = _ENV_FILE.stat().st_mtime_ns
    except OSError:
        return False
    if mtime == _reload_state["mtime"]:
        return False
    _reload_state["mtime"] = mtime

    env_map = dotenv_values(_ENV_FILE)
    for field, env_name in _ENV_REFRESH_KEYS.items():
        raw = env_map.get(env_name)
        if raw is None:
            continue  # absent in .env -> keep the current value
        if field in _INT_FIELDS:
            try:
                setattr(settings, field, int(raw.strip() or 0))
            except ValueError:
                continue
        elif field in _BOOL_FIELDS:
            setattr(settings, field, raw.strip().lower() not in ("", "0", "false", "no"))
        else:
            setattr(settings, field, raw.strip())

    sig = _current_sig()
    changed = sig != _reload_state["sig"]
    _reload_state["sig"] = sig
    if changed:
        _cached_effort_model.cache_clear()
    return changed


def build_model_from_values(values: dict, effort: str = "",
                            context_window: int | None = None,
                            max_retries: int | None = None,
                            request_timeout: float | None = None) -> BaseChatModel:
    """按一份「设置形状」的字典构建模型，不读也不改全局 ``settings``。

    与 ``build_chat_model()`` 是同一套解析规则和同一套构造方式，区别只在配置来源是
    入参。两个调用方需要它：

    - 设置页的连通性测试（表单值，绝不能污染进程级配置）；
    - 对话页按会话选的模型（``middleware/run_model.py``，走预设而非全局配置）。

    Args:
        values: ``MODEL_KEYS`` 形状的映射（``llm_model`` / ``llm_base_url`` /
            ``llm_api_key`` / ``deepseek_model`` / ``deepseek_api_key`` /
            ``llm_context_window`` / ``llm_reasoning_effort``）。
        effort: 本次调用的 reasoning effort；非法或为空时回落到 values 里的配置。
        context_window / max_retries / request_timeout: 显式覆盖，None 表示沿用全局。
    """
    base_url = (values.get("llm_base_url") or "").strip()
    model_name = (
        (values.get("llm_model") or "").strip()
        or (values.get("deepseek_model") or "").strip()
        or "deepseek-chat"
    )
    api_key = (
        (values.get("llm_api_key") or "").strip()
        or (values.get("deepseek_api_key") or "").strip()
    )

    effective_effort = effort if effort in VALID_EFFORTS else ""
    if not effective_effort:
        configured = str(values.get("llm_reasoning_effort") or "").strip()
        effective_effort = configured if configured in VALID_EFFORTS else ""

    kwargs: dict = {
        "max_retries": settings.llm_max_retries if max_retries is None else max_retries,
        # 超时必须在**构造时**传：langchain-openai 用它建 httpx client，事后赋值
        # 只是挂了个没人读的属性（详见 build_chat_model 的注释）。
        "timeout": settings.llm_request_timeout if request_timeout is None else request_timeout,
        "streaming": True,
    }
    if effective_effort:
        kwargs["reasoning_effort"] = effective_effort

    if base_url:
        if not api_key:
            raise ValueError("模型缺少 API Key（LLM_API_KEY）")
        # ReasoningChatOpenAI 保留 reasoning_content 增量（ChatOpenAI 会丢掉）。
        kwargs.update(
            model=model_name,
            base_url=base_url,
            api_key=api_key,
            default_headers=_go_session_headers(base_url),
        )
        llm = ReasoningChatOpenAI(**{k: v for k, v in kwargs.items() if v is not None})
    else:
        kwargs.update(model=f"deepseek:{model_name}")
        if api_key:
            kwargs["api_key"] = api_key
        llm = init_chat_model(**{k: v for k, v in kwargs.items() if v is not None})

    window = context_window
    if window is None:
        raw = str(values.get("llm_context_window") or "").strip()
        try:
            window = int(raw) if raw else settings.llm_context_window
        except ValueError:
            window = settings.llm_context_window
    # Real context window of the model: SummarizationMiddleware triggers at
    # 0.85 × max_input_tokens, so this must reflect the actual window.
    llm.profile = {"max_input_tokens": window}
    # 流式分块超时只能事后设（它不是构造参数，客户端按字段实时读取），
    # 但总超时已经在上面随构造传入，这里不再重复赋值以免又变成"看着设了其实没生效"。
    if hasattr(llm, "stream_chunk_timeout"):
        llm.stream_chunk_timeout = settings.llm_stream_chunk_timeout
    return llm


def build_chat_model(effort: str = "", context_window: int | None = None,
                     model_name: str | None = None) -> BaseChatModel:
    """Build a chat model from settings, optionally with a reasoning effort.

    Args:
        effort: reasoning effort ("low"/"medium"/"high"); anything else sends
            no reasoning parameter.
        context_window: override for the token budget used by summarization.
        model_name: 覆盖模型名（仍走同一个 provider/端点）。用于**异构复核**——
            评审换成不同模型家族才有意义，同族模型常常看不出自己写错的地方。

    Returns:
        A configured chat model instance.
    """
    return build_model_from_values(
        {
            "llm_model": model_name or settings.llm_model,
            "llm_base_url": settings.llm_base_url,
            "llm_api_key": settings.llm_api_key,
            "deepseek_model": settings.deepseek_model,
            "deepseek_api_key": settings.deepseek_api_key,
            "llm_context_window": settings.llm_context_window,
            "llm_reasoning_effort": settings.llm_reasoning_effort,
        },
        effort=effort,
        context_window=context_window,
    )


@lru_cache(maxsize=len(VALID_EFFORTS))
def _cached_effort_model(effort: str) -> BaseChatModel:
    return build_chat_model(effort=effort)


def effort_model(effort: str) -> BaseChatModel | None:
    """Return a cached model variant for a valid effort, else None."""
    if effort not in VALID_EFFORTS:
        return None
    return _cached_effort_model(effort)


# ---------------------------------------------------------------------------
# Connectivity test (POST /settings/model/test): build short-lived models
# from explicit form values WITHOUT touching the global settings singleton —
# the FastAPI process shares this module but must not have its own global
# model config mutated by a test request.
# ---------------------------------------------------------------------------

def build_test_model(values: dict, timeout: int = 30) -> BaseChatModel:
    """Build the short-lived model used by POST /settings/model/test.

    From explicit form values WITHOUT touching the global settings singleton —
    the FastAPI process shares this module but must not have its own global
    model config mutated by a test request.
    """
    return build_model_from_values(values, request_timeout=timeout, max_retries=0)
