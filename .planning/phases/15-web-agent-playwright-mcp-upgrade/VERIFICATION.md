---
phase: 15-web-agent-playwright-mcp-upgrade
verified: 2026-05-21T18:30:00Z
status: gaps_found
score: 5/6 must-haves verified
gaps:
  - truth: "validate_agent.py updated for new tools package structure and passes all checks"
    status: partial
    reason: "validate_agent.py has import path bug -- uses 'from app.agents.web...' instead of 'from src.app.agents.web...', causing 4/5 checks to fail with 'No module named src'. Only check 5 (source file grep) passes."
    artifacts:
      - path: "src/app/agents/web/validate_agent.py"
        issue: "Lines 29, 50, 80, 107 use 'from app.agents.web...' but sys.path entry points to src/ directory where packages are 'src.app.agents.web...'"
    missing:
      - "Fix validate_agent.py imports to use 'from src.app.agents.web...' (matching all other modules in the project)"
      - "OR add the project root (parent of src/) to sys.path instead of src/ itself"
---

# Phase 15: Web Agent Playwright MCP Upgrade Verification Report

**Phase Goal:** Replace Web Agent's Shell Backend with Playwright MCP for real browser control, add 16-tool registry for web testing lifecycle, activate 8 web_mcp skills from Phase 14
**Verified:** 2026-05-21T18:30:00Z
**Status:** gaps_found
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Config has web_mcp_root pointing to workspace/default/web directory | VERIFIED | config.py line 38: `web_mcp_root: str = ""`, lines 49-53: `web_mcp_root_resolved` property returns `workspace/default/web` when empty |
| 2 | workspace/default/web has package.json with @playwright/test and node_modules installed | VERIFIED | package.json exists with `@playwright/test: ^1.58.2`, node_modules/@playwright/test directory exists on disk |
| 3 | Tool registry exposes 18 local tools across 4 categories (function, artifacts, scripts, execution) | VERIFIED | FUNCTION_TOOLS=7, ARTIFACT_TOOLS=6, SCRIPT_TOOLS=3, EXECUTION_TOOLS=2, total=18. All import and instantiate correctly |
| 4 | All tools follow existing project patterns (@tool decorator, async def, local filesystem, dict returns) | VERIFIED | All 18 tools use `@tool` from langchain_core.tools, async def, workspace-based file paths, return dict |
| 5 | Agent creates MCP client connected to Playwright Test MCP server via stdio session-level pattern | VERIFIED | agent.py lines 415-429: MultiServerMCPClient with stdio transport, `client.session("web_mcp")`, `load_mcp_tools(session)` |
| 6 | System prompt describes 4 workflows (Generate Tests, Create Function, Execute Tests, Auto-Heal) | VERIFIED | SYSTEM_PROMPT is 7729 chars Chinese prompt with sections for all 4 workflows |
| 7 | Error handler targets only browser_ and playwright-test/ prefixed tools | VERIFIED | agent.py line 439: `tool_patterns=["browser_", "playwright-test/"]` |
| 8 | 8 web_mcp skills activate automatically when MCP tools are available | VERIFIED | 8 SKILL.md files in workspace/default/web/skills/ (case-designer, executor, explorer, generator, healer, planner, prerequisite, reporter) |
| 9 | Old tools.py file removed and replaced by tools/ package | VERIFIED | tools.py does not exist; tools/ directory with __init__.py and 4 modules exists |
| 10 | validate_agent.py updated for new tools package structure and passes | FAILED | See Gaps section below |

**Score:** 9/10 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/app/core/config.py` | web_mcp_root setting + property | VERIFIED | Line 38: setting, lines 49-53: property, returns WindowsPath |
| `workspace/default/web/package.json` | @playwright/test dependency | VERIFIED | `"@playwright/test": "^1.58.2"` and `"@types/node": "^25.0.3"` |
| `workspace/default/web/playwright.config.ts` | chromium project config | VERIFIED | defineConfig with chromium Desktop Chrome device |
| `src/app/agents/web/tools/__init__.py` | WEB_AGENT_TOOLS + backends | VERIFIED | Exports WEB_AGENT_TOOLS (18), composite_backend, file_backend, shell_backend |
| `src/app/agents/web/tools/function_tools.py` | 7 function tools | VERIFIED | FUNCTION_TOOLS list with 7 tools, all substantive implementations |
| `src/app/agents/web/tools/test_artifacts_tools.py` | 6 artifact tools | VERIFIED | ARTIFACT_TOOLS list with 6 tools, full file save/read logic |
| `src/app/agents/web/tools/script_tools.py` | 3 script tools | VERIFIED | SCRIPT_TOOLS list with 3 tools, file copy/delete operations |
| `src/app/agents/web/tools/execution_tools.py` | 2 execution tools | VERIFIED | EXECUTION_TOOLS list with 2 tools, subprocess execution |
| `src/app/agents/web/agent.py` | make_agent() + MCP + 4-workflow prompt | VERIFIED | Complete rewrite, all patterns verified |
| `src/app/agents/web/validate_agent.py` | 5-check validation suite | STUB | File exists, structure correct, but import paths broken (4/5 checks fail) |
| `.gitignore` | node_modules/ entry | VERIFIED | `node_modules/` added |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| agent.py | tools/__init__.py | `from src.app.agents.web.tools import WEB_AGENT_TOOLS, composite_backend, file_backend` | WIRED | Import succeeds, 18 tools + 3 backends loaded |
| agent.py | langchain_mcp_adapters | `MultiServerMCPClient` + `load_mcp_tools(session)` | WIRED | Both imports succeed, session-level pattern confirmed in source |
| agent.py | config.py | `settings.web_mcp_root_resolved` for MCP command | WIRED | Used in MCP client args: `f"cd {settings.web_mcp_root_resolved}"` |
| agent.py | middleware/__init__.py | `WebContextInjectionMiddleware`, `wrap_tools_with_error_handling` | WIRED | Both imported and used in make_agent() |
| tools/__init__.py | function_tools.py | `from src.app.agents.web.tools.function_tools import FUNCTION_TOOLS` | WIRED | 7 tools loaded |
| tools/__init__.py | test_artifacts_tools.py | `from src.app.agents.web.tools.test_artifacts_tools import ARTIFACT_TOOLS` | WIRED | 6 tools loaded |
| tools/__init__.py | script_tools.py | `from src.app.agents.web.tools.script_tools import SCRIPT_TOOLS` | WIRED | 3 tools loaded |
| tools/__init__.py | execution_tools.py | `from src.app.agents.web.tools.execution_tools import EXECUTION_TOOLS` | WIRED | 2 tools loaded |
| validate_agent.py | tools/__init__.py | `from app.agents.web.tools import ...` | NOT_WIRED | Import path omits `src.` prefix, fails with "No module named 'src'" |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| function_tools.py | functions JSON list | _read_json(functions.json) | Yes -- reads/writes real JSON files | FLOWING |
| test_artifacts_tools.py | file content | Filesystem reads/writes | Yes -- saves real files to artifacts dir | FLOWING |
| execution_tools.py | subprocess output | asyncio.create_subprocess_shell | Yes -- runs real `npx playwright test` | FLOWING |
| agent.py | mcp_tools | load_mcp_tools(session) | Dynamic -- depends on MCP server running | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Tool count verification | `python -c "from src.app.agents.web.tools import WEB_AGENT_TOOLS; print(len(WEB_AGENT_TOOLS))"` | 18 | PASS |
| Config path resolution | `python -c "from src.app.core.config import settings; print(settings.web_mcp_root_resolved)"` | D:\test_agent\smart-test-platform\workspace\default\web | PASS |
| Agent import chain | `python -c "from src.app.agents.web.agent import make_agent, SYSTEM_PROMPT, WebAgentContext"` | No error | PASS |
| @playwright/test installed | `test -d workspace/default/web/node_modules/@playwright/test` | Directory exists | PASS |
| validate_agent.py 5-check suite | `python src/app/agents/web/validate_agent.py` | 1/5 checks passed | FAIL |
| Skills count | `ls workspace/default/web/skills/*/SKILL.md` | 8 files | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| WEB-MCP-01 | 15-01 | Config + workspace setup | SATISFIED | config.py, package.json, playwright.config.ts, node_modules |
| WEB-MCP-02 | 15-01 | Tool registry 16+ tools | SATISFIED | 18 tools across 4 modules |
| WEB-MCP-03 | 15-01 | Tools follow project patterns | SATISFIED | All use @tool, async, local filesystem |
| WEB-MCP-04 | 15-01 | Backends exported | SATISFIED | composite_backend, file_backend, shell_backend |
| WEB-MCP-05 | 15-02 | MCP session-level pattern | SATISFIED | client.session("web_mcp") + load_mcp_tools(session) |
| WEB-MCP-06 | 15-02 | 4-workflow system prompt | SATISFIED | Chinese 4-workflow prompt (7729 chars) |
| WEB-MCP-07 | 15-02 | Targeted error handling | SATISFIED | tool_patterns=["browser_", "playwright-test/"] |
| WEB-MCP-08 | 15-02 | validate_agent.py updated | PARTIAL | File updated but has import path bug |

Note: WEB-MCP-* requirements are declared in PLAN frontmatter but do not appear in the formal REQUIREMENTS.md. ROADMAP.md lists them under Phase 15.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| function_tools.py | 197 | `get_folder_structure` returns `{"folders": [], "total": 0}` always | Info | Documented Phase 16 placeholder. Does not block current workflows. |
| execution_tools.py | 171-176 | `get_test_execution_status` always returns "completed" | Info | Documented Phase 16 placeholder. Synchronous execution only. |
| validate_agent.py | 29 | `from app.agents.web import agent as agent_module` | Warning | Import path missing `src.` prefix; fails when run directly |

No blocker anti-patterns found. The two placeholder tools are explicitly documented and tracked for Phase 16.

### Commit Verification

| Commit | Message | Status |
|--------|---------|--------|
| 6b63f3d | feat(15-01): add web_mcp_root config and Playwright workspace setup | VERIFIED |
| 20b14c0 | feat(15-01): create tool registry package with 18 local web tools | VERIFIED |
| 83c67bc | feat(15-02): rewrite web agent with Playwright MCP integration | VERIFIED |
| 4f47a54 | fix(15-02): fix validate_agent.py file_backend attribute check | VERIFIED |

All 4 commits found in git log.

### Human Verification Required

### 1. Playwright MCP Server Connection

**Test:** Start the Playwright MCP server with `npx playwright run-test-mcp-server` in the workspace/default/web/ directory, then run the agent to verify browser tools load
**Expected:** Agent session starts, ~20 MCP browser tools load alongside 18 local tools
**Why human:** Requires running external MCP server process; cannot test programmatically without server

### 2. SkillsMiddleware Auto-Loading

**Test:** Create a chat session with the web agent and verify the 8 web_mcp skills load from workspace/default/web/skills/
**Expected:** SkillsMiddleware loads all 8 SKILL.md files, agent has access to skill guidance
**Why human:** Requires full agent runtime with LangGraph server and MCP server

### 3. End-to-End Browser Test Workflow

**Test:** Send a message to the web agent requesting test generation for a web function, observe the 4-workflow execution
**Expected:** Agent initializes browser, navigates, generates test plan, creates script
**Why human:** Full runtime integration test requiring LLM API keys, MCP server, and browser

### Gaps Summary

**1 gap found: validate_agent.py import path bug**

The `validate_agent.py` script adds `src/` to `sys.path` (via `parents[3]`) but then uses `from app.agents.web...` instead of `from src.app.agents.web...`. Since `src` is the package root on the path, the correct import should be `from src.app.agents.web...` to match all other modules in the project.

This causes 4 out of 5 validation checks to fail with "No module named 'src'". Only check 5 (source file grep) passes because it reads agent.py directly from disk.

**Fix options:**
1. Change all `from app.agents.web...` to `from src.app.agents.web...` in validate_agent.py (4 locations: lines 29, 50, 80, 107)
2. Or change the sys.path entry from `src/` to the project root (parent of `src/`) so that `from src.app.agents.web...` works

**Impact:** Low severity -- validate_agent.py is a development smoke test, not production code. The actual agent.py and tools package work correctly with their imports. However, the validation script itself is broken, which means automated verification of the agent setup is not functional.

---

_Verified: 2026-05-21T18:30:00Z_
_Verifier: Claude (gsd-verifier)_
