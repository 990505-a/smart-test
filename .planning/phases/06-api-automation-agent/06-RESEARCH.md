# Phase 6: API Automation Agent - Research

**Researched:** 2026-05-14
**Domain:** REST API test automation via AI Agent (DeepAgents + Skills + MASTEST methodology)
**Confidence:** HIGH

## Summary

Phase 6 builds an API Automation Agent that takes an OpenAPI/Swagger specification, designs test scenarios following the MASTEST academic methodology (arXiv:2511.18038), generates executable Playwright TypeScript API test scripts, validates syntax, computes coverage metrics, and produces Markdown reports. The implementation is heavily guided by classroom reference code from 2026-05-07, which provides a complete, working API Agent with all three Skills, three tools (api_parser, metrics, playwright_mcp_server), and a MASTEST system prompt.

The architecture reuses established patterns from Phase 5 (Web Agent): CompositeBackend (LocalShell + Filesystem), SkillsMiddleware for SKILL.md loading, and the tools.py separation pattern. New additions are the GitNexus MCP integration (18 code-knowledge-graph tools via stdio) and the Levenshtein dependency for usability metrics. The frontend already has the "API自动化" tab and graph.json routing -- no frontend work is needed (confirmed D-11).

**Primary recommendation:** Adapt classroom reference code directly. Copy 3 Skills, 3 tools, and the MASTEST system prompt with minimal changes (workspace paths, config.py settings references). Add GitNexus MCP as a new stdio connection in mcp_client.py. Install the `Levenshtein` Python package for the metrics tool.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** LLM parsing mode -- OpenAPI JSON/YAML injected into system prompt as text, LLM parses $ref and extracts operations. No separate Python $ref parser tool.
- **D-02:** api_parser tool exists for format/structure assistance, not recursive $ref resolution.
- **D-03:** Forced multi-stage flow: spec parsing -> scenario design -> script generation -> syntax validation -> coverage report. Each stage has a Skill.
- **D-04:** 3 Skills (classroom mode): test-scenario-design, playwright-api-testing, api-test-quality.
- **D-05:** Skills directory at workspace/api/skills/, matching classroom reference structure.
- **D-06:** Tool set: api_parser (parse helper) + metrics (coverage) + Playwright MCP Server. Same as classroom.
- **D-07:** Reuse Phase 5 CompositeBackend: LocalShellBackend (execute) + FilesystemBackend (file ops).
- **D-08:** GitNexus MCP integration -- user's existing code knowledge graph at D:/prpm/72codegraph/gitnexus/ with 18 tools including api_impact, tool_map, cross_ref, protocol_trace.
- **D-09:** GitNexus MCP config via config.py (similar to wiki-mcp stdio/SSE pattern).
- **D-10:** Markdown report format -- coverage data, status code distribution, test summary as Markdown text.
- **D-11:** No extra frontend work -- graph.json has api_agent route, AgentTabs has "API自动化" tab.
- **D-12:** HITL (API-08) deferred -- no LangGraph interrupts in this phase.

### Claude's Discretion
- Exact content of 3 SKILL.md files (copy from classroom reference)
- api_parser and metrics tool implementation details
- GitNexus MCP connection config (stdio vs SSE)
- SYSTEM_PROMPT wording and MASTEST methodology instructions

### Deferred Ideas (OUT OF SCOPE)
- Human-in-the-Loop (API-08): LangGraph interrupts deferred to later phase
- Graphical reports (antvis): Simple Markdown reports instead
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| API-01 | OpenAPI/Swagger spec parser ($ref resolution, param/response/schema extraction) | D-01: LLM parses spec text. api_parser.py provides `parse_api_spec()` as a deterministic tool with full $ref resolution, operation extraction, and schema flattening. Classroom code has complete implementation. |
| API-02 | MASTEST academic methodology (arXiv:2511.18038) | System prompt encodes 7-stage workflow from MASTEST paper. Skills encode scenario design, script generation, quality analysis patterns. Metrics tool implements formulas 1,3,4-5,7. |
| API-03 | Test scenario design (positive/negative/boundary/cross-operation sequences) | `test-scenario-design` Skill provides unit (per-operation) and system (cross-operation) scenario templates. Skill copied from classroom reference verbatim. |
| API-04 | Playwright TypeScript script generation (test.step, soft assertions) | `playwright-api-testing` Skill provides request fixture patterns, assertion templates, multi-step system test conventions. `playwright_mcp_server.py` provides Playwright MCP tools. |
| API-05 | Syntax validation tool (check_script_syntax) | `metrics.py::check_script_syntax()` -- deterministic bracket balance + Playwright construct detection. Returns JSON with valid/errors/error_count. |
| API-06 | Coverage calculation tool (compute_coverage, data type + status code coverage) | `metrics.py::compute_coverage()` -- deterministic formulas from MASTEST paper: scenario coverage (4-5), operation coverage (7), usability/Levenshtein (3). Requires `Levenshtein` package. |
| API-07 | GitNexus code knowledge graph MCP integration | GitNexus provides stdio MCP server at `D:/prpm/72codegraph/gitnexus/` with 18 tools. Key tools: `api_impact`, `route_map`, `shape_check`, `query`, `context`, `impact`, `cross_ref`, `protocol_trace`. Connected via stdio transport using `npx tsx` or `node dist/cli/index.js mcp`. |
| API-08 | Human-in-the-Loop integration (LangGraph interrupts) | DEFERRED per D-12. System prompt includes "PAUSE and ask user to review" language instead of programmatic interrupts. |
| API-09 | Test report graphical display | D-10: Markdown report format. `api-test-quality` Skill includes final report template with metrics table. No antvis charts. |
| UI-13 | Interrupt handling (tool call approval) | DEFERRED with API-08. No frontend interrupt UI needed in this phase. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| DeepAgents | >= 0.5.5 | Agent framework | Project-wide framework. SkillsMiddleware, CompositeBackend, create_deep_agent. |
| langchain-mcp-adapters | >= 0.1.13 | MCP client | MultiServerMCPClient for stdio/SSE connections. Already used for wiki-mcp, graphify. |
| PyYAML | 6.0.3 | OpenAPI YAML parsing | api_parser.py needs to parse YAML OpenAPI specs. Already installed. |
| requests | 2.32.5 | HTTP fetching | api_parser.py fetches OpenAPI specs from URLs. Already installed. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Levenshtein | (not yet installed) | Edit distance for usability metric | `compute_coverage()` uses Levenshtein.distance() for MASTEST formula 3 (usability). Must install. |
| pytest | 9.0.3 | Test framework | Agent import tests, tool unit tests. Already configured. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Levenshtein (C extension) | rapidfuzz (pure Python + C) | rapidfuzz has Levenshtein distance too, but classroom code uses `import Levenshtein` directly. Match classroom for consistency. |
| GitNexus stdio MCP | GitNexus SSE/HTTP | GitNexus uses stdio transport (ConfirmedStdioServerTransport). stdio is the established pattern in this project (wiki-mcp uses stdio). |

**Installation:**
```bash
# Only new dependency needed
cd D:/test_agent/smart-test-platform
.venv/Scripts/pip install Levenshtein
```

**Verification:**
```bash
.venv/Scripts/python -c "import Levenshtein; print(Levenshtein.__version__)"
```

## Architecture Patterns

### Recommended Project Structure
```
src/app/agents/api/
    __init__.py              # existing (empty)
    agent.py                 # REPLACE stub with full API Agent
    tools/
        __init__.py          # NEW: MASTEST_TOOLS list
        api_parser.py        # NEW: from classroom reference
        metrics.py           # NEW: from classroom reference
        playwright_mcp_server.py  # NEW: from classroom reference

workspace/api/
    skills/
        test-scenario-design/
            SKILL.md         # NEW: from classroom reference
        playwright-api-testing/
            SKILL.md         # NEW: from classroom reference
        api-test-quality/
            SKILL.md         # NEW: from classroom reference

src/app/core/
    config.py                # MODIFY: add GitNexus MCP settings
src/app/mcp/
    mcp_client.py            # MODIFY: add gitnexus entry

.gitignore                  # MODIFY: add !workspace/api/skills/ negation
```

### Pattern 1: CompositeBackend + SkillsMiddleware (from Phase 5)
**What:** Agent uses CompositeBackend(default=shell, routes={"/": file}) for both command execution and file operations. SkillsMiddleware loads SKILL.md files from FilesystemBackend.
**When to use:** Every agent that needs shell + file I/O + skills.
**Example:**
```python
# Source: Phase 5 web/tools.py pattern, adapted for API agent
from src.app.core.config import settings

workspace_dir = settings.workspace_dir / "api"
# NOT api_output root -- keep workspace_dir simple

shell_backend = LocalShellBackend(
    root_dir=workspace_dir,
    virtual_mode=False,
    inherit_env=True,
    timeout=180,
)

file_backend = FilesystemBackend(
    root_dir=workspace_dir,
    virtual_mode=True,
)

composite_backend = CompositeBackend(
    default=shell_backend,
    routes={"/": file_backend},
)

skills_middleware = SkillsMiddleware(
    backend=file_backend,
    sources=["/skills/"],  # resolves to workspace/api/skills/
)
```

### Pattern 2: Tool Registration via __init__.py
**What:** Tools module exports a flat `MASTEST_TOOLS` list that agent.py imports. Each tool is a `@tool`-decorated function wrapping a pure helper from a sibling module.
**When to use:** When agent needs multiple tools from separate modules.
**Example:**
```python
# tools/__init__.py pattern (from classroom reference)
from langchain_core.tools import tool
from .api_parser import parse_api_spec
from .metrics import check_script_syntax as _check_syntax
from .metrics import compute_coverage as _compute_coverage
from .playwright_mcp_server import playwright_api_tools

@tool
def parse_openapi_spec(spec_url: str) -> str:
    """Load and parse an OpenAPI/Swagger specification."""
    return json.dumps(parse_api_spec(spec_url), indent=2, default=str)

@tool
def check_script_syntax(script: str) -> str:
    """Check TypeScript test script for syntax issues."""
    return _check_syntax(script)

@tool
def compute_coverage(parsed_api_json: str, ...) -> str:
    """Compute deterministic test quality metrics."""
    return _compute_coverage(parsed_api_json, ...)

MASTEST_TOOLS: list = [
    parse_openapi_spec,
    check_script_syntax,
    compute_coverage,
] + playwright_api_tools
```

### Pattern 3: MCP Client Registration
**What:** Add GitNexus as a new entry in MultiServerMCPClient configuration, using stdio transport.
**When to use:** Connecting to any MCP server.
**Example:**
```python
# Source: mcp_client.py existing pattern
"gitnexus": {
    "transport": "stdio",
    "command": settings.gitnexus_mcp_command,
    "args": settings.gitnexus_mcp_args.split(),
}
```

### Pattern 4: Async MCP Tool Loading (from Phase 3 wiki-mcp)
**What:** Use `asyncio.new_event_loop().run_until_complete()` for module-level async tool fetching in playwright_mcp_server.py, avoiding `asyncio.run()` crashes inside LangGraph server.
**When to use:** Module-level initialization of MCP tools.
**Example:**
```python
# Source: Phase 03 decision -- asyncio.new_event_loop() for safe module-level async
import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient

client = MultiServerMCPClient({...})
playwright_api_tools = asyncio.new_event_loop().run_until_complete(client.get_tools())
```
NOTE: The classroom code uses `asyncio.run()` which works in standalone mode but crashes inside LangGraph server. The planner should use `asyncio.new_event_loop()` instead (established Phase 3 pattern).

### Anti-Patterns to Avoid
- **Hardcoded workspace paths:** Classroom code uses `Path(r"C:\Users\65132\Desktop\...")`. Must use `settings.workspace_dir / "api"` instead.
- **asyncio.run() at module level:** Crashes inside LangGraph server. Use `asyncio.new_event_loop().run_until_complete()` (Phase 3 pattern).
- **Hardcoded shell PATH:** Classroom code sets explicit Windows PATH. Use `inherit_env=True` instead (Phase 5 pattern).
- **Using `requests` (sync) in async context:** api_parser.py uses `requests.get()` which is sync. This is acceptable inside a `@tool` function (runs in thread pool by LangChain), but do NOT call it from async code directly.
- **Adding Playwright MCP to mcp_client.py:** The classroom uses a separate `playwright_mcp_server.py` that creates its own MCP client. This is the correct pattern -- the Playwright tools are loaded at module import time and merged into MASTEST_TOOLS. Do NOT add Playwright to the shared mcp_client.py.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| OpenAPI $ref resolution | Custom recursive resolver | api_parser.py's `_resolve_all_refs()` | Classroom code already handles circular refs, nested $ref, path/operation-level parameters |
| Coverage metrics formulas | Custom math functions | metrics.py's `compute_coverage()` | Implements MASTEST formulas 3,4-5,7 correctly with edge cases (empty sets, zero division) |
| TypeScript syntax checking | Full AST parser | `check_script_syntax()` heuristic + `npx tsc --noEmit` | Bracket balance + Playwright construct detection is sufficient for validation. Full checking via shell execute. |
| Edit distance calculation | Custom diff algorithm | `Levenshtein.distance()` | C-optimized, O(n*m) but fast. MASTEST formula 3 requires this. |

**Key insight:** The classroom reference provides battle-tested implementations for all deterministic tools. Adapt them with project path/config changes, but do not rewrite the logic.

## Common Pitfalls

### Pitfall 1: asyncio.run() vs new_event_loop()
**What goes wrong:** `asyncio.run()` crashes with "cannot be called from a running event loop" when playwright_mcp_server.py is imported inside LangGraph server.
**Why it happens:** LangGraph server already runs an event loop. `asyncio.run()` creates a new one, conflicting.
**How to avoid:** Use `asyncio.new_event_loop().run_until_complete(client.get_tools())` -- this creates an independent loop (Phase 3 decision).
**Warning signs:** ImportError or RuntimeError at agent module import time when LangGraph server starts.

### Pitfall 2: Hardcoded Workspace Paths
**What goes wrong:** Classroom code has `Path(r"C:\Users\65132\Desktop\workspace\testing\ai-test-agent-system\src\workspace")` which won't work on any other machine.
**Why it happens:** Classroom code was not designed for portability.
**How to avoid:** Use `settings.workspace_dir / "api"` consistently. All Phase 5 patterns already do this.
**Warning signs:** FileNotFoundError at runtime, or tests failing with path-related errors.

### Pitfall 3: Missing Levenshtein Package
**What goes wrong:** `import Levenshtein` fails because the package is not in pyproject.toml or installed.
**Why it happens:** Classroom code uses Levenshtein for usability metric but the project hasn't needed it before.
**How to avoid:** Install `Levenshtein` before running any tests. Add to pyproject.toml dependencies.
**Warning signs:** ImportError on metrics.py import.

### Pitfall 4: GitNexus Not Built/Not on PATH
**What goes wrong:** `gitnexus` command not found when MCP client tries to spawn it via stdio.
**Why it happens:** GitNexus is at `D:/prpm/72codegraph/gitnexus/` but may not be globally installed or the dist/ might be stale.
**How to avoid:** Use `node D:/prpm/72codegraph/gitnexus/dist/cli/index.js mcp` as the command, or `npx tsx D:/prpm/72codegraph/gitnexus/src/cli/index.ts mcp`. Verify the dist/ is built. Make this configurable via settings like wiki-mcp.
**Warning signs:** MCP client connection timeout or "command not found" error.

### Pitfall 5: .gitignore Missing workspace/api/skills/ Negation
**What goes wrong:** Skills files in workspace/api/skills/ are ignored by git because `workspace/*/` matches.
**Why it happens:** .gitignore has `workspace/*/` with only `!workspace/web/skills/` negation.
**How to avoid:** Add `!workspace/api/skills/` to .gitignore alongside the web/skills negation.
**Warning signs:** `git status` not showing new SKILL.md files after creation.

### Pitfall 6: Playwright MCP Server Tool Spam
**What goes wrong:** Playwright MCP server exposes many browser-control tools that confuse the API test agent.
**Why it happens:** The classroom code loads ALL playwright-api tools plus chart tools.
**How to avoid:** Consider filtering playwright_api_tools to only API-relevant tools (e.g., `api_request_context`, `post`, `get`, `put`, `delete`). Or keep all as classroom does and let the system prompt guide usage.
**Warning signs:** Agent trying to interact with browser elements instead of API endpoints.

### Pitfall 7: LLM Parsing Mode vs Deterministic Parsing Conflict
**What goes wrong:** D-01 says "LLM parses spec" but api_parser.py has a full deterministic parser with $ref resolution. Confusion about which path to use.
**Why it happens:** Two parsing strategies exist for the same input.
**How to avoid:** The `parse_openapi_spec` tool provides structured, resolved data. The LLM also receives the raw spec in the prompt. The tool result gives the LLM structured data to work with -- it is a supplement, not a replacement. The system prompt should instruct the agent to call `parse_openapi_spec` first, then use the structured result.
**Warning signs:** Agent trying to manually parse $ref references in prompt instead of using the tool.

## Code Examples

### API Agent Main File (adapted from classroom)
```python
# Source: classroom reference agent.py, adapted for project architecture
from __future__ import annotations

from pathlib import Path
from deepagents import create_deep_agent as create_agent
from deepagents.middleware import SkillsMiddleware
from langchain.chat_models import init_chat_model
from dotenv import load_dotenv

from src.app.agents.api.tools import MASTEST_TOOLS
from src.app.agents.api.tools import composite_backend, file_backend

load_dotenv()

llm = init_chat_model("deepseek:deepseek-chat")

SYSTEM_PROMPT = """..."""  # MASTEST system prompt from classroom reference

skills_middleware = SkillsMiddleware(
    backend=file_backend,
    sources=["/skills/"],
)

agent = create_agent(
    model=llm,
    tools=MASTEST_TOOLS,
    system_prompt=SYSTEM_PROMPT,
    middleware=[skills_middleware],
    backend=composite_backend,
)
```

### GitNexus MCP Config Entry
```python
# Source: mcp_client.py existing pattern, adapted for GitNexus
"gitnexus": {
    "transport": "stdio",
    "command": settings.gitnexus_mcp_command,
    "args": settings.gitnexus_mcp_args.split(),
}
```

### Config.py Settings Addition
```python
# Source: config.py existing pattern
# GitNexus MCP (Phase 6 - API Agent code knowledge graph)
gitnexus_mcp_command: str = "node"
gitnexus_mcp_args: str = "D:/prpm/72codegraph/gitnexus/dist/cli/index.js mcp"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| asyncio.run() for module-level MCP | asyncio.new_event_loop() | Phase 3 (2026-05-12) | Prevents crash inside LangGraph server event loop |
| Full Playwright MCP mode | Playwright CLI mode | Phase 5 decision D-04 | Token efficiency -- single execute tool vs many MCP tools |
| Hand-written system prompts | Classroom-adapted MASTEST prompts | Phase 6 (current) | Academic methodology grounding, proven in classroom |

**Deprecated/outdated:**
- Playwright MCP mode for browser testing: CLI mode preferred (D-04). For API testing, Playwright MCP server is still acceptable because API tests use `request` fixture, not browser.
- `asyncio.run()` at module level: Use `asyncio.new_event_loop().run_until_complete()` per Phase 3 pattern.

## Open Questions

1. **GitNexus startup command**
   - What we know: GitNexus has `dist/cli/index.js` with shebang, and `bin.gitnexus` pointing to it. Server uses stdio transport.
   - What's unclear: Whether `node dist/cli/index.js mcp` starts the MCP server correctly (the CLI may need a subcommand like `gitnexus mcp`).
   - Recommendation: Check by running `node D:/prpm/72codegraph/gitnexus/dist/cli/index.js mcp` manually. The `mcp.js` exists in dist/cli/ so the subcommand likely works. Configure command as "node" and args as the full path + "mcp".

2. **Playwright MCP Server tool filtering**
   - What we know: Classroom code loads ALL playwright-api tools + antv chart tools. The `@executeautomation/playwright-mcp-server` package exposes browser automation tools that are irrelevant for API testing.
   - What's unclear: Whether filtering is needed. The classroom code includes them all.
   - Recommendation: Start with the same approach as classroom (load all tools). The system prompt focuses the agent on API testing. Tool filtering can be added later if needed.

3. **GitNexus tool integration into agent workflow**
   - What we know: GitNexus has 18 tools including `api_impact`, `route_map`, `shape_check`, `query`. These could enrich API test design by providing source-code-level endpoint information.
   - What's unclear: Whether GitNexus tools should be loaded into the API agent directly (like wiki-mcp tools are loaded into testcase agent) or accessed via a separate mechanism.
   - Recommendation: Follow the wiki-mcp pattern -- register GitNexus in mcp_client.py, and consider loading GitNexus tools into the agent. However, CONTEXT.md D-06 specifies only api_parser + metrics + playwright_mcp_server as the tool set. GitNexus tools could be mentioned in the system prompt as available for deeper analysis, loaded via mcp_client if the agent needs them.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.13 | Runtime | Available | 3.13.2 | -- |
| DeepAgents | Agent framework | Available | >= 0.5.5 | -- |
| langchain-mcp-adapters | MCP client | Available | 0.1.13 | -- |
| PyYAML | OpenAPI parsing | Available | 6.0.3 | -- |
| requests | Spec URL fetching | Available | 2.32.5 | -- |
| Levenshtein | Usability metric | NOT installed | -- | pip install Levenshtein |
| npx | MCP server spawning | Available | 10.9.2 | -- |
| GitNexus | Code knowledge graph | NOT on PATH | dist built at D:/prpm/72codegraph/gitnexus/ | Use direct node path |
| pytest | Test framework | Available | 9.0.3 | -- |

**Missing dependencies with no fallback:**
- Levenshtein: Must install via `pip install Levenshtein` before running metrics.py. Add to pyproject.toml.

**Missing dependencies with fallback:**
- GitNexus CLI: Not on PATH, but dist/ is built. Use `node D:/prpm/72codegraph/gitnexus/dist/cli/index.js mcp` as the command. Agent works without GitNexus (graceful fallback like wiki-mcp).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 |
| Config file | pyproject.toml (no pytest.ini) |
| Quick run command | `.venv/Scripts/python -m pytest tests/test_api_agent.py -x` |
| Full suite command | `.venv/Scripts/python -m pytest tests/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| API-01 | api_parser parses OpenAPI JSON with $ref | unit | `pytest tests/test_api_tools.py::TestApiParser -x` | Wave 0 |
| API-02 | SYSTEM_PROMPT contains MASTEST workflow stages | unit | `pytest tests/test_api_agent.py::TestSystemPrompt -x` | Wave 0 |
| API-03 | test-scenario-design Skill loads correctly | unit | `pytest tests/test_api_skills.py -x` | Wave 0 |
| API-04 | playwright-api-testing Skill loads correctly | unit | `pytest tests/test_api_skills.py -x` | Wave 0 |
| API-05 | check_script_syntax validates TypeScript | unit | `pytest tests/test_api_tools.py::TestCheckSyntax -x` | Wave 0 |
| API-06 | compute_coverage returns correct metrics | unit | `pytest tests/test_api_tools.py::TestComputeCoverage -x` | Wave 0 |
| API-07 | GitNexus MCP config present in mcp_client | unit | `pytest tests/test_api_agent.py::TestMCPConfig -x` | Wave 0 |
| API-08 | DEFERRED -- no test needed | -- | -- | N/A |
| API-09 | api-test-quality Skill contains report template | unit | `pytest tests/test_api_skills.py -x` | Wave 0 |
| UI-13 | DEFERRED -- no test needed | -- | -- | N/A |

### Sampling Rate
- **Per task commit:** `.venv/Scripts/python -m pytest tests/test_api_agent.py tests/test_api_tools.py tests/test_api_skills.py -x`
- **Per wave merge:** `.venv/Scripts/python -m pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_api_agent.py` -- covers API-02, API-07 (agent import, system prompt, MCP config)
- [ ] `tests/test_api_tools.py` -- covers API-01, API-05, API-06 (api_parser, check_syntax, compute_coverage)
- [ ] `tests/test_api_skills.py` -- covers API-03, API-04, API-09 (3 Skill file existence and content)
- [ ] `Levenshtein` package install -- required before compute_coverage tests pass

## Sources

### Primary (HIGH confidence)
- Classroom reference code (2026-05-07): agent.py, tools/__init__.py, tools/api_parser.py, tools/metrics.py, tools/playwright_mcp_server.py, 3x SKILL.md files -- direct implementation source
- Existing project code: src/app/agents/web/agent.py, src/app/agents/web/tools.py, src/app/core/config.py, src/app/mcp/mcp_client.py -- patterns to follow
- GitNexus source: D:/prpm/72codegraph/gitnexus/src/mcp/tools.ts, server.ts -- 18 tool definitions, stdio transport confirmed

### Secondary (MEDIUM confidence)
- MASTEST paper (arXiv:2511.18038): Could not read PDF directly (pdftoppm not available). Methodology details inferred from classroom code's system prompt and metrics.py docstrings, which reference specific formula numbers (1,3,4-5,7).
- GitNexus CLI subcommand `mcp`: Inferred from `dist/cli/mcp.js` existence and `server.ts` using stdio transport. Not verified by running.

### Tertiary (LOW confidence)
- None -- all findings are from direct code reading.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries verified installed or installable; only Levenshtein missing and has clear install path.
- Architecture: HIGH -- patterns established in Phases 1-5; classroom reference provides complete implementation.
- Pitfalls: HIGH -- asyncio.run and hardcoded path issues are known from Phase 3/5 experience.
- MASTEST methodology: MEDIUM -- inferred from classroom code docstrings and skill content; could not verify against original paper.

**Research date:** 2026-05-14
**Valid until:** 2026-06-14 (stable -- based on established patterns and reference code)
