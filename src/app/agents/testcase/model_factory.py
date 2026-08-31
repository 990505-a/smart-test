"""Chat-model factory for the agent.

One place that turns settings into a runnable chat model, so the default
model (agent bootstrap), per-run variants (reasoning-effort overrides) and
the vision model stay consistent. Provider selection is derived — no manual
switch:

- llm_base_url set  -> ANY OpenAI-compatible endpoint (OpenAI, SiliconFlow,
  OneAPI, OpenRouter, vLLM, Ollama's OpenAI shim, ...) via ChatOpenAI
- llm_base_url empty -> official DeepSeek API via langchain-deepseek

`effort` attaches a `reasoning_effort` model kwarg ("low"/"medium"/"high")
for reasoning-capable models; empty string sends nothing. If an endpoint
rejects the parameter, leave the effort unset.

`build_vision_model()` serves image-content turns: an explicit vision_model
wins; otherwise the text model is reused (it must then be vision-capable,
e.g. a multimodal chat model).
"""

from __future__ import annotations

from functools import lru_cache

from dotenv import dotenv_values
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_openai import ChatOpenAI

# Dual import alias: the LangGraph process puts src/ on sys.path ("app.*"),
# the FastAPI process imports everything as "src.app.*" (uvicorn from ROOT).
try:
    from app.core.config import settings
except ImportError:  # pragma: no cover — FastAPI-process alias
    from src.app.core.config import settings

VALID_EFFORTS = ("low", "medium", "high")


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
_ENV_REFRESH_KEYS: dict[str, str] = {
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
    "lark_cli_bin": "LARK_CLI_BIN",
    "lark_cli_identity": "LARK_CLI_IDENTITY",
    "feishu_mindnote_id": "FEISHU_MINDNOTE_ID",
    "feishu_mindnote_parent_node": "FEISHU_MINDNOTE_PARENT_NODE",
    "feishu_folder_token": "FEISHU_FOLDER_TOKEN",
}
_INT_FIELDS = {"llm_context_window"}

# Fields that produce a different built model (cache signature)
_SIG_FIELDS = (
    "llm_model", "llm_base_url", "llm_api_key",
    "vision_model", "vision_base_url", "vision_api_key",
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
        else:
            setattr(settings, field, raw.strip())

    sig = _current_sig()
    changed = sig != _reload_state["sig"]
    _reload_state["sig"] = sig
    if changed:
        _cached_effort_model.cache_clear()
    return changed


def _resolve_provider() -> str:
    return "openai_compatible" if (settings.llm_base_url or "").strip() else "deepseek"


def _resolve_model_name() -> str:
    return (settings.llm_model or "").strip() or settings.deepseek_model or "deepseek-chat"


def _resolve_api_key() -> str:
    return (settings.llm_api_key or "").strip() or settings.deepseek_api_key or ""


def build_chat_model(effort: str = "", context_window: int | None = None) -> BaseChatModel:
    """Build a chat model from settings, optionally with a reasoning effort.

    Args:
        effort: reasoning effort ("low"/"medium"/"high"); anything else sends
            no reasoning parameter.
        context_window: override for the token budget used by summarization.

    Returns:
        A configured chat model instance.
    """
    provider = _resolve_provider()
    model_name = _resolve_model_name()
    api_key = _resolve_api_key()

    # langchain 1.x chat models expose reasoning_effort as a first-class
    # field; passing it via model_kwargs only triggers a warning + relocation.
    effective_effort = effort
    if effective_effort not in VALID_EFFORTS:
        # fall back to the configured default when no per-run override exists
        effective_effort = (
            settings.llm_reasoning_effort
            if settings.llm_reasoning_effort in VALID_EFFORTS
            else ""
        )

    kwargs: dict = {
        "max_retries": settings.llm_max_retries,
        # Inline subagents are invoked with ainvoke(). LangChain emits their
        # nested messages only when the model itself is configured for streaming.
        "streaming": True,
    }
    if effective_effort:
        kwargs["reasoning_effort"] = effective_effort

    if provider == "openai_compatible":
        if not settings.llm_base_url:
            raise ValueError(
                "LLM_PROVIDER=openai_compatible 需要 LLM_BASE_URL（OpenAI 兼容端点地址）"
            )
        if not api_key:
            raise ValueError(
                "LLM_PROVIDER=openai_compatible 需要 LLM_API_KEY（或回退的 DEEPSEEK_API_KEY）"
            )
        # ReasoningChatOpenAI keeps reasoning_content deltas out of the
        # provider's thinking stream instead of letting ChatOpenAI drop them.
        kwargs.update(
            model=model_name,
            base_url=settings.llm_base_url,
            api_key=api_key,
        )
        openai_kwargs = {k: v for k, v in kwargs.items() if v is not None}
        llm = ReasoningChatOpenAI(**openai_kwargs)
    else:
        # default: official DeepSeek API (reads DEEPSEEK_API_KEY env if unset here)
        kwargs.update(model=f"deepseek:{model_name}")
        if api_key:
            kwargs["api_key"] = api_key
        llm = init_chat_model(**{k: v for k, v in kwargs.items() if v is not None})

    # Real context window of the model: SummarizationMiddleware triggers at
    # 0.85 × max_input_tokens, so this must reflect the actual window.
    llm.profile = {"max_input_tokens": context_window or settings.llm_context_window}
    llm.request_timeout = settings.llm_request_timeout
    if hasattr(llm, "stream_chunk_timeout"):
        llm.stream_chunk_timeout = settings.llm_stream_chunk_timeout
    return llm


@lru_cache(maxsize=len(VALID_EFFORTS))
def _cached_effort_model(effort: str) -> BaseChatModel:
    return build_chat_model(effort=effort)


def effort_model(effort: str) -> BaseChatModel | None:
    """Return a cached model variant for a valid effort, else None."""
    if effort not in VALID_EFFORTS:
        return None
    return _cached_effort_model(effort)


def build_vision_model() -> BaseChatModel:
    """Build the model used for image-content turns.

    Resolution order:
    1. vision_model empty -> reuse the text model (must be vision-capable).
    2. vision_base_url (or the text model's llm_base_url) set ->
       OpenAI-compatible endpoint; key falls back to the text model's key.
    3. neither base URL set -> official OpenAI endpoint, keyed by
       vision_api_key only (never the DeepSeek fallback key).
    """
    vision_model = (settings.vision_model or "").strip()
    if not vision_model:
        return build_chat_model()

    base_url = (
        (settings.vision_base_url or "").strip()
        or (settings.llm_base_url or "").strip()
    )

    kwargs: dict = {
        "max_retries": settings.llm_max_retries,
        "streaming": True,
    }
    if base_url:
        api_key = (settings.vision_api_key or "").strip() or _resolve_api_key()
        if not api_key:
            raise ValueError("视觉模型缺少 API Key（VISION_API_KEY 或文本模型的 Key）")
        # Direct construction (no "openai:" provider prefix — that is an
        # init_chat_model convention, ChatOpenAI would take it literally).
        kwargs.update(model=vision_model, base_url=base_url, api_key=api_key)
        llm = ReasoningChatOpenAI(**{k: v for k, v in kwargs.items() if v is not None})
    else:
        api_key = (settings.vision_api_key or "").strip()
        if not api_key:
            raise ValueError("视觉模型缺少 API Key（VISION_API_KEY）")
        kwargs.update(model=f"openai:{vision_model}", api_key=api_key)
        llm = init_chat_model(**kwargs)

    llm.profile = {"max_input_tokens": settings.llm_context_window}
    llm.request_timeout = settings.llm_request_timeout
    if hasattr(llm, "stream_chunk_timeout"):
        llm.stream_chunk_timeout = settings.llm_stream_chunk_timeout
    return llm


# ---------------------------------------------------------------------------
# Connectivity test (POST /settings/model/test): build short-lived models
# from explicit form values WITHOUT touching the global settings singleton —
# the FastAPI process shares this module but must not have its own global
# model config mutated by a test request.
# ---------------------------------------------------------------------------

def _test_text_model(values: dict, timeout: int) -> BaseChatModel:
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
    kwargs: dict = {"model": f"openai:{model_name}", "max_retries": 0}
    if base_url:
        if not api_key:
            raise ValueError("文本模型缺少 API Key")
        kwargs.update(base_url=base_url, api_key=api_key)
    else:
        kwargs["model"] = f"deepseek:{model_name}"
        if api_key:
            kwargs["api_key"] = api_key
    llm = init_chat_model(**kwargs)
    llm.request_timeout = timeout
    return llm


def _test_vision_model(values: dict, timeout: int) -> BaseChatModel | None:
    """Mirror build_vision_model()'s resolution against explicit values."""
    vision_model = (values.get("vision_model") or "").strip()
    if not vision_model:
        return None  # reuses the text model — text ping covers it
    base_url = (
        (values.get("vision_base_url") or "").strip()
        or (values.get("llm_base_url") or "").strip()
    )
    kwargs: dict = {"model": f"openai:{vision_model}", "max_retries": 0}
    if base_url:
        api_key = (
            (values.get("vision_api_key") or "").strip()
            or (values.get("llm_api_key") or "").strip()
            or (values.get("deepseek_api_key") or "").strip()
        )
        if not api_key:
            raise ValueError("视觉模型缺少 API Key")
        kwargs.update(base_url=base_url, api_key=api_key)
    else:
        api_key = (values.get("vision_api_key") or "").strip()
        if not api_key:
            raise ValueError("视觉模型缺少 API Key（VISION_API_KEY）")
        kwargs["api_key"] = api_key
    llm = init_chat_model(**kwargs)
    llm.request_timeout = timeout
    return llm


def build_test_models(values: dict, timeout: int = 30) -> dict[str, BaseChatModel | None]:
    """Build {"text": model, "vision": model|None} from explicit values."""
    return {
        "text": _test_text_model(values, timeout),
        "vision": _test_vision_model(values, timeout),
    }
