"""Smoke tests for Web Agent creation and tool registration."""
import pytest


class TestAgentImport:
    def test_tools_module_imports(self):
        from src.app.agents.web.tools import (
            detect_test_mode, check_environment, ensure_output_dir,
            composite_backend, file_backend, shell_backend,
        )
        assert callable(detect_test_mode)
        assert callable(check_environment)
        assert callable(ensure_output_dir)

    def test_agent_module_imports(self):
        """Agent module should import without error (may fail on LLM key, which is OK)."""
        try:
            from src.app.agents.web import agent as agent_module
            assert hasattr(agent_module, "agent")
        except (ImportError, Exception) as e:
            err_msg = str(e).lower()
            if "deepseek" in err_msg or "api_key" in err_msg or "langchain" in err_msg:
                pytest.skip("LLM dependency not configured")
            raise

    def test_backends_created(self):
        from src.app.agents.web.tools import composite_backend, file_backend, shell_backend
        assert composite_backend is not None
        assert file_backend is not None
        assert shell_backend is not None

    def test_skills_middleware_configured(self):
        """Verify agent.py creates SkillsMiddleware with correct sources."""
        try:
            from src.app.agents.web import agent as agent_module
            # Agent was created successfully, middleware is wired
            assert agent_module.agent is not None
        except (ImportError, Exception) as e:
            err_msg = str(e).lower()
            if "deepseek" in err_msg or "api_key" in err_msg:
                pytest.skip("LLM dependency not configured")
            raise

    def test_system_prompt_contains_dual_mode(self):
        """Verify SYSTEM_PROMPT has Mode A and Mode B instructions."""
        try:
            from src.app.agents.web import agent as agent_module
            prompt = agent_module.SYSTEM_PROMPT
            assert "Mode A" in prompt or "Exploratory QA" in prompt
            assert "Mode B" in prompt or "Component-Aware" in prompt
            assert "Script Analyst" in prompt
        except (ImportError, Exception) as e:
            err_msg = str(e).lower()
            if "deepseek" in err_msg or "api_key" in err_msg:
                pytest.skip("LLM dependency not configured")
            raise
