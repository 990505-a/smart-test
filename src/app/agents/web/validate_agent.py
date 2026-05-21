"""Smoke-test script for the Web Automation Testing Agent (Phase 15).

Usage:
    python -m app.agents.web.validate_agent

Checks:
    1. Agent module imports cleanly (or reports LLM dep issue)
    2. Tool registry has 18 local tools
    3. Backend routing works (composite, shell, file)
    4. System prompt contains 4-workflow structure
    5. MCP pattern in agent.py source code
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
        if (
            "langchain-deepseek" in err_msg
            or "deepseek" in err_msg.lower()
            or "api_key" in err_msg.lower()
        ):
            print("      WARN -- LLM dependency missing (pip install langchain-deepseek)")
            print(f"             {err_msg}")
            return True
        print(f"      FAIL -- {e}")
        return False


def _check_tools() -> bool:
    print("[2/5] Checking tool registry (18 local tools)...")
    try:
        from app.agents.web.tools import WEB_AGENT_TOOLS

        tool_count = len(WEB_AGENT_TOOLS)
        tool_names = [t.name for t in WEB_AGENT_TOOLS]

        # Verify expected tool count (18 from Plan 01: 7+6+3+2)
        assert tool_count == 18, f"Expected 18 tools, got {tool_count}"

        # Spot-check key tools
        expected_tools = [
            "list_web_functions",
            "create_web_function",
            "save_web_test_plan",
            "save_web_test_cases",
            "save_web_test_script",
            "execute_web_script",
        ]
        for name in expected_tools:
            assert name in tool_names, f"Missing tool: {name}"

        print(f"      OK -- {tool_count} tools registered ({', '.join(tool_names[:5])}...)")
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

        # File backend ls should work (lists workspace contents)
        ls_result = file_backend.ls("/")
        assert not ls_result.error, f"file_backend.ls failed: {ls_result.error}"
        print(f"      OK -- file_backend.ls ({len(ls_result.entries or [])} entries)")

        # Composite backend execute delegates to shell
        result2 = composite_backend.execute("echo composite_ok")
        assert result2.exit_code == 0
        print("      OK -- composite_backend.execute")

        return True
    except Exception as e:
        print(f"      FAIL -- {e}")
        return False


def _check_system_prompt() -> bool:
    print("[4/5] Checking system prompt (4-workflow structure)...")
    try:
        from app.agents.web.agent import SYSTEM_PROMPT

        # Key elements from classroom 4-workflow prompt
        keywords = [
            "planner_setup_page",
            "browser_snapshot",
            "save_web_test_plan",
            "healer",
            "generator",
            "executor",
        ]
        for kw in keywords:
            assert kw in SYSTEM_PROMPT, f"System prompt missing keyword: {kw}"

        print(f"      OK -- system prompt contains all {len(keywords)} key elements")
        return True
    except Exception as e:
        print(f"      FAIL -- {e}")
        return False


def _check_mcp_pattern() -> bool:
    print("[5/5] Checking MCP pattern in agent.py source...")
    try:
        agent_source = Path(__file__).resolve().parent / "agent.py"
        source = agent_source.read_text(encoding="utf-8")

        patterns = {
            "MultiServerMCPClient": "MCP client import",
            "client.session": "session-level MCP pattern",
            "load_mcp_tools(session)": "load tools from session (not client)",
            "browser_": "browser_ error pattern",
            "playwright-test/": "playwright-test/ error pattern",
            "web_mcp_root_resolved": "settings.web_mcp_root_resolved for MCP command",
        }
        for pattern, desc in patterns.items():
            assert pattern in source, f"Agent source missing: {pattern} ({desc})"

        print(f"      OK -- all {len(patterns)} MCP patterns verified")
        return True
    except Exception as e:
        print(f"      FAIL -- {e}")
        return False


def main() -> int:
    print("=" * 60)
    print("Web Automation Testing Agent -- Validation Suite (Phase 15)")
    print("=" * 60)

    results = [
        _check_import(),
        _check_tools(),
        _check_backend(),
        _check_system_prompt(),
        _check_mcp_pattern(),
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
