# Phase 15: Web Agent Playwright MCP Upgrade - Research

**Researched:** 2026-05-21
**Domain:** Playwright Test MCP integration, Web Agent browser automation
**Confidence:** HIGH

## Summary

Phase 15 upgrades the Web Automation Agent from Shell-based Playwright CLI execution to real-time browser control via the Playwright Test MCP server. The current agent (`src/app/agents/web/agent.py`) uses a `CompositeBackend` with `LocalShellBackend` to execute Playwright commands through a subprocess, and has only 3 local tools. The upgrade replaces this with a `MultiServerMCPClient` connected to the Playwright Test MCP server (`npx playwright run-test-mcp-server`), which provides ~20 browser interaction tools (navigate, click, type, snapshot, verify) directly to the LLM as first-class callable tools.

The classroom reference implementation demonstrates the exact pattern needed: an `asynccontextmanager make_agent()` that opens an MCP stdio session, loads browser tools via `load_mcp_tools(session)`, combines them with 16 local tools (function management, test artifacts, scripts, execution), wraps only browser-prefixed tools with error handling, and yields the agent graph. The MCP session persists for the agent's entire lifetime. Our Phase 14 already created the `make_agent()` stub with this architecture in mind.

The 8 web_mcp skills installed in Phase 14 (planner, case-designer, executor, generator, healer, reporter, explorer, prerequisite) reference Playwright MCP tools in their YAML frontmatter and will activate automatically once the MCP tools are available. The system prompt needs a significant rewrite to match the classroom's 4-workflow structure (Generate Tests, Create Function, Execute Tests, Auto-Heal) which replaces our current dual-mode prompt.

**Primary recommendation:** Follow the classroom pattern exactly -- replace Shell backend with Playwright MCP stdio transport, expand local tools from 3 to ~16 (or adapt from API agent's DB tools pattern), rewrite system prompt to 4-workflow structure, and change error handler from wrapping ALL tools to targeting only `browser_` and `playwright-test/` prefixed tools.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| langchain-mcp-adapters | 0.2.2 | MCP client for Playwright Test tools | Already used in API agent for GitNexus. Provides `MultiServerMCPClient` and `load_mcp_tools`. |
| deepagents | 0.6.1 | Agent framework with Skills/Backend/Middleware | Project standard since Phase 1. `create_deep_agent`, `SkillsMiddleware`, `CompositeBackend`. |
| Playwright CLI | 1.60.0 | Browser automation runtime | Already installed globally. Provides `run-test-mcp-server` subcommand (available since 1.58). |
| @playwright/test | ^1.58.2 | Test framework for MCP server | Needs local install in workspace. Required by `run-test-mcp-server`. Classroom uses 1.58.2. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|-------------|-------------|
| langchain-core | >= 0.3.x | BaseTool, StructuredTool for tool definitions | Already installed. Used for local tool creation. |
| pydantic-settings | >= 2.x | Settings class for MCP config | Already in config.py. Add web_mcp settings. |

### MCP Server (Not a pip package -- npm-based)
| Server | Command | Purpose | Tools Provided |
|--------|---------|---------|----------------|
| Playwright Test MCP | `npx playwright run-test-mcp-server` | Real browser control for testing | ~20 tools: `planner_setup_page`, `generator_setup_page`, `browser_navigate`, `browser_click`, `browser_type`, `browser_snapshot`, `browser_verify_text_visible`, `browser_verify_element_visible`, `browser_verify_list_visible`, `browser_verify_value`, `browser_wait_for`, `browser_generate_locator`, `browser_evaluate`, `browser_tab_*`, etc. |

**Installation (workspace npm):**
```bash
# In the workspace/web directory (or similar MCP working directory)
cd workspace/default/web
npm init -y
npm install @playwright/test@^1.58.2 @types/node
```

**No additional pip packages required** -- all Python dependencies already installed.

## Architecture Patterns

### Recommended Changes Overview
```
BEFORE (Phase 14):                          AFTER (Phase 15):
agent.py:                                   agent.py:
  make_agent()                                make_agent()
    3 local tools                               MultiServerMCPClient (stdio)
    wrap ALL with error handling                async with client.session()
    SkillsMiddleware(file_backend)                load_mcp_tools(session) -> ~20 browser tools
    CompositeBackend(shell + file)                16 local tools (expanded)
                                                  wrap ONLY browser_ + playwright-test/ tools
                                                  SkillsMiddleware(composite_backend)
                                                  CompositeBackend(shell + file + skills)
```

### Pattern 1: MCP Session Lifecycle in make_agent()
**What:** The Playwright MCP server runs as a subprocess via stdio. The session must persist for the agent's entire lifetime because browser state (page, cookies, navigation) lives in that process.
**When to use:** This is THE pattern for Phase 15 -- replaces the current stub.

**Example (from classroom reference):**
```python
# Source: classroom backend/app/agents/web_mcp/agent.py
@asynccontextmanager
async def make_agent() -> AsyncIterator[Pregel]:
    context_middleware = WebContextInjectionMiddleware()

    client = MultiServerMCPClient({
        "web_mcp": {
            "transport": "stdio",
            "command": r"cmd",
            "args": ["/c", f"cd {settings.web_mcp_root} & ",
                     "npx", "playwright", "run-test-mcp-server"],
        }
    })

    async with client.session("web_mcp") as session:
        mcp_tools = await load_mcp_tools(session)
        all_tools = mcp_tools + get_local_tools()

        all_tools = wrap_tools_with_error_handling(
            all_tools,
            tool_patterns=["browser_", "playwright-test/"])

        web_agent = create_agent(
            model=llm,
            tools=all_tools,
            system_prompt=SYSTEM_PROMPT,
            middleware=[skills_middleware, context_middleware],
            backend=composite_backend,
            context_schema=WebAgentContext,
        )
        yield web_agent
```

**Key differences from our current stub:**
1. `client.session("web_mcp")` -- uses session context, NOT `load_mcp_tools(client, server_name=...)` like our API agent
2. MCP tools come FIRST: `mcp_tools + local_tools` (classroom), not `local + mcp` (our API pattern)
3. Error handler targets only browser tools: `tool_patterns=["browser_", "playwright-test/"]`
4. Session persists via `async with` -- browser state survives across tool calls

### Pattern 2: Config Settings for Playwright MCP
**What:** Three new settings for MCP workspace paths.
**When to use:** Add to `src/app/core/config.py`.

**Example (from classroom reference):**
```python
# In Settings class:
# Web MCP configuration
web_mcp_workspace_root: str = ""  # Root for web workspace files
web_mcp_root: str = ""  # Directory containing package.json with @playwright/test
web_mcp_skills_root: str = ""  # Root for skills SKILL.md files
```

Our version should use computed defaults based on `workspace_dir`:
```python
# Proposed for our config.py:
web_mcp_root: str = ""  # defaults to workspace_dir/{space_id}/web
```

### Pattern 3: Targeted Error Handler
**What:** Only wrap browser-related tools, not ALL tools.
**Why:** Browser tools frequently fail (element not found, timeout, navigation error). Local DB/file tools rarely fail. Wrapping ALL tools adds unnecessary overhead and hides real errors in DB operations.
**Change:** `tool_patterns=None` -> `tool_patterns=["browser_", "playwright-test/"]`

### Pattern 4: CompositeBackend Upgrade for Skills
**What:** SkillsMiddleware needs composite_backend (not file_backend) to route `/skills/` reads through the backend system.
**Current:** `SkillsMiddleware(backend=file_backend, sources=["/skills/"])`
**After:** `SkillsMiddleware(backend=composite_backend, sources=["/skills/"])` with composite routing `{"default": shell, "/": file, "/skills/": skills_backend}` -- or simpler, keep existing composite_backend which already routes file ops correctly.

### Pattern 5: System Prompt Rewrite
**What:** Replace current dual-mode (Exploratory QA / Component-Aware) prompt with classroom's 4-workflow structure.
**Workflows:**
1. **Generate Tests** (most common): Get sub_function -> planner skill -> save plan -> case-designer skill -> save cases -> generator skill -> save script -> verify artifacts
2. **Create Function**: Create function + sub-functions -> generate tests for each
3. **Execute Tests**: Get script -> download -> execute -> executor skill -> auto-heal if failed
4. **Auto-Heal** (triggered on failure): healer skill -> fix code -> save -> re-run (max 3 retries)

**Critical prompt rules from classroom:**
- Must call `planner_setup_page` or `generator_setup_page` BEFORE any browser operation
- Must `browser_snapshot()` after navigation and before verification
- Locator text must be preserved exactly (no "correcting" Chinese characters)
- Must auto-save artifacts after each generation step
- Must output progress frequently to avoid timeout

### Anti-Patterns to Avoid
- **Using `load_mcp_tools(client, server_name=...)` instead of `load_mcp_tools(session)`:** Our API agent uses the client-level API. The classroom web_mcp agent uses the session-level API because the Playwright MCP server requires a persistent session. The session pattern ensures browser state persists.
- **Wrapping ALL tools with error handler:** Browser tools fail frequently (expected). DB tools should NOT have their errors silently swallowed. Use targeted patterns.
- **Hardcoding MCP workspace path:** Must be configurable via settings, with workspace-aware resolution via `get_space_id()`.
- **Forgetting `npm install` in workspace:** The MCP server requires `@playwright/test` installed locally. If missing, `run-test-mcp-server` will fail.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Browser automation protocol | Custom subprocess wrapper for Playwright | Playwright Test MCP server (`run-test-mcp-server`) | Handles browser lifecycle, page state, element interaction, snapshots, locators -- 20+ tools for free |
| MCP tool loading | Manual tool registration | `langchain-mcp-adapters` `load_mcp_tools(session)` | Already proven in API agent. Handles tool schema conversion, async lifecycle. |
| Tool error handling for browser ops | Per-tool try/catch | `wrap_tools_with_error_handling(tools, tool_patterns=["browser_", "playwright-test/"])` | Already implemented in Phase 14. Just change pattern parameter. |
| Playwright config | Custom test runner config | Standard `playwright.config.ts` from classroom | Chromium project, HTML reporter, trace on first retry. Proven template. |

**Key insight:** The entire browser interaction layer is provided by the Playwright Test MCP server. We do NOT write any browser automation code -- the LLM calls MCP tools directly (browser_navigate, browser_click, etc.) and the MCP server translates these into real browser actions.

## Common Pitfalls

### Pitfall 1: MCP Session Scope Mismatch
**What goes wrong:** Using `load_mcp_tools(client, server_name=...)` (our API agent pattern) instead of `load_mcp_tools(session)` (classroom pattern). The client-level API may not maintain persistent stdio connection needed by Playwright.
**Why it happens:** Both APIs exist in langchain-mcp-adapters 0.2.2. The client-level pattern works for GitNexus (stateless tools), but Playwright MCP needs stateful session.
**How to avoid:** Use `async with client.session("web_mcp") as session:` + `load_mcp_tools(session)`. Match classroom pattern exactly.
**Warning signs:** Browser tools fail with "Must setup test before..." errors, or browser state lost between calls.

### Pitfall 2: Missing @playwright/test in Workspace
**What goes wrong:** `npx playwright run-test-mcp-server` fails because no local `@playwright/test` installation.
**Why it happens:** Playwright CLI 1.60.0 is installed globally, but `run-test-mcp-server` needs a local `node_modules/@playwright/test` in the working directory.
**How to avoid:** Phase plan must include `npm install @playwright/test` in the workspace/web directory. Create `package.json` and `playwright.config.ts` following classroom template.
**Warning signs:** MCP server exits immediately with module not found error.

### Pitfall 3: Windows cmd.exe Path in MCP Args
**What goes wrong:** MCP server fails to start because of incorrect command/args for Windows.
**Why it happens:** The `cd & npx` pattern requires `cmd /c` on Windows. Our API agent uses `node` directly for GitNexus, but Playwright MCP needs shell chaining.
**How to avoid:** Use exactly: `"command": "cmd", "args": ["/c", f"cd {web_mcp_root} & ", "npx", "playwright", "run-test-mcp-server"]`
**Warning signs:** MCP client connection timeout, empty tool list.

### Pitfall 4: Browser State Lost Between Calls
**What goes wrong:** Agent navigates to a page, then subsequent tool calls fail because browser has been reset.
**Why it happens:** MCP session ended prematurely (not using `async with client.session()`), or agent creates new session per request.
**How to avoid:** Ensure `async with client.session()` wraps the entire `yield web_agent` block. The session must not exit until the agent request completes.
**Warning signs:** "Must setup test before interacting with the page" errors appearing after initial navigation.

### Pitfall 5: Not Calling setup_page Before Browser Operations
**What goes wrong:** Agent tries `browser_navigate` without first calling `planner_setup_page` or `generator_setup_page`.
**Why it happens:** LLM skips initialization step, or system prompt doesn't emphasize it enough.
**How to avoid:** System prompt must contain explicit initialization instructions (classroom has detailed rules). The setup tools initialize the browser context and test state.
**Warning signs:** "Must setup test before interacting with the page" error from MCP tools.

### Pitfall 6: Error Handler Wrapping Non-Browser Tools
**What goes wrong:** DB tools, file tools have their errors wrapped into JSON, making debugging impossible.
**Why it happens:** Current code uses `tool_patterns=None` which wraps ALL tools.
**How to avoid:** Change to `tool_patterns=["browser_", "playwright-test/"]` -- only browser tools need graceful error handling.
**Warning signs:** DB operation failures return cryptic JSON instead of raising meaningful exceptions.

## Code Examples

### MCP Client Configuration (Windows stdio)
```python
# Source: classroom backend/app/agents/web_mcp/agent.py, adapted for our project
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from src.app.core.config import settings

client = MultiServerMCPClient({
    "web_mcp": {
        "transport": "stdio",
        "command": "cmd",
        "args": ["/c", f"cd {settings.web_mcp_root} & ",
                 "npx", "playwright", "run-test-mcp-server"],
    }
})
```

### Tool Combination Pattern
```python
# Source: classroom pattern -- MCP tools first, then local tools
async with client.session("web_mcp") as session:
    mcp_tools = await load_mcp_tools(session)
    all_tools = mcp_tools + get_local_tools()

    all_tools = wrap_tools_with_error_handling(
        all_tools,
        tool_patterns=["browser_", "playwright-test/"]
    )
```

### Workspace package.json for Playwright Test MCP
```json
{
  "name": "playwright-test-agents",
  "version": "1.0.0",
  "devDependencies": {
    "@playwright/test": "^1.58.2",
    "@types/node": "^25.0.3"
  }
}
```

### Config Settings Addition
```python
# Add to src/app/core/config.py Settings class
# Web MCP (Phase 15 - Playwright Test MCP server)
web_mcp_workspace_root: str = ""   # e.g. workspace/{space_id}/web
web_mcp_root: str = ""             # Directory with package.json for MCP server
web_mcp_skills_root: str = ""      # Skills root for web_mcp skills
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Playwright CLI via subprocess | Playwright Test MCP server | Playwright 1.58 (May 2026) | LLM calls browser tools directly, no shell command generation |
| Shell Backend for all ops | MCP tools for browser, Shell for scripts only | Phase 15 | Cleaner separation: browser = MCP, scripts = shell execute |
| wrap_tools(error, all) | wrap_tools(error, patterns=["browser_"]) | Phase 14 decision | Only browser tools get error wrapping. DB tools raise normally. |
| Dual-mode system prompt (QA/Component) | 4-workflow prompt (Generate/Create/Execute/Heal) | Classroom pattern | Aligns with actual usage patterns. MCP tools enable real workflows. |

**New capabilities unlocked by Playwright Test MCP:**
- `planner_setup_page` / `generator_setup_page` -- initialize browser context for specific tasks
- `browser_snapshot()` -- get page accessibility tree (replaces manual DOM inspection)
- `browser_generate_locator` -- let Playwright generate optimal selectors
- `browser_verify_*` tools -- purpose-built verification without writing code
- Persistent browser state across tool calls (cookies, navigation, form fills)

## Open Questions

1. **Local tool count and implementation scope**
   - What we know: Classroom has 16 local tools in 4 categories (function management, test artifacts, scripts, execution). Our API agent has ~28 tools including DB CRUD. Our current web agent has only 3 tools.
   - What's unclear: How many of the 16 classroom tools should we implement vs. adapt from our existing API agent's DB tools pattern. The classroom uses MinIO for storage; we use local filesystem + SQLite.
   - Recommendation: Start with the tools needed for the 4 core workflows. Function management (create_web_function, get_function_details, etc.) may map to existing DB models. Test artifact tools (save_web_test_plan, save_web_test_cases, save_web_test_script) need new implementation. Script tools (download, info, delete) use local filesystem. Execution tools (execute_web_script) reuse shell backend pattern.

2. **Skills source path**
   - What we know: Current SkillsMiddleware uses `sources=["/skills/"]` with file_backend. Classroom uses `sources=["/skills/web_mcp/"]` with composite_backend.
   - What's unclear: Whether to change the skills source path to `/skills/web_mcp/` to match classroom, or keep `/skills/` since our skills are already at `/workspace/default/web/skills/`.
   - Recommendation: Keep `sources=["/skills/"]` -- our 8 skills are already at `workspace/default/web/skills/{name}/SKILL.md`. Changing the path would require moving files.

3. **MCP workspace directory for each workspace**
   - What we know: Playwright Test MCP needs a working directory with `package.json` and `@playwright/test`. Classroom uses a fixed `web_mcp_root`.
   - What's unclear: Whether each workspace needs its own MCP working directory, or if one shared directory suffices.
   - Recommendation: One shared directory with `@playwright/test` installed. Tests run against different URLs, not different Playwright installations. Use `workspace/default/web/` as the MCP root.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Playwright CLI | MCP server host | Available | 1.60.0 | -- |
| Node.js | npx, MCP server runtime | Available | v22.14.0 | -- |
| npm/npx | Package management, MCP startup | Available | 10.9.2 | -- |
| langchain-mcp-adapters | MCP client | Available | 0.2.2 | -- |
| deepagents | Agent framework | Available | 0.6.1 | -- |
| @playwright/test (local) | MCP server functionality | Not installed | -- | Phase must include npm install |
| Python 3.12+ | Backend runtime | Available | 3.12.x | -- |

**Missing dependencies with no fallback:**
- `@playwright/test` local installation -- must be installed in workspace directory before MCP server can start. Phase plan must include this as an early task.

**Missing dependencies with fallback:**
- None identified.

## Sources

### Primary (HIGH confidence)
- Classroom reference: `d:/test_agent/2026-05-20-ai-test-agent-system-platform/ai-test-agent-system-platform/backend/app/agents/web_mcp/agent.py` -- Complete agent implementation with MCP integration
- Classroom reference: `d:/test_agent/2026-05-20-ai-test-agent-system-platform/ai-test-agent-system-platform/backend/app/agents/web_mcp/tool_registry.py` -- 16 local tools in 4 categories
- Classroom reference: `d:/test_agent/2026-05-20-ai-test-agent-system-platform/ai-test-agent-system-platform/backend/workspace/web_mcp/package.json` -- @playwright/test ^1.58.2 requirement
- Our codebase: `d:/test_agent/smart-test-platform/src/app/agents/web/agent.py` -- Current agent to upgrade
- Our codebase: `d:/test_agent/smart-test-platform/src/app/agents/api/agent.py` -- MCP pattern reference (GitNexus)
- Our codebase: `d:/test_agent/smart-test-platform/src/app/core/config.py` -- Settings class to extend
- Verified: Playwright CLI 1.60.0 installed, `run-test-mcp-server` available from 1.58+
- Verified: langchain-mcp-adapters 0.2.2 installed, `MultiServerMCPClient` + `load_mcp_tools` available
- Verified: deepagents 0.6.1 installed, `create_deep_agent` + `SkillsMiddleware` + `CompositeBackend` available

### Secondary (MEDIUM confidence)
- Playwright Test Agents documentation (playwright.dev/docs/test-agents) -- Test MCP server capabilities and tool list
- dev.to article on Playwright MCP servers -- Distinction between browser MCP and test MCP servers

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- All packages verified as installed. Classroom pattern proven.
- Architecture: HIGH -- Direct classroom reference for exact agent structure. Our stub already prepared.
- Pitfalls: HIGH -- Well-documented in classroom system prompt and our own Phase 14 experience.
- Tool scope: MEDIUM -- Exact number and implementation of local tools depends on design decisions (Open Question 1).

**Research date:** 2026-05-21
**Valid until:** 2026-06-21 (stable -- all libraries at mature versions)
