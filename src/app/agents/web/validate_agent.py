"""
Smoke-test script for the Web Automation Testing Agent.

Usage:
    python -m app.agents.web.validate_agent

Checks:
    1. Agent module imports cleanly (or reports LLM dep issue)
    2. Custom tools are registered and callable
    3. Backend routes resolve correctly
    4. Skills are discoverable
    5. Environment dependencies are available
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ directory is on path for `from app.agents.web.tools import ...`
# validate_agent.py lives at src/app/agents/web/validate_agent.py
# parents[3] = src/
src_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(src_root))


def _check_import() -> bool:
    print("[1/5] Checking agent module import...")
    try:
        from app.agents.web import agent as agent_module

        print(f"      OK -- agent created: {type(agent_module.agent).__name__}")
        return True
    except (ImportError, Exception) as e:
        err_msg = str(e)
        if "langchain-deepseek" in err_msg or "deepseek" in err_msg.lower() or "api_key" in err_msg.lower():
            print("      WARN -- LLM dependency missing (pip install langchain-deepseek)")
            print(f"             {err_msg}")
            return True
        print(f"      FAIL -- {e}")
        return False
    except Exception as e:
        print(f"      FAIL -- {e}")
        return False


def _check_tools() -> bool:
    print("[2/5] Checking custom tools...")
    try:
        from app.agents.web.tools import check_environment, detect_test_mode, ensure_output_dir

        # detect_test_mode
        assert detect_test_mode("Test https://example.com") == "MODE_A_QA"
        assert detect_test_mode("Test repo at C:\\Projects\\app") == "MODE_B_COMPONENT"
        assert detect_test_mode("hello") == "ASK_CLARIFICATION"
        print("      OK -- detect_test_mode")

        # check_environment
        env = check_environment()
        assert "tools" in env
        print(f"      OK -- check_environment (platform={env.get('platform')})")

        # ensure_output_dir
        qa_dir = ensure_output_dir("MODE_A_QA", "example.com")
        assert Path(qa_dir).exists()
        assert (Path(qa_dir) / "screenshots").exists()
        import shutil

        shutil.rmtree(qa_dir, ignore_errors=True)
        print("      OK -- ensure_output_dir")

        return True
    except Exception as e:
        print(f"      FAIL -- {e}")
        return False


def _check_backend() -> bool:
    print("[3/5] Checking backend routing...")
    try:
        from app.agents.web.tools import composite_backend, file_backend, shell_backend

        # Shell backend should support execute
        result = shell_backend.execute("echo backend_ok")
        assert result.exit_code == 0
        assert "backend_ok" in result.output
        print("      OK -- shell_backend.execute")

        # File backend should list skills
        ls_result = file_backend.ls("/skills")
        assert not ls_result.error, f"ls error: {ls_result.error}"
        assert ls_result.entries is not None, "ls returned None entries"
        skill_names = {entry["path"].rstrip("/").split("/")[-1] for entry in ls_result.entries}
        assert "pw-dogfood" in skill_names, f"missing pw-dogfood in {skill_names}"
        assert "component-aware-web-automation" in skill_names, f"missing component-aware-web-automation in {skill_names}"
        print(f"      OK -- file_backend.ls found {len(skill_names)} skills")

        # Composite backend execute delegates to shell
        result2 = composite_backend.execute("echo composite_ok")
        assert result2.exit_code == 0
        print("      OK -- composite_backend.execute")

        return True
    except Exception as e:
        print(f"      FAIL -- {e}")
        return False


def _check_skills() -> bool:
    print("[4/5] Checking skill readability...")
    try:
        from app.agents.web.tools import file_backend

        required_skills = [
            "/skills/pw-dogfood/SKILL.md",
            "/skills/component-aware-web-automation/SKILL.md",
            "/skills/agent-browser-vs-playwright-cli/SKILL.md",
            "/skills/playwright-cli/SKILL.md",
            "/skills/agent-browser/SKILL.md",
        ]
        for path in required_skills:
            res = file_backend.read(path)
            assert not res.error, f"Cannot read {path}: {res.error}"
            assert res.file_data is not None, f"{path} returned no file_data"
            content = res.file_data.get("content", "")
            assert len(content) > 100, f"{path} seems too short ({len(content)} chars)"
        print(f"      OK -- all {len(required_skills)} required skills readable")
        return True
    except Exception as e:
        print(f"      FAIL -- {e}")
        return False


def _check_environment() -> bool:
    print("[5/5] Checking external CLI dependencies...")
    try:
        from app.agents.web.tools import check_environment

        env = check_environment()
        playwright = env["tools"].get("playwright-cli", {})
        if playwright.get("available"):
            print(f"      OK -- playwright-cli {playwright.get('version')}")
        else:
            print(f"      WARN -- playwright-cli unavailable: {playwright.get('error')}")

        ab = env["tools"].get("agent-browser", {})
        if ab.get("available"):
            print(f"      OK -- agent-browser {ab.get('version')}")
        else:
            print(f"      WARN -- agent-browser unavailable: {ab.get('error')}")

        return True
    except Exception as e:
        print(f"      FAIL -- {e}")
        return False


def main() -> int:
    print("=" * 60)
    print("Web Automation Testing Agent -- Validation Suite")
    print("=" * 60)

    results = [
        _check_import(),
        _check_tools(),
        _check_backend(),
        _check_skills(),
        _check_environment(),
    ]

    passed = sum(results)
    total = len(results)

    print("=" * 60)
    if passed == total:
        print(f"All {total} checks PASSED.")
        return 0
    else:
        print(f"{passed}/{total} checks passed. Review failures above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
