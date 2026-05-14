# Phase 7: Multi-Workspace & Infrastructure Hardening - Research

**Researched:** 2026-05-14
**Domain:** LangGraph configurable mechanism, multi-workspace isolation, HTTP resilience patterns
**Confidence:** HIGH

## Summary

Phase 7 introduces two independent but complementary concerns: (1) multi-workspace isolation via LangGraph's `configurable` mechanism with `space_id` propagation from frontend to backend, and (2) infrastructure resilience via `httpx.AsyncClient` connection pooling, exponential backoff retry, and circuit breaker patterns wrapping external service calls.

The LangGraph API already provides the plumbing for per-request configuration. The frontend `@langchain/langgraph-sdk` v1.9.1 `useStream.submit()` accepts `SubmitOptions.config.configurable` which flows through to Python agents via `langgraph.config.get_config()["configurable"]`. The key challenge is that all three agents currently use **module-level backend instantiation** with hardcoded `workspace_dir` paths -- these must be refactored to factory/lazy patterns that resolve paths dynamically from the incoming `configurable.space_id`.

For resilience, `httpx>=0.28.1` is already in `pyproject.toml` and installed. The `api_parser.py` uses the sync `requests` library and must be migrated to async `httpx`. No external circuit breaker library is needed -- a lightweight custom implementation is sufficient for the scope (5 failures open, 30s half-open).

**Primary recommendation:** Use LangGraph's native `configurable` dict to pass `space_id` from frontend to agents. Refactor agent backends from module-level globals to factory functions. Build a minimal `ResilientClient` wrapper class combining httpx connection pooling, retry, and circuit breaker in a single module.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Agent subdirectory isolation -- `workspace/{space_id}/testcase/`, `workspace/{space_id}/web/`, `workspace/{space_id}/api/`. Each Agent's workspace_dir resolves dynamically to `settings.workspace_dir / space_id / agent_name`
- **D-02:** LangGraph configurable passes space_id -- frontend sends X-Space-Id header, LangGraph's configurable field propagates to Agent, Agent extracts space_id from config and sets workspace path dynamically
- **D-03:** Default workspace "default" -- no X-Space-Id header defaults to "default" workspace. Existing workspace/ data migrates to workspace/default/
- **D-04:** FilesystemBackend root path dynamic -- no hardcoded workspace_dir; runtime computation: `workspace_dir = settings.workspace_dir / space_id`
- **D-05:** Dropdown menu for workspace switching -- in same row as Agent Tabs. Lists available workspaces. Current workspace ID stored in localStorage
- **D-06:** Switching workspace clears thread list (threadId reset) to prevent cross-workspace data leakage
- **D-07:** Unified ResilientClient wrapper -- httpx.AsyncClient connection pool, exponential backoff retry, circuit breaker. Wraps MCP client and api_parser external calls
- **D-08:** Replace `requests` with `httpx` in api_parser -- unified async HTTP client
- **D-09:** Circuit breaker params -- 5 consecutive failures open, 30s half-open recovery. All params via config.py Settings
- **D-10:** Retry strategy -- exponential backoff (initial 1s, max 30s, max 3 retries), only retry recoverable errors (connection timeout, 5xx)

### Claude's Discretion
- graph.json configurable field configuration
- Workspace data migration strategy (existing default data to workspace/default/)
- ResilientClient implementation style (decorator, context manager, or wrapper class)
- MCP client resilience integration approach (langchain_mcp_adapters manages connections; resilience may wrap at higher layer)

### Deferred Ideas (OUT OF SCOPE)
- User authentication (JWT) -- X-Space-Id for isolation only, no auth
- LightRAG integration code -- config.py has config but no integration code, not adding
- Workspace management API -- CRUD REST API for workspaces deferred to future version
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INFRA-07 | Implement X-Space-Id multi-workspace isolation (different knowledge base spaces, no user login auth) | LangGraph `configurable` mechanism (verified in SDK types + LangGraph config.py); frontend `defaultHeaders` on Client; dynamic backend factory pattern |
| INFRA-08 | Configure connection pool (httpx.AsyncClient), exponential backoff retry, circuit breaker pattern | httpx 0.28.1 already installed; ResilientClient wrapper class combining pool + retry + breaker; configurable params in Settings |
| RAGS-02 | Multi-workspace isolation (workspace_id filtering, directory-level isolation) | Per-space_id subdirectory structure; wiki-mcp config path remains shared but workspace artifacts isolated per space_id |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| httpx | 0.28.1 | Async HTTP client with connection pooling | Already in pyproject.toml, async-native, supports HTTP/2, connection pooling built in |
| langgraph.config.get_config | (installed) | Access RunnableConfig with configurable dict | LangGraph native mechanism for per-request config propagation |
| @langchain/langgraph-sdk | 1.9.1 | Frontend streaming client with configurable support | Already installed, submit() accepts config.configurable |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| asyncio | stdlib | Async event loop utilities | For circuit breaker state management |
| dataclasses | stdlib | CircuitBreaker state dataclass | Lightweight state tracking without pydantic overhead |
| functools | stdlib | Wraps for retry decorator | Standard library retry wrapper implementation |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom circuit breaker | aiobreaker | aiobreaker adds a dependency for trivial logic (state counter + timer). Custom is ~40 lines, no dep |
| Custom retry with backoff | tenacity | tenacity is powerful but heavy for 3-retry exponential backoff. Custom is ~20 lines |
| X-Space-Id via HTTP header | configurable dict only | Header approach (D-02) is cleaner: frontend sends header, server converts to configurable. But since we use submit() directly, pass via config.configurable.space_id |
| Module-level backend (current) | Factory function | Factory is required for dynamic workspace. Module-level pattern cannot change per-request |

**Installation:**
```bash
# No new packages needed -- httpx already installed
# Verify:
pip show httpx  # 0.28.1
```

## Architecture Patterns

### Recommended Project Structure (new/changed files only)
```
src/app/
├── core/
│   ├── config.py                    # ADD: resilience settings (retry, breaker params)
│   └── workspace.py                 # NEW: get_workspace_dir(space_id, agent_name) helper
├── resilient/
│   ├── __init__.py                  # NEW: ResilientClient wrapper class
│   └── circuit_breaker.py           # NEW: CircuitBreaker dataclass + logic
├── agents/
│   ├── testcase/
│   │   └── agent.py                 # MODIFY: module-level -> factory function
│   ├── web/
│   │   ├── agent.py                 # MODIFY: module-level -> factory function
│   │   └── tools.py                 # MODIFY: dynamic workspace_dir
│   └── api/
│       ├── agent.py                 # MODIFY: module-level -> factory function
│       ├── tools/__init__.py        # MODIFY: dynamic workspace_dir
│       └── tools/api_parser.py      # MODIFY: requests -> httpx
webui/src/
├── app/
│   ├── components/
│   │   ├── AgentTabs.tsx            # MODIFY: add workspace dropdown
│   │   └── WorkspaceSelect.tsx      # NEW: workspace selector component
│   ├── hooks/
│   │   └── useChat.ts               # MODIFY: pass space_id in config.configurable
│   └── page.tsx                     # MODIFY: workspace state management
├── lib/
│   └── config.ts                    # MODIFY: add workspaceId to config
└── providers/
    └── ClientProvider.tsx           # MODIFY: pass defaultHeaders with X-Space-Id
```

### Pattern 1: LangGraph Configurable Space ID Propagation

**What:** Pass `space_id` from frontend through LangGraph API to agent backend resolution.
**When to use:** Every agent request that needs workspace isolation.

**Verified mechanism (SDK v1.9.1 + LangGraph config.py):**

```typescript
// Frontend: useChat.ts -> stream.submit()
stream.submit(
  { messages: [newMessage] },
  {
    config: {
      recursion_limit: 1000,
      configurable: { space_id: currentSpaceId }  // <-- ADD THIS
    },
  },
);
```

```python
# Backend: agent.py or workspace.py
from langgraph.config import get_config

def get_space_id() -> str:
    """Extract space_id from LangGraph configurable, default to 'default'."""
    try:
        config = get_config()
        return config.get("configurable", {}).get("space_id", "default")
    except RuntimeError:
        # Outside runnable context (tests, imports)
        return "default"
```

**Source:** Verified from `@langchain/langgraph-sdk/dist/ui/types.d.ts` SubmitOptions interface (line 905: `config?: ConfigWithConfigurable<ContextType>`) and `langgraph/config.py` (line 17: `get_config() -> RunnableConfig`).

### Pattern 2: Dynamic Backend Factory (replacing module-level instantiation)

**What:** Replace module-level `workspace_dir = settings.workspace_dir / "agent"` with factory function that resolves per-request.
**When to use:** All three agents (testcase, web, api).

**Current pattern (breaks with dynamic workspace):**
```python
# tools.py or agent.py -- module level
workspace_dir = settings.workspace_dir / "web"  # hardcoded at import time
file_backend = FilesystemBackend(root_dir=workspace_dir, virtual_mode=True)
```

**New pattern (factory function):**
```python
# tools.py -- factory function
from src.app.core.workspace import get_workspace_dir

def create_backends(space_id: str = "default"):
    """Create backends for the given workspace space_id."""
    workspace_dir = get_workspace_dir(space_id, "web")
    shell_backend = LocalShellBackend(
        root_dir=workspace_dir, virtual_mode=False,
        inherit_env=True, timeout=180,
    )
    file_backend = FilesystemBackend(
        root_dir=workspace_dir, virtual_mode=True,
    )
    composite_backend = CompositeBackend(
        default=shell_backend, routes={"/": file_backend},
    )
    return composite_backend, file_backend
```

**Key consideration:** DeepAgents `create_agent()` returns a compiled graph. The backend is passed at graph creation time. For dynamic workspace resolution, the agent's tools (not the graph-level backend) need workspace-aware paths. The graph-level `backend` parameter may remain static if tools handle their own path resolution via `get_space_id()` at call time.

### Pattern 3: ResilientClient Wrapper Class

**What:** Wrapper around `httpx.AsyncClient` with connection pooling, retry, and circuit breaker.
**When to use:** All external HTTP calls (api_parser, MCP client calls).

```python
# src/app/resilient/__init__.py
class ResilientClient:
    """Resilient HTTP client with retry and circuit breaker."""

    def __init__(self, breaker: CircuitBreaker | None = None):
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
        self._breaker = breaker or CircuitBreaker(
            fail_max=settings.circuit_breaker_fail_max,      # 5
            reset_timeout=settings.circuit_breaker_reset_timeout,  # 30
        )

    async def get(self, url: str, **kwargs) -> httpx.Response:
        return await self._request_with_retry("GET", url, **kwargs)

    async def _request_with_retry(self, method: str, url: str, **kwargs):
        # Circuit breaker check
        self._breaker.check_state()
        # Exponential backoff retry
        for attempt in range(settings.retry_max_attempts):  # 3
            try:
                response = await self._client.request(method, url, **kwargs)
                response.raise_for_status()
                self._breaker.record_success()
                return response
            except (httpx.ConnectTimeout, httpx.ReadTimeout,
                    httpx.RemoteProtocolError) as e:
                self._breaker.record_failure()
                if attempt == settings.retry_max_attempts - 1:
                    raise
                delay = min(
                    settings.retry_initial_delay * (2 ** attempt),
                    settings.retry_max_delay,
                )
                await asyncio.sleep(delay)
            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500:
                    self._breaker.record_failure()
                    # retry on 5xx
                    ...
                raise  # non-5xx: don't retry, but check breaker
```

### Pattern 4: Frontend Workspace State

**What:** Workspace selector component + localStorage persistence.
**When to use:** In AgentTabs row.

```typescript
// WorkspaceSelect.tsx
// Uses shadcn/ui Select component
// Reads/writes workspaceId to localStorage
// On change: resets threadId, propagates to useChat via config

// config.ts -- add workspaceId
export interface StandaloneConfig {
  deploymentUrl: string;
  assistantId: string;
  langsmithApiKey?: string;
  enablePdfMultimodal?: boolean;
  workspaceId?: string;  // NEW: default "default"
}
```

### Anti-Patterns to Avoid
- **Module-level workspace paths:** Current pattern uses `workspace_dir = settings.workspace_dir / "web"` at import time. This cannot change per-request. MUST use factory or lazy pattern.
- **Synchronous `requests` in async context:** `api_parser.py` uses `requests.get()` which blocks the event loop. MUST migrate to `httpx`.
- **Circuit breaker per global instance:** Don't use one breaker for all services. Use per-service-name breakers so one failing MCP server doesn't block others.
- **Breaking existing default workspace:** The "default" workspace must work identically to current single-workspace behavior. No behavior change for users who don't set X-Space-Id.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP connection pooling | Custom pool manager | `httpx.AsyncClient` with `limits` param | httpx handles keep-alive, connection reuse, HTTP/2 multiplexing |
| Per-request config in LangGraph | Custom middleware or header parsing | `config.configurable` dict + `get_config()` | Native LangGraph mechanism, no server-side changes needed |
| Frontend HTTP headers | Manual fetch wrapper | `ClientConfig.defaultHeaders` | SDK Client supports defaultHeaders natively |
| Workspace dropdown component | Custom select | shadcn/ui `Select` component | Already in project, consistent UI |

**Key insight:** The LangGraph ecosystem already has the plumbing for per-request configuration. The `configurable` dict flows from `stream.submit({ config: { configurable: { space_id } } })` through the API server to `get_config()["configurable"]` in Python agent code. No server middleware or custom header extraction needed on the backend.

## Common Pitfalls

### Pitfall 1: Module-level Backend Instantiation
**What goes wrong:** `workspace_dir = settings.workspace_dir / "web"` is computed at Python import time. If space_id is only known at request time, the backend points to the wrong directory.
**Why it happens:** All three agents (testcase, web, api) follow the Phase 5/6 pattern of module-level globals.
**How to avoid:** Refactor to factory functions. The `create_agent()` call can still happen at module level, but tools and backends that depend on workspace_dir must resolve it lazily using `get_space_id()` inside each tool call.
**Warning signs:** Agent writes files to `workspace/web/` instead of `workspace/{space_id}/web/`.

### Pitfall 2: DeepAgents Backend is Compile-Time
**What goes wrong:** `create_deep_agent(backend=composite_backend)` binds the backend at graph compilation time. Changing the backend per-request is not straightforward.
**Why it happens:** LangGraph compiles the graph once and reuses it across requests.
**How to avoid:** Two options: (a) Use tools with workspace-aware paths (tools call `get_space_id()` internally), keeping the graph-level backend as a "shell" that doesn't need workspace isolation; or (b) Use a proxy backend that delegates to the correct workspace-specific backend at runtime. Option (a) is simpler and recommended.
**Warning signs:** Files written to wrong workspace directory.

### Pitfall 3: Async Event Loop in api_parser
**What goes wrong:** Replacing `requests.get()` with `httpx.get()` (sync) is easy but wrong. In an async LangGraph server, sync calls block the event loop.
**Why it happens:** `requests` is sync-only, but `httpx` has both sync and async APIs.
**How to avoid:** Use `httpx.AsyncClient` with `await client.get()`. The tool function `parse_openapi_spec` must become async or call async code via a helper.
**Warning signs:** Server becomes unresponsive when parsing large OpenAPI specs.

### Pitfall 4: Workspace Data Migration Breaks Existing Sessions
**What goes wrong:** Moving `workspace/web/` to `workspace/default/web/` without updating paths causes all existing sessions to lose their data.
**Why it happens:** Existing checkpointer state (in-memory in this project) may reference old paths.
**How to avoid:** Since the project uses `DATABASE_URI: :memory:`, checkpoint data is ephemeral. Migration is a filesystem operation only. Create `workspace/default/` and move `workspace/web/` and `workspace/api/` into it. Update .gitignore if needed.
**Warning signs:** Agent cannot find skills or previous artifacts after migration.

### Pitfall 5: Circuit Breaker State Shared Across Services
**What goes wrong:** One failing service (e.g., gitnexus MCP) trips the breaker and blocks requests to healthy services (e.g., wiki-mcp).
**Why it happens:** Using a single global breaker instance.
**How to avoid:** Create per-service breakers: `breakers = {"wiki-mcp": CircuitBreaker(...), "graphify": CircuitBreaker(...), ...}`.
**Warning signs:** Healthy MCP services return "circuit open" errors.

## Code Examples

### Example 1: Workspace Helper (src/app/core/workspace.py)
```python
"""Workspace directory resolution for multi-space isolation."""
from pathlib import Path
from langgraph.config import get_config
from src.app.core.config import settings


def get_space_id() -> str:
    """Extract space_id from LangGraph configurable, default to 'default'.

    Safe to call outside runnable context (returns 'default').
    """
    try:
        config = get_config()
        return config.get("configurable", {}).get("space_id", "default")
    except RuntimeError:
        return "default"


def get_workspace_dir(space_id: str | None = None, agent_name: str = "") -> Path:
    """Resolve workspace directory for a given space_id and agent.

    Args:
        space_id: Workspace ID. If None, reads from current LangGraph config.
        agent_name: Agent subdirectory name (e.g., "web", "api", "testcase").

    Returns:
        Path like workspace/{space_id}/{agent_name}/
    """
    if space_id is None:
        space_id = get_space_id()
    base = settings.workspace_dir / space_id
    if agent_name:
        base = base / agent_name
    return base
```

### Example 2: Frontend useChat with space_id (webui/src/app/hooks/useChat.ts)
```typescript
// Add space_id parameter to sendMessage's config
stream.submit(
  { messages: [newMessage] },
  {
    optimisticValues: (prev) => ({
      messages: [...(prev.messages ?? []), newMessage],
    }),
    config: {
      recursion_limit: 1000,
      configurable: { space_id: currentSpaceId || "default" },
    },
  },
);
```

### Example 3: api_parser async with httpx (src/app/agents/api/tools/api_parser.py)
```python
import httpx

async def _load_spec(spec_url_or_path: str) -> dict[str, Any]:
    """Load an OpenAPI spec from URL or file path using async httpx."""
    if spec_url_or_path.startswith(("http://", "https://")):
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(spec_url_or_path)
            resp.raise_for_status()
            content = resp.text
    else:
        with open(spec_url_or_path, encoding="utf-8") as f:
            content = f.read()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return yaml.safe_load(content)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `requests` sync HTTP | `httpx` async HTTP | httpx mature since 2021 | Async-native, connection pooling, HTTP/2 support |
| Module-level agent instantiation | Factory/lazy patterns | LangGraph 0.2+ | Per-request dynamic configuration |
| `langgraph.json` `configurable_headers` | `submit()` `config.configurable` | SDK v0.0.31+ | Client-side configurable dict, no server config needed |
| Custom circuit breaker libs | Lightweight stdlib implementations | 2024+ | ~40 lines vs. adding pybreaker/aiobreaker dependency |

**Deprecated/outdated:**
- `pybreaker`: Sync-only, not maintained for async patterns
- `aiobreaker`: Adds dependency for trivial logic

## Open Questions

1. **graph.json configurable_headers support**
   - What we know: The `langgraph_cli/schemas.py` defines `ConfigurableHeaderConfig` for `langgraph.json`. But this project uses `graph.json` + `start_server.py` (not `langgraph.json`).
   - What's unclear: Whether the inmem server (`langgraph_api.server:app`) respects `configurable_headers` from `graph.json` or only from `langgraph.json`.
   - Recommendation: Don't rely on `configurable_headers`. Pass `space_id` via the frontend `submit()` `config.configurable` dict directly. This works regardless of server configuration.

2. **DeepAgents backend binding at compile time**
   - What we know: `create_deep_agent(backend=composite_backend)` creates a compiled graph with a fixed backend reference.
   - What's unclear: Whether tools that access the filesystem via backend use the backend's `root_dir` or can override paths dynamically.
   - Recommendation: Keep the graph-level backend for execute (shell) operations. Tools that need workspace-specific file paths should resolve them via `get_workspace_dir()` at call time, not rely on the backend's root_dir.

3. **MCP client resilience integration**
   - What we know: `langchain_mcp_adapters.MultiServerMCPClient` manages its own connections (stdio transport).
   - What's unclear: Whether we can wrap MCP client calls with circuit breaker without modifying the library.
   - Recommendation: Since MCP calls happen via `asyncio.new_event_loop().run_until_complete(client.get_tools(...))` at module load time, resilience wrapping should focus on the tool execution phase, not the connection phase. The circuit breaker should wrap the actual tool invocations within agent nodes, not the MCP client itself.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| httpx | ResilientClient, api_parser | Available | 0.28.1 | -- |
| Python 3.13 | Runtime | Available | 3.13.2 | -- |
| Node.js | Frontend | Available | (in webui/) | -- |
| @langchain/langgraph-sdk | Frontend streaming | Available | 1.9.1 | -- |
| langgraph | Backend agent runtime | Available | 1.1.10+ | -- |
| deepagents | Agent framework | Available | 0.5.5+ | -- |
| requests | api_parser (being replaced) | Available | 2.32.5 | Removing, not adding |
| aiobreaker | Circuit breaker | Not installed | -- | Custom implementation |
| tenacity | Retry logic | Not installed | -- | Custom implementation |

**Missing dependencies with no fallback:**
- None -- all required tools are available.

**Missing dependencies with fallback:**
- aiobreaker/tenacity: Not installed, but custom implementation is the recommended approach anyway (~60 lines total vs. adding dependencies).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | None (conftest.py in tests/) |
| Quick run command | `python -m pytest tests/ -x -q` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFRA-07 | get_space_id() returns "default" when no configurable | unit | `python -m pytest tests/test_workspace.py::test_default_space_id -x` | Wave 0 |
| INFRA-07 | get_space_id() returns configured space_id | unit | `python -m pytest tests/test_workspace.py::test_configured_space_id -x` | Wave 0 |
| INFRA-07 | get_workspace_dir() resolves correct path | unit | `python -m pytest tests/test_workspace.py::test_workspace_dir_path -x` | Wave 0 |
| INFRA-07 | Workspace migration creates default directory | unit | `python -m pytest tests/test_workspace.py::test_migration -x` | Wave 0 |
| INFRA-08 | ResilientClient retries on timeout | unit | `python -m pytest tests/test_resilient.py::test_retry_on_timeout -x` | Wave 0 |
| INFRA-08 | Circuit breaker opens after 5 failures | unit | `python -m pytest tests/test_resilient.py::test_circuit_breaker_opens -x` | Wave 0 |
| INFRA-08 | Circuit breaker half-open recovery | unit | `python -m pytest tests/test_resilient.py::test_circuit_breaker_half_open -x` | Wave 0 |
| INFRA-08 | api_parser uses httpx (not requests) | unit | `python -m pytest tests/test_api_tools.py -x` | Exists (verify) |
| RAGS-02 | Per-space_id workspace subdirectories isolated | unit | `python -m pytest tests/test_workspace.py::test_space_isolation -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/ -x -q`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_workspace.py` -- covers INFRA-07, RAGS-02 (workspace resolution, isolation)
- [ ] `tests/test_resilient.py` -- covers INFRA-08 (ResilientClient, CircuitBreaker, retry)
- [ ] No framework install needed -- pytest already configured

## Sources

### Primary (HIGH confidence)
- `@langchain/langgraph-sdk` v1.9.1 type definitions -- SubmitOptions.config.configurable verified in `dist/ui/types.d.ts` lines 902-906
- `langgraph/config.py` -- `get_config() -> RunnableConfig` verified, returns configurable dict
- `langgraph_cli/schemas.py` -- `ConfigurableHeaderConfig` and `HttpConfig` verified (lines 415-508)
- `@langchain/langgraph-sdk` ClientConfig.defaultHeaders -- verified in `dist/client/base.d.ts` line 30
- Project source files: all agent.py, tools.py, config.py, api_parser.py, mcp_client.py read directly

### Secondary (MEDIUM confidence)
- httpx AsyncClient patterns -- verified from httpx 0.28.1 installed package
- LangGraph configurable mechanism -- verified from LangGraph source code in .venv

### Tertiary (LOW confidence)
- aiobreaker/circuit breaker best practices -- based on training knowledge, not verified with current docs (web search rate limited)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already installed and verified in project
- Architecture: HIGH -- LangGraph configurable mechanism verified in source code (SDK types + Python config.py)
- Pitfalls: HIGH -- all pitfalls identified from reading actual codebase patterns
- ResilientClient: MEDIUM -- pattern is standard but not yet implemented; httpx API usage verified

**Research date:** 2026-05-14
**Valid until:** 2026-06-14 (stable: LangGraph + httpx are mature technologies)
