"""Smoke tests for API Agent creation, tool registration, and system prompt."""
import pytest


class TestAgentImport:
    def test_tools_module_imports(self):
        """Tools module imports should work without LLM key."""
        from src.app.agents.api.tools import (
            MASTEST_TOOLS,
            composite_backend,
            file_backend,
            shell_backend,
        )

        assert isinstance(MASTEST_TOOLS, list)
        assert len(MASTEST_TOOLS) >= 3
        assert composite_backend is not None
        assert file_backend is not None
        assert shell_backend is not None

    def test_agent_module_imports(self):
        """Agent module should import without error (may fail on LLM key, which is OK)."""
        try:
            from src.app.agents.api import agent as agent_module

            assert hasattr(agent_module, "agent")
        except (ImportError, Exception) as e:
            err_msg = str(e).lower()
            if "deepseek" in err_msg or "api_key" in err_msg or "langchain" in err_msg:
                pytest.skip("LLM dependency not configured")
            raise

    def test_backends_created(self):
        """Backends should be instantiated in the tools module."""
        from src.app.agents.api.tools import composite_backend, file_backend, shell_backend

        assert composite_backend is not None
        assert file_backend is not None
        assert shell_backend is not None

    def test_skills_middleware_configured(self):
        """Verify agent.py creates SkillsMiddleware with correct sources."""
        try:
            from src.app.agents.api import agent as agent_module

            assert agent_module.agent is not None
            assert agent_module.skills_middleware is not None
        except (ImportError, Exception) as e:
            err_msg = str(e).lower()
            if "deepseek" in err_msg or "api_key" in err_msg:
                pytest.skip("LLM dependency not configured")
            raise

    def test_system_prompt_contains_mastest(self):
        """Verify SYSTEM_PROMPT has MASTEST methodology and all 7 stages."""
        try:
            from src.app.agents.api import agent as agent_module

            prompt = agent_module.SYSTEM_PROMPT
            assert "MASTEST" in prompt
            # 7 stages
            assert "Parse" in prompt
            assert "Scenarios" in prompt
            assert "Scripts" in prompt
            assert "Syntax" in prompt
            assert "Execute" in prompt
            assert "Quality" in prompt
            assert "Report" in prompt
        except (ImportError, Exception) as e:
            err_msg = str(e).lower()
            if "deepseek" in err_msg or "api_key" in err_msg:
                pytest.skip("LLM dependency not configured")
            raise
