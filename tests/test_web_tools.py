"""Tests for Web Agent tools: detect_test_mode, check_environment, ensure_output_dir."""
import shutil
from pathlib import Path

import pytest

from app.agents.web.tools import check_environment, detect_test_mode, ensure_output_dir


class TestDetectTestMode:
    def test_url_only_returns_mode_a(self):
        assert detect_test_mode("Test https://example.com") == "MODE_A_QA"

    def test_url_with_http(self):
        assert detect_test_mode("Check http://localhost:3000") == "MODE_A_QA"

    def test_windows_path_returns_mode_b(self):
        assert detect_test_mode("Test repo at C:\\Projects\\app") == "MODE_B_COMPONENT"

    def test_git_url_returns_mode_b(self):
        assert detect_test_mode("git@github.com:user/repo.git") == "MODE_B_COMPONENT"

    def test_source_code_keyword(self):
        assert detect_test_mode("Analyze the source code of my project") == "MODE_B_COMPONENT"

    def test_both_url_and_repo_returns_mode_b(self):
        result = detect_test_mode("Test https://example.com from repo at /home/user/proj")
        assert result == "MODE_B_COMPONENT"

    def test_ambiguous_returns_ask(self):
        assert detect_test_mode("hello world") == "ASK_CLARIFICATION"

    def test_empty_returns_ask(self):
        assert detect_test_mode("") == "ASK_CLARIFICATION"


class TestCheckEnvironment:
    def test_returns_dict_with_platform(self):
        result = check_environment()
        assert "platform" in result
        assert "tools" in result

    def test_tools_keys(self):
        result = check_environment()
        assert "playwright-cli" in result["tools"]
        assert "agent-browser" in result["tools"]

    def test_tool_entry_has_available_key(self):
        result = check_environment()
        for tool_name, info in result["tools"].items():
            assert "available" in info


class TestEnsureOutputDir:
    def test_mode_a_creates_subdirs(self):
        path = ensure_output_dir("MODE_A_QA", "test_site")
        p = Path(path)
        assert p.exists()
        assert (p / "screenshots").exists()
        assert (p / "traces").exists()
        assert (p / "videos").exists()
        assert (p / "storage").exists()
        shutil.rmtree(p.parent, ignore_errors=True)

    def test_mode_b_creates_subdirs(self):
        path = ensure_output_dir("MODE_B_COMPONENT", "my_app")
        p = Path(path)
        assert p.exists()
        assert (p / "poms").exists()
        assert (p / "tests").exists()
        assert (p / "references").exists()
        shutil.rmtree(p.parent, ignore_errors=True)

    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError, match="Unknown mode"):
            ensure_output_dir("UNKNOWN_MODE")

    def test_default_label(self):
        path = ensure_output_dir("MODE_A_QA")
        assert "session" in path
        shutil.rmtree(Path(path).parent, ignore_errors=True)
