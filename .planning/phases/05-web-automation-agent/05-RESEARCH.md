# Phase 5: Web Automation Agent - Research

**Researched:** 2026-05-13
**Domain:** Web browser automation testing via AI Agent with Playwright CLI + Skills system
**Confidence:** HIGH

## Summary

Phase 5 builds a dual-mode Web Automation Agent that generates executable Playwright TypeScript test scripts. The classroom reference at `D:/test_agent/2026-05-07-ai-test-agent-system/` provides a complete, production-quality implementation that this phase adapts into the existing smart-test-platform architecture.

The agent supports two mutually exclusive modes: (A) Exploratory QA, where the user provides a URL and the agent runs a 6-phase professional QA workflow using playwright-cli; and (B) Component-Aware Testing, where the user provides a source code repository and the agent runs a 7-Agent Director Pipeline (Script Analyst through Continuity Lead) to produce deterministic POM-based Playwright tests. The classroom reference implements all of this via DeepAgents with SkillsMiddleware, CompositeBackend (LocalShell + Filesystem), and 5 Skills with detailed SKILL.md files and reference guides.

The primary work is adaptation, not invention. The classroom code's agent.py (~90 lines), tools.py (~177 lines), and 5 Skills directories (with 25+ reference files totaling ~5000 lines) are directly portable, requiring only path adjustments, import path fixes, and integration with the project's existing config/middleware patterns.

**Primary recommendation:** Copy the classroom reference code with mechanical adaptations (workspace paths, import paths, config integration). Do not redesign the architecture.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** LLM intelligent mode detection via system prompt rules (URL -> exploratory QA; repo/git/ path keywords -> component-aware)
- **D-02:** `detect_test_mode` tool with regex matching returning MODE_A_QA / MODE_B_COMPONENT / ASK_CLARIFICATION
- **D-03:** Component-aware testing requires full implementation with Git repo URL + Graphify MCP source analysis
- **D-04:** Single `execute` tool -- agent passes Playwright command string, backend uses subprocess (minimal LLM token consumption)
- **D-05:** All 4 Playwright features in Phase 5: session management (--storage-state), video recording (--video), Trace tracking (--trace on), network control (route.fulfill())
- **D-06:** CompositeBackend = LocalShellBackend (execute commands) + FilesystemBackend (read/write files)
- **D-07:** Exploratory QA uses forced multi-stage flow via pw-dogfood Skill's 6-phase workflow
- **D-08:** 5 independent Skills with SKILL.md: playwright-cli, agent-browser, pw-dogfood, agent-browser-vs-playwright-cli, component-aware-web-automation
- **D-09:** Skills directory at workspace/web/skills/ (matches classroom reference)
- **D-10:** 7-Agent Director Pipeline via Skill references (load 7 guide files sequentially from component-aware-web-automation/references/)
- **D-11:** No DeepAgents SubAgent or LangGraph multi-node graph -- single agent loads guides sequentially
- **D-12:** 7 roles in fixed order: Script Analyst -> Stage Manager -> Blocking Coach -> Set Designer -> Choreographer -> Assistant Director -> Continuity Lead

### Claude's Discretion
- Specific SKILL.md content copied/adapted from classroom reference
- detect_test_mode regex matching rules details
- ensure_output_dir directory structure and naming conventions
- check_environment CLI dependency check list
- SYSTEM_PROMPT specific wording and instruction details
- CompositeBackend routing configuration details

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| WEB-01 | Web Agent dual-mode auto-detection (URL -> exploratory QA; source repo -> component-aware) | D-01/D-02: detect_test_mode tool + LLM prompt rules. Classroom tools.py has regex-based detection function. |
| WEB-02 | Playwright CLI integration (session mgmt, storage state, network control, multi-tab, video recording) | D-04/D-05/D-06: CompositeBackend with LocalShellBackend for execute. playwright-cli SKILL.md covers all commands. |
| WEB-03 | Exploratory QA skill (playwright-cli) -- 6-phase professional QA flow | D-07/D-08: pw-dogfood SKILL.md defines 6-phase workflow (Plan/Setup -> Systematic Exploration -> Evidence Collection -> Advanced Testing -> Categorize -> Report). |
| WEB-04 | Agent-Browser mode (agent-browser skill) | D-08: agent-browser SKILL.md provides CLI reference. agent-browser-vs-playwright-cli SKILL.md guides framework selection. |
| WEB-05 | Professional QA skill (pw-dogfood) -- system exploration/evidence/performance/security/accessibility/responsive | D-07/D-08: pw-dogfood SKILL.md + 4 references (accessibility-testing, issue-taxonomy, performance-testing, security-checks) + report template. |
| WEB-06 | 7-Agent Director Pipeline (Script Analyst -> Continuity Lead) | D-10/D-11/D-12: component-aware-web-automation SKILL.md + 7 reference guides in references/ directory. Single agent loads guides sequentially. |
| WEB-07 | Component-aware test skill -- source analysis -> data-testid injection -> POM generation | D-03/D-08: component-aware-web-automation SKILL.md defines Agents 1-4 for static analysis phase. Graphify MCP for source code analysis. |
| WEB-08 | Auto-generate TypeScript test scripts (with trace/screenshots evidence) | D-04/D-05/D-06: Agents 5-6 generate Playwright TypeScript tests. Agent 7 executes with evidence capture. ARTIFACT_CONTRACT.md defines output formats. |
| UI-14 | Sub-agent visualization display | Frontend AgentTabs already routes to web_agent. Visualization of 7-agent pipeline progress needs a new component showing pipeline stage status. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| DeepAgents | 0.5.9 (installed) | Agent framework with Skills/Backend/Middleware | Project standard, provides CompositeBackend + SkillsMiddleware |
| LangChain Core | >= 0.3.x | LLM abstraction, tool registration | Required by DeepAgents, @tool decorator for custom tools |
| playwright-cli | latest (npm) | Browser automation CLI | D-04: CLI mode for token efficiency, single execute command |
| agent-browser | latest (npm) | Alternative browser CLI | D-08: Rust-based, faster than playwright-cli for most tasks |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| CompositeBackend | deepagents 0.5.9 | Routes shell vs filesystem operations | D-06: LocalShell for execute, Filesystem for read/write |
| LocalShellBackend | deepagents 0.5.9 | Execute shell commands | D-04/D-06: Runs playwright-cli/agent-browser commands |
| FilesystemBackend | deepagents 0.5.9 | Virtual filesystem for Skills and artifacts | D-06/D-09: Reads SKILL.md files and writes test artifacts |
| SkillsMiddleware | deepagents 0.5.9 | Injects SKILL.md content into system prompt | D-08: Loads 5 Skills from workspace/web/skills/ |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Playwright CLI mode | Playwright MCP mode | MCP exposes many tools, confusing for agent. CLI uses single execute tool per CLAUDE.md decision. |
| CompositeBackend | Separate backends | CompositeBackend provides routing in one object. Separate backends require manual dispatch. |
| agent-browser | playwright-cli only | agent-browser is faster (Rust daemon) but Chromium-only. playwright-cli supports cross-browser and tracing. Both available per skill selection. |

**Installation:**
```bash
# Backend (already installed in .venv)
# No new Python packages needed for Phase 5

# CLI tools (may need installation)
npm install -g @playwright/cli@latest   # playwright-cli
npm install -g agent-browser             # agent-browser (optional)
```

**Version verification:**
- DeepAgents 0.5.9 confirmed installed (verified via `python -c "import deepagents; print(deepagents.__version__)"`)
- Node.js v22.14.0 confirmed available
- playwright-cli: NOT on PATH (needs installation)
- agent-browser: NOT on PATH (optional, needs installation)

## Architecture Patterns

### Recommended Project Structure
```
src/
├── app/
│   ├── agents/
│   │   └── web/
│   │       ├── __init__.py       # (exists, empty)
│   │       ├── agent.py          # REPLACE stub with full Web Agent
│   │       ├── tools.py          # NEW: detect_test_mode, check_environment, ensure_output_dir
│   │       └── validate_agent.py # NEW: Agent validation script (optional, from classroom)
│   ├── core/
│   │   └── config.py             # MODIFY: add Graphify MCP config
│   └── mcp/
│       └── mcp_client.py         # MODIFY: uncomment Graphify MCP entry
workspace/                         # (created at project root by config.py)
└── web/
    └── skills/                    # NEW: 5 Skills directories
        ├── playwright-cli/
        │   ├── SKILL.md
        │   └── references/       # 9 reference files
        ├── agent-browser/
        │   └── SKILL.md
        ├── agent-browser-vs-playwright-cli/
        │   └── SKILL.md
        ├── pw-dogfood/
        │   ├── SKILL.md
        │   ├── references/       # 4 reference files
        │   └── templates/        # report-template.md
        └── component-aware-web-automation/
            ├── SKILL.md
            └── references/       # 7 agent guide files
```

### Pattern 1: Dual-Mode Agent with CompositeBackend
**What:** Single agent with two mutually exclusive workflows, backed by CompositeBackend that routes shell commands to LocalShellBackend and file operations to FilesystemBackend.
**When to use:** Always -- this is the core architecture for the Web Agent.
**Example:**
```python
# Source: classroom reference src/app/agents/web/tools.py
from deepagents.backends import CompositeBackend, FilesystemBackend, LocalShellBackend

shell = LocalShellBackend(root_dir=workspace_dir, virtual_mode=False, inherit_env=True, timeout=180)
file = FilesystemBackend(root_dir=workspace_dir, virtual_mode=True)
composite = CompositeBackend(default=shell, routes={"/": file})
```

### Pattern 2: SkillsMiddleware for Web Skills
**What:** SkillsMiddleware loads SKILL.md files from workspace/web/skills/ into the system prompt, providing the agent with knowledge of playwright-cli, pw-dogfood, etc.
**When to use:** At agent creation time, as outer middleware layer.
**Example:**
```python
# Source: classroom reference src/app/agents/web/agent.py
skills_middleware = SkillsMiddleware(
    backend=file_backend,  # FilesystemBackend rooted at workspace/
    sources=["/web/skills/"],
)
```

### Pattern 3: Custom Tools as Plain Functions
**What:** Three custom tools (detect_test_mode, check_environment, ensure_output_dir) registered as plain Python functions passed to create_deep_agent(tools=[...]). DeepAgents wraps them automatically.
**When to use:** All three tools in tools.py.
**Example:**
```python
# Source: classroom reference src/app/agents/web/tools.py
def detect_test_mode(user_request: str) -> str:
    """Analyze user request and decide testing mode."""
    url_pattern = re.compile(r"https?://[^\s\"']+")
    has_url = bool(url_pattern.search(user_request))
    path_markers = [r"[a-zA-Z]:\\", r"/home/", r"/Users/", r"git@", r"github\.com", ...]
    has_repo = any(re.search(marker, user_request) for marker in path_markers)
    if has_repo and not has_url: return "MODE_B_COMPONENT"
    if has_url and not has_repo: return "MODE_A_QA"
    if has_url and has_repo: return "MODE_B_COMPONENT"
    return "ASK_CLARIFICATION"
```

### Pattern 4: Sequential 7-Agent Pipeline via Skill References
**What:** Single agent loads guide files one at a time from component-aware-web-automation/references/, adopting each role in sequence. Agent outputs pass through the workspace filesystem, not conversation memory.
**When to use:** Mode B (component-aware testing) only.
**Example:**
```python
# Agent reads references sequentially via file_backend.read()
# Phase 1: Setup
#   read("/web/skills/component-aware-web-automation/references/script-analyst-guide.md") -> act as Script Analyst
#   read("/web/skills/component-aware-web-automation/references/stage-manager-guide.md") -> act as Stage Manager
#   ... etc through Continuity Lead
```

### Anti-Patterns to Avoid
- **Registering @tool decorator on custom tools:** The classroom reference uses plain functions passed to create_deep_agent(tools=[...]). DeepAgents auto-wraps them. Do NOT use @tool decorator like the TestCase Agent's export_test_cases -- the Web Agent tools are simpler and don't need LangChain @tool.
- **Using multiple agents or SubAgent:** D-11 explicitly forbids DeepAgents SubAgent or LangGraph multi-node graph. Single agent, sequential guide loading.
- **Hardcoding Playwright commands in system prompt:** The system prompt references Skills by name. The actual command details live in SKILL.md files. This keeps the prompt small and Skills updatable.
- **Creating workspace/ at module level with hardcoded path:** Use config.py's settings.workspace_dir or the same Path(__file__).parent resolution pattern as the stub.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Browser command execution | Custom subprocess wrapper | LocalShellBackend + DeepAgents built-in execute tool | DeepAgents provides sandboxed execution, timeout, output capture |
| Skill file loading | Custom file reader | SkillsMiddleware | Handles SKILL.md parsing, source path resolution, system prompt injection |
| Mode detection regex | LLM-only mode selection | detect_test_mode tool + LLM prompt rules | Regex is deterministic and cheap; LLM adds intelligence for edge cases |
| Output directory creation | Manual os.makedirs | ensure_output_dir tool with mode-specific structure | Mode A needs screenshots/traces/videos/storage; Mode B needs poms/tests/references |
| Report template formatting | Custom Markdown builder | pw-dogfood/templates/report-template.md | Professional template with severity badges, evidence tables, coverage metrics |

**Key insight:** The classroom reference has already solved these problems. Copy the solutions, don't redesign them.

## Common Pitfalls

### Pitfall 1: CompositeBackend Routing Misconfiguration
**What goes wrong:** CompositeBackend routes are path-prefix based. If routes={"/": file} routes ALL paths to FilesystemBackend, shell commands still go to the default (shell), but the agent's built-in file operations might conflict.
**Why it happens:** Misunderstanding that CompositeBackend routes by operation type (file ops vs execute ops), not just path prefix.
**How to avoid:** Match classroom reference exactly: `CompositeBackend(default=shell, routes={"/": file})`. The default handles execute(), routes handle read/write/ls file operations.
**Warning signs:** Agent can execute commands but cannot read SKILL.md files, or vice versa.

### Pitfall 2: Workspace Path Mismatch Between Skills and Tools
**What goes wrong:** SkillsMiddleware reads from one path root while ensure_output_dir writes to a different path root.
**Why it happens:** SkillsMiddleware needs FilesystemBackend rooted at workspace/ (to find /web/skills/), but LocalShellBackend needs root_dir for command execution working directory.
**How to avoid:** Both backends use the same workspace_dir. SkillsMiddleware sources=["/web/skills/"]. ensure_output_dir writes to workspace_dir / "web-output". This matches the classroom reference.
**Warning signs:** Agent loads Skills correctly but write_file fails with path not found, or vice versa.

### Pitfall 3: Windows PATH for LocalShellBackend
**What goes wrong:** playwright-cli or agent-browser not found when LocalShellBackend tries to execute commands.
**Why it happens:** LocalShellBackend inherits env from the process, but npm global bin may not be on PATH in the Python process.
**How to avoid:** Classroom reference explicitly sets `env={"PATH": "..."}` in LocalShellBackend. Adapt this to the project's environment by either: (a) setting PATH in .env, or (b) inheriting env with `inherit_env=True` (current project pattern).
**Warning signs:** check_environment reports tools unavailable despite npm install succeeding.

### Pitfall 4: Skill File Size Bloating System Prompt
**What goes wrong:** Loading all 5 SKILL.md files into the system prompt consumes too many tokens.
**Why it happens:** pw-dogfood SKILL.md alone is ~530 lines, playwright-cli SKILL.md is ~350 lines.
**How to avoid:** SkillsMiddleware with sources=["/web/skills/"] loads SKILL.md summaries (frontmatter + first section), not full references. The agent reads references on demand via read_file. This is the intended pattern -- the SKILL.md acts as a directory index, not the full content.
**Warning signs:** LLM runs out of context or produces low-quality responses.

### Pitfall 5: Graphify MCP Not Configured
**What goes wrong:** Mode B (component-aware testing) needs Graphify MCP for source code analysis, but it's commented out in mcp_client.py.
**Why it happens:** Graphify was deferred to later phases in the MCP client setup.
**How to avoid:** Uncomment and configure Graphify MCP entry in mcp_client.py. The config needs the Graphify command path and args.
**Warning signs:** Agent enters Mode B but cannot analyze source code, falls back to runtime-only testing.

### Pitfall 6: Frontend Sub-Agent Visualization Not Connected
**What goes wrong:** UI-14 requires sub-agent visualization but the frontend has no component to show 7-agent pipeline progress.
**Why it happens:** The existing AgentTabs only handles agent selection, not sub-agent state.
**How to avoid:** Design a simple pipeline status component that shows the current stage in the 7-agent sequence. The agent can emit structured messages indicating which guide it's currently following.
**Warning signs:** Users have no visibility into which pipeline stage is active.

## Code Examples

### Web Agent Main File (Adapted from Classroom)
```python
# Source: classroom reference src/app/agents/web/agent.py (adapted for project)
from pathlib import Path
from deepagents import create_deep_agent as create_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, LocalShellBackend
from deepagents.middleware import SkillsMiddleware
from langchain.chat_models import init_chat_model
from dotenv import load_dotenv

from app.agents.web.tools import (
    check_environment, detect_test_mode, ensure_output_dir,
    composite_backend, file_backend, output_root,
)
from app.core.config import settings

load_dotenv()

llm = init_chat_model("deepseek:deepseek-chat")

# Path resolution: match existing project pattern
workspace_dir = settings.workspace_dir
output_root = workspace_dir / "web-output"
output_root.mkdir(parents=True, exist_ok=True)

# FilesystemBackend for skills and artifacts
file_backend = FilesystemBackend(root_dir=workspace_dir, virtual_mode=True)

# LocalShellBackend for command execution
shell_backend = LocalShellBackend(root_dir=workspace_dir, virtual_mode=False, inherit_env=True, timeout=180)

# CompositeBackend: default=shell for execute, routes={"/": file} for file ops
composite_backend = CompositeBackend(default=shell_backend, routes={"/": file_backend})

SYSTEM_PROMPT = """..."""  # Dual-mode system prompt (adapted from classroom)

skills_middleware = SkillsMiddleware(backend=file_backend, sources=["/web/skills/"])

agent = create_agent(
    model=llm,
    tools=[detect_test_mode, check_environment, ensure_output_dir],
    backend=composite_backend,
    middleware=[skills_middleware],
    system_prompt=SYSTEM_PROMPT,
)
```

### Tools File Pattern (from Classroom)
```python
# Source: classroom reference src/app/agents/web/tools.py
import re, subprocess, os
from datetime import datetime
from pathlib import Path
from typing import Any

def detect_test_mode(user_request: str) -> str:
    """Analyze user request -> MODE_A_QA / MODE_B_COMPONENT / ASK_CLARIFICATION"""
    url_pattern = re.compile(r"https?://[^\s\"']+")
    has_url = bool(url_pattern.search(user_request))
    path_markers = [r"[a-zA-Z]:\\", r"/home/", r"/Users/", r"git@", r"github\.com",
                    r"\.git", r"src/", r"repo", r"project path", r"source code", r"codebase"]
    has_repo = any(re.search(m, user_request) for m in path_markers)
    if has_repo and not has_url: return "MODE_B_COMPONENT"
    if has_url and not has_repo: return "MODE_A_QA"
    if has_url and has_repo: return "MODE_B_COMPONENT"
    return "ASK_CLARIFICATION"

def check_environment() -> dict[str, Any]:
    """Verify playwright-cli and agent-browser are available."""
    results = {"platform": os.name, "tools": {}}
    for tool in ["playwright-cli", "agent-browser"]:
        # Check availability with version
        ...
    return results

def ensure_output_dir(mode: str, label: str = "") -> str:
    """Create timestamped artifact directory for current testing session."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_label = re.sub(r"[^\w\-]", "_", label)[:40] if label else "session"
    if mode == "MODE_A_QA":
        root = output_root / "qa" / f"{safe_label}_{ts}"
        for sub in ("screenshots", "traces", "videos", "storage"):
            (root / sub).mkdir(parents=True, exist_ok=True)
    elif mode == "MODE_B_COMPONENT":
        root = output_root / "tests" / f"{safe_label}_{ts}"
        for sub in ("poms", "tests", "references"):
            (root / sub).mkdir(parents=True, exist_ok=True)
    return str(root.resolve())
```

### System Prompt Structure (from Classroom)
```python
# Source: classroom reference agent.py SYSTEM_PROMPT (key sections)
SYSTEM_PROMPT = """# Web Automation Testing Agent

You orchestrate two mutually exclusive testing workflows. Never run both simultaneously.

## Mode Selection
- User provides a source-code repository path -> Mode B: Component-Aware Test Generation
- User provides only a target URL -> Mode A: Exploratory QA Testing
- Neither -> Ask the user for clarification

## Mode A: Exploratory QA (Target URL)
1. Load `agent-browser-vs-playwright-cli` skill to choose browser framework.
2. Load `pw-dogfood` skill and follow its 6-phase workflow strictly.
3. Load `agent-browser` or `playwright-cli` skill only when you need command-level reference.
4. Save all evidence to `{output_root / "qa"}/{{timestamp}}/`.
5. Final deliverable: `report.md` using report template.

## Mode B: Component-Aware Test Generation (Source Repo)
1. Load `component-aware-web-automation` skill and execute its 7-Agent Pipeline in strict order.
2. Agent outputs pass through workspace filesystem; never keep them in conversation memory.
3. Save all artifacts to `{output_root / "tests"}/{{project_name}}/`.
4. Final deliverables: component-registry.json, locator-catalog.json, poms/*.ts, tests/*.spec.ts.

## Universal Rules
- Do NOT repeat skill internals in reasoning -- load skill via read_file when needed.
- Before any browser command, verify dependencies with check_environment.
- One mode per session.
"""
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Playwright MCP (many tools) | Playwright CLI (single execute) | D-04 in CLAUDE.md | Fewer LLM tokens, simpler agent cognition |
| Multiple agent nodes | Single agent + Skill references | D-11 in CONTEXT.md | Lower complexity, matches classroom pattern |
| CSS selectors in tests | data-testid + POM pattern | Classroom reference | Deterministic tests, survives refactoring |
| Runtime DOM scraping | Source code static analysis | Classroom Agent 1 | Upstream understanding, covers all state permutations |

**Deprecated/outdated:**
- Playwright MCP mode for agent integration: CLAUDE.md explicitly prefers CLI mode for token efficiency
- Multi-agent graph architectures for the 7-agent pipeline: D-11 decides against this

## Open Questions

1. **Graphify MCP Installation Path**
   - What we know: Graphify MCP is commented out in mcp_client.py. It's needed for Mode B (component-aware testing) to analyze source code.
   - What's unclear: Whether Graphify is installed and what its command/args should be.
   - Recommendation: Plan for graceful fallback -- agent works in Mode A without Graphify. Mode B can use file-based source analysis as interim. Add Graphify config when available.

2. **playwright-cli / agent-browser Availability**
   - What we know: Neither tool is on PATH in the current environment. Node.js v22.14.0 and npm 10.9.2 are available.
   - What's unclear: Whether these should be installed globally or locally.
   - Recommendation: Add installation step to Wave 0. check_environment tool will verify at runtime. Agent degrades gracefully if tools unavailable.

3. **UI-14 Sub-Agent Visualization Scope**
   - What we know: The requirement asks for sub-agent visualization. The current frontend has no such component.
   - What's unclear: How detailed the visualization should be (simple text status vs. full pipeline diagram).
   - Recommendation: Start with a lightweight text-based stage indicator in the chat response. The agent emits stage markers like "[Script Analyst]" in its messages. A future enhancement can add a dedicated visual component.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node.js | playwright-cli, agent-browser | Available | v22.14.0 | -- |
| npm | Installing CLI tools | Available | 10.9.2 | -- |
| playwright-cli | Mode A + Mode B browser testing | Not installed | -- | Agent detects and reports unavailability |
| agent-browser | Alternative browser CLI | Not installed | -- | Optional, playwright-cli sufficient |
| DeepAgents 0.5.9 | Agent framework | Available | 0.5.9 | -- |
| Python 3.12+ | Backend runtime | Available | 3.12.x | -- |
| Graphify MCP | Mode B source code analysis | Not configured | -- | Agent falls back to file-based analysis |
| npx | Running local CLI tools | Available | 10.9.2 | -- |

**Missing dependencies with no fallback:**
- None blocking. Both modes degrade gracefully: Mode A reports that playwright-cli is not installed; Mode B can use file-based source analysis instead of Graphify MCP.

**Missing dependencies with fallback:**
- playwright-cli: Agent's check_environment tool detects and reports. User can install via `npm install -g @playwright/cli@latest`.
- agent-browser: Optional alternative. playwright-cli is the primary tool.
- Graphify MCP: Mode B uses read_file to analyze source code directly. Graphify enhances the analysis but is not strictly required.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing) |
| Config file | pyproject.toml (no explicit pytest config -- uses defaults) |
| Quick run command | `python -m pytest tests/ -x -q` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| WEB-01 | detect_test_mode returns correct mode for URL, repo path, ambiguous input | unit | `python -m pytest tests/test_web_tools.py::test_detect_test_mode -x` | Wave 0 |
| WEB-02 | LocalShellBackend executes playwright-cli commands | integration | `python -m pytest tests/test_web_tools.py::test_shell_execute -x` | Wave 0 |
| WEB-03/04/05 | Skills load and contain expected content | unit | `python -m pytest tests/test_web_skills.py::test_skill_load -x` | Wave 0 |
| WEB-06/07 | 7 reference guides exist and are readable | unit | `python -m pytest tests/test_web_skills.py::test_reference_guides -x` | Wave 0 |
| WEB-08 | ensure_output_dir creates correct directory structure | unit | `python -m pytest tests/test_web_tools.py::test_ensure_output_dir -x` | Wave 0 |
| WEB-01 | Agent imports and creates successfully | smoke | `python -m pytest tests/test_web_agent.py::test_agent_import -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_web_tools.py tests/test_web_skills.py -x -q`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_web_tools.py` -- covers WEB-01 (detect_test_mode), WEB-02 (shell execute), WEB-08 (ensure_output_dir), check_environment
- [ ] `tests/test_web_skills.py` -- covers WEB-03/04/05/06/07 (Skill loading, reference guide readability)
- [ ] `tests/test_web_agent.py` -- covers WEB-01 (agent import and creation)

## Sources

### Primary (HIGH confidence)
- Classroom reference code: `D:/test_agent/2026-05-07-ai-test-agent-system/2026-05-07-ai-test-agent-system/ai-test-agent-system/` -- full implementation verified line by line
- Project source code: `D:/test_agent/smart-test-platform/src/` -- existing patterns verified
- DeepAgents 0.5.9: CompositeBackend, LocalShellBackend, FilesystemBackend, SkillsMiddleware APIs verified via `help()` in installed package

### Secondary (MEDIUM confidence)
- CONTEXT.md decisions: User-verified architecture choices from discussion phase
- CLAUDE.md stack decisions: Playwright CLI preference over MCP, technology stack constraints

### Tertiary (LOW confidence)
- Graphify MCP integration details: Commented out in mcp_client.py, exact command/args unknown

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries installed and verified, classroom reference provides proven patterns
- Architecture: HIGH -- classroom reference has complete working implementation, adaptation is mechanical
- Pitfalls: HIGH -- identified from reading classroom code and comparing with existing project patterns
- Skills content: HIGH -- all 25+ files read and analyzed from classroom reference
- Graphify MCP: LOW -- not yet configured, exact integration unclear

**Research date:** 2026-05-13
**Valid until:** 2026-06-13 (stable domain, no fast-moving dependencies)
