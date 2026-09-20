"""Unit tests for the chat-model factory (custom providers + reasoning effort)."""
import pytest

import src.app.agents.testcase.model_factory as mf
from src.app.agents.testcase.model_factory import (
    VALID_EFFORTS,
    build_chat_model,
    build_model_from_values,
    build_test_model,
    effort_model,
    refresh_from_env,
)
from src.app.core.config import settings


@pytest.fixture(autouse=True)
def _clean_settings(monkeypatch):
    """Pin settings to a known state and clear the effort-model cache."""
    monkeypatch.setattr(settings, "llm_model", "", raising=False)
    monkeypatch.setattr(settings, "llm_base_url", "", raising=False)
    monkeypatch.setattr(settings, "llm_api_key", "", raising=False)
    monkeypatch.setattr(settings, "llm_context_window", 128_000, raising=False)
    monkeypatch.setattr(settings, "llm_max_retries", 3, raising=False)
    monkeypatch.setattr(settings, "llm_request_timeout", 300, raising=False)
    monkeypatch.setattr(settings, "llm_reasoning_effort", "", raising=False)
    monkeypatch.setattr(settings, "deepseek_model", "deepseek-chat", raising=False)
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test", raising=False)
    mf._cached_effort_model.cache_clear()
    yield
    mf._cached_effort_model.cache_clear()


class TestDeepSeekProvider:
    def test_default_build(self):
        model = build_chat_model()

        assert getattr(model, "model_name", None) == "deepseek-chat"
        assert model.profile["max_input_tokens"] == 128_000
        assert model.request_timeout == 300

    def test_model_name_override(self, monkeypatch):
        monkeypatch.setattr(settings, "llm_model", "deepseek-reasoner", raising=False)

        model = build_chat_model()

        assert getattr(model, "model_name", None) == "deepseek-reasoner"


class TestOpenAICompatibleProvider:
    def test_custom_endpoint_build(self, monkeypatch):
        monkeypatch.setattr(settings, "llm_model", "qwen3-max")
        monkeypatch.setattr(settings, "llm_base_url", "https://api.siliconflow.cn/v1")
        monkeypatch.setattr(settings, "llm_api_key", "sk-custom")

        model = build_chat_model()

        assert getattr(model, "model_name", None) == "qwen3-max"
        base = getattr(model, "openai_api_base", None) or getattr(model, "base_url", None)
        assert str(base) == "https://api.siliconflow.cn/v1"

    def test_no_base_url_uses_deepseek(self, monkeypatch):
        """Provider is derived: base_url empty -> official DeepSeek, no error."""
        monkeypatch.setattr(settings, "llm_model", "")
        monkeypatch.setattr(settings, "llm_base_url", "")

        model = build_chat_model()

        assert getattr(model, "model_name", None) == "deepseek-chat"

    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.setattr(settings, "llm_base_url", "https://x.example/v1")
        monkeypatch.setattr(settings, "llm_api_key", "")
        monkeypatch.setattr(settings, "deepseek_api_key", "", raising=False)

        with pytest.raises(ValueError, match="API"):
            build_chat_model()


class TestBuildModelFromValues:
    """按显式配置构建模型：设置页连通性测试与对话页模型预设共用这条路径。"""

    def test_explicit_endpoint_and_model(self):
        model = build_model_from_values({
            "llm_base_url": "https://api.siliconflow.cn/v1",
            "llm_model": "glm-5.3-flash",
            "llm_api_key": "sk-x",
        })

        assert getattr(model, "model_name", None) == "glm-5.3-flash"
        base = getattr(model, "openai_api_base", None) or getattr(model, "base_url", None)
        assert str(base) == "https://api.siliconflow.cn/v1"
        # profile 用于 SummarizationMiddleware 的触发阈值
        assert model.profile["max_input_tokens"] == 128_000

    def test_effort_wins_over_values_default(self):
        values = {
            "llm_base_url": "https://x.example/v1",
            "llm_model": "m1",
            "llm_api_key": "sk-x",
            "llm_reasoning_effort": "low",
        }

        assert getattr(build_model_from_values(values, effort="high"),
                       "reasoning_effort", None) == "high"
        assert getattr(build_model_from_values(values), "reasoning_effort", None) == "low"

    def test_no_base_url_uses_deepseek(self):
        model = build_model_from_values({"llm_model": "", "deepseek_model": "deepseek-chat"})

        assert getattr(model, "model_name", None) == "deepseek-chat"

    def test_missing_key_raises(self):
        with pytest.raises(ValueError, match="API Key"):
            build_model_from_values({"llm_base_url": "https://x.example/v1"})

    def test_does_not_touch_global_settings(self):
        before = mf._current_sig()
        build_model_from_values({
            "llm_base_url": "https://api.siliconflow.cn/v1",
            "llm_model": "some-other-model",
            "llm_api_key": "sk-x",
        })
        assert mf._current_sig() == before


class TestBuildTestModel:
    def test_text_via_custom_endpoint(self):
        model = build_test_model({
            "llm_base_url": "https://api.siliconflow.cn/v1",
            "llm_model": "glm-5.3-flash",
            "llm_api_key": "sk-x",
        })

        assert getattr(model, "model_name", None) == "glm-5.3-flash"

    def test_missing_key_raises(self):
        with pytest.raises(ValueError, match="API Key"):
            build_test_model({"llm_base_url": "https://x.example/v1"})


class TestLiveReload:
    def test_refresh_picks_up_changed_env(self, tmp_path, monkeypatch):
        env = tmp_path / ".env"
        env.write_text("LLM_MODEL=glm-5.3-flash\n", encoding="utf-8")
        monkeypatch.setattr(mf, "_ENV_FILE", env)
        monkeypatch.setitem(mf._reload_state, "mtime", None)
        mf._reload_state["sig"] = mf._current_sig()

        assert refresh_from_env() is True
        assert settings.llm_model == "glm-5.3-flash"
        # same mtime -> skipped entirely
        assert refresh_from_env() is False

    def test_refresh_only_reports_real_changes(self, tmp_path, monkeypatch):
        env = tmp_path / ".env"
        env.write_text("LLM_MODEL=\n", encoding="utf-8")
        monkeypatch.setattr(mf, "_ENV_FILE", env)
        monkeypatch.setitem(mf._reload_state, "mtime", None)
        mf._reload_state["sig"] = mf._current_sig()

        assert refresh_from_env() is False  # same effective config

    def test_refresh_missing_env_file_is_noop(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mf, "_ENV_FILE", tmp_path / "nope.env")

        assert refresh_from_env() is False


class TestReasoningEffort:
    def test_valid_effort_attached(self):
        model = build_chat_model(effort="high")

        assert getattr(model, "reasoning_effort", None) == "high"

    def test_invalid_effort_sends_nothing(self):
        model = build_chat_model(effort="banana")

        assert getattr(model, "reasoning_effort", None) is None

    def test_empty_effort_falls_back_to_configured_default(self, monkeypatch):
        monkeypatch.setattr(settings, "llm_reasoning_effort", "low", raising=False)

        model = build_chat_model()

        assert getattr(model, "reasoning_effort", None) == "low"

    def test_effort_model_cache(self):
        m1 = effort_model("low")
        m2 = effort_model("low")

        assert m1 is not None and m1 is m2

    def test_effort_model_invalid_returns_none(self):
        assert effort_model("off") is None
        assert effort_model("") is None

    def test_valid_efforts_tuple(self):
        assert VALID_EFFORTS == ("low", "medium", "high")
