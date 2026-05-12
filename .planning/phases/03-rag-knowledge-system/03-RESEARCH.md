# Phase 3: RAG Knowledge System (wiki-mcp) - Research

**Researched:** 2026-05-12
**Domain:** MCP stdio server integration, wiki-mcp knowledge query, DeepAgents tool registration
**Confidence:** HIGH

## Summary

Phase 3 replaces the originally planned LightRAG + RAG system with wiki-mcp, a stdio MCP server that provides 6 knowledge query tools for the TestCase Agent. The integration involves three concrete code changes: (1) adding wiki-mcp as a stdio entry in the existing `MultiServerMCPClient` configuration in `mcp_client.py`, (2) creating a `wiki-query` SKILL.md that teaches the Agent when and how to use wiki knowledge, and (3) updating `config.py` with wiki-mcp path settings. The Agent's `agent.py` must then fetch and register wiki-mcp tools at creation time.

The wiki-mcp server is a TypeScript application at `D:\llm-wiki\wiki-mcp\` that reads Markdown files from disk-based wiki projects, builds a full-text search index (MiniSearch) and knowledge graph (graphology), and exposes tools via the MCP protocol over stdio transport. It is started via `npx tsx src/index.ts --config=<path>` and communicates through JSON-RPC on stdin/stdout.

**Primary recommendation:** Register wiki-mcp as a stdio MCP server using the exact same `MultiServerMCPClient` pattern already in `mcp_client.py`. Fetch tools via `await client.get_tools(server_name="wiki-mcp")` at agent creation time and merge them into the agent's tools list. No middleware changes needed -- the existing 2-layer onion (SkillsMiddleware + PDFContextMiddleware) stays intact per D-16.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Completely replace LightRAG with llm-wiki + wiki-mcp. No LightRAG Server, Ollama embeddings, or vector database. Knowledge base is Markdown files managed by llm-wiki project.
- **D-02:** wiki-mcp only handles querying (search, get_page, list_pages, list_wikis, graph_query, reload), not content creation/editing/maintenance.
- **D-03:** Knowledge base content is pre-built Markdown files, no document upload feature needed.
- **D-04:** wiki-mcp registered via stdio MCP protocol using MultiServerMCPClient (reuse Phase 1 MCP infrastructure pattern).
- **D-05:** wiki-mcp's 6 tools exposed to Agent automatically via MCP protocol, no manual @tool wrapping needed.
- **D-06:** Create independent wiki-query SKILL.md at `src/app/skills/wiki-query/`, guiding Agent on when/how to query wiki.
- **D-07:** wiki-query Skill does NOT change the existing 5-stage workflow structure. Agent decides autonomously whether to query wiki during requirement-analysis and test-strategy stages.
- **D-08:** wiki-mcp path and knowledge base directory configured via environment variables (.env + config.py Settings class extension).
- **D-09:** wiki-mcp-config.json config file specifies wiki project names and paths.
- **D-10:** MIDW-05 (RAGMiddleware) NOT needed. wiki-mcp tools auto-available via MCP protocol.
- **D-11:** RAGS-01 (LightRAG 7 MCP tools) replaced by wiki-mcp 6 tools.
- **D-12:** RAGS-03 (RAG-first forced strategy) NOT needed. Agent queries on demand.
- **D-13:** RAGS-04 (6 query modes) replaced by wiki-mcp's own query capabilities (search + graph_query + get_page etc.), Agent auto-selects.
- **D-14:** RAGS-05 (document status monitoring) NOT needed. wiki-mcp reads pre-built files.
- **D-15:** UI-06 (RAG toggle) NOT needed. Wiki tools always available.
- **D-16:** No 3-layer onion middleware. Keep Phase 2's 2-layer (SkillsMiddleware + PDFContextMiddleware) unchanged.

### Claude's Discretion
- wiki-query SKILL.md specific prompt content and query guidance
- wiki-mcp registration code details in agent.py
- config.py new field naming

### Deferred Ideas (OUT OF SCOPE)
- Frontend Wiki knowledge base status display -- future phase
- Multi-knowledge-base dynamic switching -- only config file wikis supported
- Wiki content creation/maintenance integration -- done in llm-wiki project separately
- LightRAG complete removal -- Phase 7 infrastructure hardening
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MIDW-05 | RAGMiddleware dynamic tool injection/removal | SUPERCeded by D-10/D-16. wiki-mcp tools loaded at agent creation time via MCP client, no middleware needed |
| SKILL-08 | RAG knowledge query skill | Replaced by D-06: wiki-query SKILL.md. Uses wiki-mcp's 6 tools (search, get_page, list_pages, list_wikis, graph_query, reload) |
| RAGS-01 | RAG MCP Server (7 tools) | Replaced by D-11: wiki-mcp provides 6 tools via stdio MCP |
| RAGS-03 | RAG-first forced strategy | Superseded by D-12: Agent queries wiki on demand, no forced strategy |
| RAGS-04 | 6 query modes | Superseded by D-13: wiki-mcp has its own query capabilities |
| RAGS-05 | Document status monitoring | Superseded by D-14: wiki-mcp reads pre-built files |
| UI-06 | RAG toggle button | Superseded by D-15: Wiki tools always available |
</phase_requirements>

## Standard Stack

### Core (already installed, no new dependencies)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| langchain-mcp-adapters | 0.2.2 | MCP client for tool loading | Already in pyproject.toml. Provides MultiServerMCPClient with stdio support. |
| deepagents | >=0.5.5 | Agent framework | Provides create_deep_agent, SkillsMiddleware, FilesystemBackend. Already installed. |
| langchain | >=1.2.0 | Tool abstraction | BaseTool type system. MCP tools become LangChain tools automatically. |
| pydantic-settings | >=2.14.1 | Configuration management | Settings class in config.py. Already installed. |

### External (must be installed and built)
| Tool | Version | Purpose | When to Use |
|------|---------|---------|-------------|
| wiki-mcp | 0.1.0 | Knowledge query MCP server | Started as stdio subprocess. Located at D:\llm-wiki\wiki-mcp\. Needs `npm install` and `npx tsx` to run. |
| Node.js | 22.14.0 | wiki-mcp runtime | Required to run wiki-mcp as stdio process. Verified available. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| wiki-mcp stdio | SSE-based wiki server | stdio is simpler (no port management), matches D-04 decision |
| Manual @tool wrapping | MCP auto-discovery | MCP auto-discovery is standard per D-05, avoids duplicate code |

**Installation:**
```bash
# No new Python packages needed -- all dependencies already in pyproject.toml
# wiki-mcp must have npm dependencies installed:
cd D:\llm-wiki\wiki-mcp && npm install
```

**Version verification:**
```
langchain-mcp-adapters: 0.2.2 (installed, verified in site-packages)
deepagents: >=0.5.5 (in pyproject.toml)
node: v22.14.0 (verified on system)
npx: 10.9.2 (verified on system)
tsx: v4.21.0 (available via npx, also in wiki-mcp/node_modules)
```

## Architecture Patterns

### Recommended Integration Architecture
```
src/app/
  core/config.py          # Add WIKI_MCP_COMMAND, WIKI_MCP_CONFIG_PATH to Settings
  mcp/mcp_client.py       # Add "wiki-mcp" stdio entry to MultiServerMCPClient config
  agents/testcase/agent.py # Fetch wiki-mcp tools at module level, merge into agent tools
  skills/wiki-query/       # New directory
    SKILL.md               # Wiki query guidance skill
```

### Pattern 1: MultiServerMCPClient stdio configuration
**What:** Add wiki-mcp as a stdio transport server to the existing MCP client
**When to use:** This is the ONLY way to connect to wiki-mcp per D-04
**Example:**
```python
# Source: langchain_mcp_adapters.sessions.StdioConnection (verified in venv)
# The exact TypedDict structure for stdio connections:

{
    "wiki-mcp": {
        "transport": "stdio",
        "command": "npx",                    # or "node" if dist/ is built
        "args": [
            "tsx",
            "D:\\llm-wiki\\wiki-mcp\\src\\index.ts",
            "--config=D:\\llm-wiki\\wiki-mcp\\wiki-mcp-config.json"
        ],
        "cwd": "D:\\llm-wiki\\wiki-mcp",     # optional but recommended
    }
}
```

Key findings from source code review of `langchain_mcp_adapters.sessions`:
- `command` (str, required): The executable to run
- `args` (list[str], required): Command line arguments
- `transport` must be literal `"stdio"`
- `cwd` (optional): Working directory for the subprocess
- `env` (optional): Environment variables dict

### Pattern 2: Async tool fetching at agent creation
**What:** Fetch MCP tools asynchronously and merge into agent's tool list
**When to use:** At module load time in agent.py
**Example:**
```python
# Source: Classroom reference (2026-05-07-ai-test-agent-system)
# Pattern: fetch MCP tools via client, merge with existing tools

from app.mcp.mcp_client import get_mcp_client

async def get_wiki_tools():
    """Fetch wiki-mcp tools via MCP client."""
    client = await get_mcp_client()
    tools = await client.get_tools(server_name="wiki-mcp")
    return tools

# In agent creation:
# tools=[export_test_cases_to_excel] + wiki_tools
```

CRITICAL: The existing `mcp_client.py` returns a `MultiServerMCPClient` from `get_mcp_client()`. The classroom reference shows two patterns:
1. `asyncio.run(client.get_tools())` -- used at module level (tools.py line 241)
2. `await client.get_tools()` -- used in async context

For agent.py module-level setup, the classroom reference uses `asyncio.run()` to fetch tools synchronously. However, this can cause issues if an event loop is already running. The safer approach is to either:
- Fetch tools lazily on first agent invocation, OR
- Use `asyncio.run()` only at module level if no loop is running

### Pattern 3: SKILL.md format
**What:** YAML frontmatter + Markdown body for skill definition
**When to use:** Creating the wiki-query skill
**Example:**
```markdown
---
name: wiki-query
description: [Chinese description of when to activate wiki knowledge queries]
---

# Wiki Knowledge Query Skill

## Activation Scenarios
[When the agent should query the wiki]

## Tool Usage Guide
[How to use each of the 6 wiki-mcp tools]

## Integration with Workflow
[How wiki results feed into requirement-analysis and test-strategy stages]
```

Key format rules (from existing skills):
- `name` in frontmatter MUST match directory name exactly
- `description` is a single line in Chinese (following project convention)
- Body follows standard Markdown with activation scenarios, execution steps, output spec

### Anti-Patterns to Avoid
- **DO NOT create a new middleware layer for wiki tools.** D-16 explicitly keeps 2-layer onion. Tools are registered directly in the agent's tools list, not via middleware injection.
- **DO NOT use `asyncio.run()` inside an already-running event loop.** This will crash with "cannot run the event loop while another loop is running". Use lazy initialization or module-level caching carefully.
- **DO NOT wrap wiki-mcp tools in `@tool` decorators.** MCP tools come pre-wrapped as LangChain BaseTool objects from `client.get_tools()`.
- **DO NOT hardcode wiki-mcp paths in agent.py.** All paths must come from config.py Settings (D-08).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| MCP tool discovery | Manual @tool wrappers for each wiki-mcp tool | `client.get_tools()` from langchain-mcp-adapters | MCP SDK auto-discovers tools, converts to LangChain BaseTool |
| stdio transport management | Custom subprocess management for wiki-mcp | `StdioConnection` in MultiServerMCPClient | Handles subprocess lifecycle, JSON-RPC framing, error recovery |
| Full-text search | Custom search indexing for wiki content | wiki-mcp's MiniSearch-based search tool | Supports CJK, ranking, token budgets, graph expansion |
| Knowledge graph queries | Custom graph traversal code | wiki-mcp's graph_query tool (neighbors/stats/trace_source) | Built on graphology with correlation scoring |
| Config file parsing | Custom JSON config reading for wiki-mcp-config.json | wiki-mcp's own loadConfig() with validation | It validates required fields, searches multiple paths |

**Key insight:** wiki-mcp is a complete, self-contained MCP server. The Python side only needs to configure the stdio transport and fetch tools. Zero knowledge of wiki-mcp's internals is needed in the Python codebase.

## Common Pitfalls

### Pitfall 1: wiki-mcp dist/ not built
**What goes wrong:** The `package.json` has `"main": "dist/index.js"` but `dist/` does not exist on disk. Running `node dist/index.js` will fail.
**Why it happens:** wiki-mcp uses `tsx` for development (`npm run dev` = `tsx src/index.ts`). The TypeScript source is compiled on-the-fly by tsx, so dist/ was never generated.
**How to avoid:** Use `npx tsx src/index.ts` as the command, not `node dist/index.js`. This matches the `npm run dev` script in wiki-mcp's package.json.
**Warning signs:** FileNotFoundError or module resolution errors when MCP client tries to start wiki-mcp subprocess.

### Pitfall 2: console.log corrupting stdio MCP stream
**What goes wrong:** wiki-mcp's index.ts redirects console.log to stderr at the very top of the file (line 4). If this redirect is bypassed or the subprocess inherits stdout, JSON-RPC messages get corrupted.
**Why it happens:** MCP stdio protocol uses stdout exclusively for JSON-RPC. Any stray write to stdout breaks the message framing.
**How to avoid:** Never modify wiki-mcp's console.log redirect. When debugging, read stderr output, never stdout.
**Warning signs:** MCP client reports JSON parse errors, tools not loading, or empty tool lists.

### Pitfall 3: asyncio.run() inside running event loop
**What goes wrong:** Calling `asyncio.run(client.get_tools())` at module level crashes when imported inside a running LangGraph server (which already has an event loop).
**Why it happens:** `asyncio.run()` creates a new event loop and fails if one already exists.
**How to avoid:** Either (a) use lazy initialization pattern (fetch tools on first call), or (b) use `asyncio.get_event_loop().run_until_complete()` with a try/except for already-running loops, or (c) configure tools at agent invocation time rather than module import time.
**Warning signs:** RuntimeError: "This event loop is already running" or "cannot run the event loop while another loop is running".

### Pitfall 4: wiki-mcp-config.json missing or malformed
**What goes wrong:** wiki-mcp exits with fatal error if config file is not found or has invalid JSON.
**Why it happens:** wiki-mcp searches for config in three locations: --config path, $HOME/.wiki-mcp/, and CWD. If none found, it throws.
**How to avoid:** Create wiki-mcp-config.json with the required format before testing. Ensure the --config argument path uses forward slashes or properly escaped backslashes.
**Warning signs:** wiki-mcp subprocess exits immediately, MCP client reports connection failure.

### Pitfall 5: SKILL.md name mismatch
**What goes wrong:** SkillsMiddleware fails to load the skill, or loads it with wrong name.
**Why it happens:** The YAML frontmatter `name` field must exactly match the directory name.
**How to avoid:** For `src/app/skills/wiki-query/SKILL.md`, the frontmatter must have `name: wiki-query`.
**Warning signs:** Agent doesn't reference wiki knowledge in its responses, skill not appearing in system prompt.

### Pitfall 6: Wiki project directory not populated
**What goes wrong:** wiki-mcp starts but reports 0 wiki projects, all tools return empty results.
**Why it happens:** The wiki-mcp-config.json points to wiki project paths that don't exist or have no Markdown files.
**How to avoid:** Verify wiki-mcp-config.json paths exist and contain .md files before running integration tests.
**Warning signs:** `list_wikis` returns empty, `search` returns no results.

## Code Examples

### Example 1: wiki-mcp stdio connection config
```python
# Source: langchain_mcp_adapters.sessions.StdioConnection + mcp_client.py
# The exact dict structure for MultiServerMCPClient

{
    "wiki-mcp": {
        "transport": "stdio",
        "command": "npx",
        "args": [
            "tsx",
            "D:/llm-wiki/wiki-mcp/src/index.ts",
            "--config=D:/llm-wiki/wiki-mcp/wiki-mcp-config.json"
        ],
    }
}
```

### Example 2: wiki-mcp-config.json format
```json
// Source: wiki-mcp/src/config.ts + types.ts
// Required format for wiki-mcp configuration file
{
    "wikis": [
        {
            "name": "test-knowledge",
            "path": "D:/llm-wiki/test-knowledge"
        }
    ]
}
```

### Example 3: config.py Settings extension
```python
# Source: src/app/core/config.py (existing pattern)
class Settings(BaseSettings):
    # ... existing fields ...

    # wiki-mcp configuration (Phase 3)
    wiki_mcp_command: str = "npx"
    wiki_mcp_args: str = "tsx D:/llm-wiki/wiki-mcp/src/index.ts"
    wiki_mcp_config_path: str = "D:/llm-wiki/wiki-mcp/wiki-mcp-config.json"
```

### Example 4: Tool fetching and agent creation
```python
# Source: Classroom reference tools.py + agent.py patterns
# Option A: Lazy tool fetching (recommended to avoid asyncio.run issues)

from functools import lru_cache

_wiki_tools_cache = None

async def get_wiki_mcp_tools():
    """Fetch wiki-mcp tools, caching result."""
    global _wiki_tools_cache
    if _wiki_tools_cache is not None:
        return _wiki_tools_cache
    client = await get_mcp_client()
    tools = await client.get_tools(server_name="wiki-mcp")
    _wiki_tools_cache = tools
    return tools
```

### Example 5: wiki-mcp 6 tools and their parameters
```typescript
// Source: wiki-mcp/src/server.ts + tools/*.ts (verified from source)

// Tool 1: list_wikis - no parameters
// Returns: "wiki-name: 15 pages (3 entities, 5 concepts, 2 sources)"

// Tool 2: list_pages - parameters: wiki?, type?, tags?
// Returns: Markdown table with Title, Type, Tags, Path columns

// Tool 3: get_page - parameters: path (required), wiki?, related?
// Returns: Metadata JSON + full markdown content + optional related pages

// Tool 4: search - parameters: query (required), wiki?, type?, tags?, maxTokens?
// Returns: Purpose.md context + ranked results with scores, snippets, [graph] expansions
// NOTE: Supports English AND CJK (Chinese/Japanese/Korean) queries

// Tool 5: graph_query - parameters: mode (required: neighbors|stats|trace_source),
//   page?, source?, wiki?, maxTokens?, limit?
// Returns: Depends on mode (related pages table / graph statistics / citing pages table)

// Tool 6: reload - parameters: wiki?
// Returns: Success message. Used when wiki files change on disk.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| LightRAG + Ollama embeddings | wiki-mcp (disk-based Markdown) | Phase 3 redesign | No vector DB, no embedding model, no GPU needed. Simpler deployment. |
| RAGMiddleware (dynamic tool injection) | Direct MCP tool registration | D-10/D-16 decision | Agent always has wiki tools available, no enable/disable toggle needed |
| 3-layer onion middleware | 2-layer (Skills + PDF) | D-16 decision | Simpler middleware chain, wiki tools via tools= parameter not middleware |
| SSE transport (Docling) | stdio transport (wiki-mcp) | D-04 decision | Different transport config needed. wiki-mcp uses stdio, Docling uses SSE. Both supported by MultiServerMCPClient. |
| rag-query Skill (LightRAG) | wiki-query Skill (wiki-mcp) | D-06 decision | Different tool set (6 vs 7), different query patterns, different integration points |

**Deprecated/outdated:**
- LightRAG Server (port 9621): Not needed. wiki-mcp replaces this entirely.
- Ollama embedding model (qwen3-embedding:0.6b): Not needed. wiki-mcp uses file-based search (MiniSearch).
- RAGAnything: Not needed. wiki-mcp has its own search pipeline.
- NanoVectorDB, NetworkX: Not needed. wiki-mcp uses MiniSearch + graphology internally.

## Open Questions

1. **wiki-mcp startup time impact on agent creation**
   - What we know: wiki-mcp builds its search index on startup. Large wikis could take several seconds.
   - What's unclear: How long the initial index build takes for the actual knowledge base.
   - Recommendation: Test with the actual wiki project. If >5 seconds, consider lazy tool loading or pre-warming.

2. **wiki-mcp-config.json location**
   - What we know: wiki-mcp searches --config path, $HOME/.wiki-mcp/, and CWD. No config exists yet.
   - What's unclear: Where the config file should be placed for the smart-test-platform project.
   - Recommendation: Create it alongside wiki-mcp source at `D:\llm-wiki\wiki-mcp\wiki-mcp-config.json` and pass via --config argument. This keeps config with the tool, not the platform.

3. **Tool name prefixing**
   - What we know: MultiServerMCPClient has a `tool_name_prefix` option that prefixes tool names with server name (e.g., "wiki-mcp_search" instead of "search").
   - What's unclear: Whether the SKILL.md should reference prefixed or unprefixed tool names.
   - Recommendation: Use default `tool_name_prefix=False` (no prefix). The SKILL.md will reference tools by their natural names (search, get_page, etc.).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node.js | wiki-mcp runtime | Yes | 22.14.0 | -- |
| npx | wiki-mcp startup | Yes | 10.9.2 | -- |
| tsx (via npx) | wiki-mcp TypeScript execution | Yes | 4.21.0 | -- |
| Python | Agent framework | Yes | 3.13.2 | -- |
| pytest | Testing | Yes | 9.0.2 | -- |
| wiki-mcp source | Knowledge server | Yes | 0.1.0 | -- |
| wiki-mcp node_modules | wiki-mcp dependencies | Yes | installed | `npm install` in wiki-mcp dir |
| wiki-mcp-config.json | wiki-mcp config | No | -- | Must be created in Wave 0 |

**Missing dependencies with no fallback:**
- wiki-mcp-config.json must be created before testing. Without it, wiki-mcp refuses to start.

**Missing dependencies with fallback:**
- None. All required tools are available.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | None (uses defaults) |
| Quick run command | `pytest tests/test_wiki_integration.py -x -v` |
| Full suite command | `pytest tests/ -x -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| D-04/D-05 | wiki-mcp stdio tools load correctly | unit | `pytest tests/test_wiki_integration.py::test_wiki_tools_load -x` | No, Wave 0 |
| D-06 | wiki-query SKILL.md loads into agent system prompt | unit | `pytest tests/test_wiki_integration.py::test_wiki_skill_loaded -x` | No, Wave 0 |
| D-08 | config.py reads wiki-mcp settings from env | unit | `pytest tests/test_wiki_integration.py::test_config_settings -x` | No, Wave 0 |
| D-05 | Agent has 6 wiki-mcp tools registered | integration | `pytest tests/test_wiki_integration.py::test_agent_has_wiki_tools -x` | No, Wave 0 |
| D-06 | SKILL.md name matches directory name | unit | `pytest tests/test_wiki_integration.py::test_skill_name_match -x` | No, Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_wiki_integration.py -x -v`
- **Per wave merge:** `pytest tests/ -x -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_wiki_integration.py` -- covers D-04, D-05, D-06, D-08
- [ ] `D:/llm-wiki/wiki-mcp/wiki-mcp-config.json` -- minimal config file for testing
- [ ] Test wiki project directory with sample .md files (if no real wiki exists)

## Sources

### Primary (HIGH confidence)
- `D:\llm-wiki\wiki-mcp\src\server.ts` -- wiki-mcp MCP server registration, 6 tool definitions, resource registration
- `D:\llm-wiki\wiki-mcp\src\index.ts` -- stdio transport setup, console.log redirect to stderr
- `D:\llm-wiki\wiki-mcp\src\config.ts` -- Config loading, validation, search paths
- `D:\llm-wiki\wiki-mcp\src\types.ts` -- WikiConfig, WikiConfigEntry type definitions
- `D:\llm-wiki\wiki-mcp\src\tools\search.ts` -- search tool with multi-stage retrieval pipeline
- `D:\llm-wiki\wiki-mcp\src\tools\graph-query.ts` -- graph_query tool (neighbors/stats/trace_source)
- `D:\llm-wiki\wiki-mcp\src\tools\get-page.ts` -- get_page with 3-stage path resolution
- `D:\llm-wiki\wiki-mcp\src\tools\list-wikis.ts` -- list_wikis with page type statistics
- `D:\llm-wiki\wiki-mcp\src\tools\list-pages.ts` -- list_pages with type/tag filtering
- `D:\llm-wiki\wiki-mcp\src\tools\reload.ts` -- reload for index rebuilding
- `D:\llm-wiki\wiki-mcp\src\resources\wiki-resources.ts` -- 4 MCP resources (purpose/schema/overview/index)
- `D:\llm-wiki\wiki-mcp\package.json` -- Dependencies, scripts, bin config
- `src/app/mcp/mcp_client.py` -- Existing MultiServerMCPClient configuration
- `src/app/agents/testcase/agent.py` -- Current agent creation with middleware chain
- `src/app/core/config.py` -- Settings class with existing LightRAG/MCP fields
- `.venv/Lib/site-packages/langchain_mcp_adapters/client.py` -- MultiServerMCPClient API, get_tools() signature
- `.venv/Lib/site-packages/langchain_mcp_adapters/sessions.py` -- StdioConnection TypedDict, create_session flow

### Secondary (MEDIUM confidence)
- Classroom reference `2026-05-07-ai-test-agent-system/src/app/agents/testcase/tools.py` -- MCP tool fetching patterns (asyncio.run, caching)
- Classroom reference `2026-05-07-ai-test-agent-system/src/app/agents/testcase/agent.py` -- Agent creation with MCP tools, Context schema
- Classroom reference `2026-05-07-ai-test-agent-system/src/app/middleware/rag_context.py` -- RAGMiddleware pattern (NOT used, for contrast only)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries already installed and verified in project venv
- Architecture: HIGH - Source code reviewed for every integration point (mcp_client.py, agent.py, config.py, skills/)
- Pitfalls: HIGH - Derived from actual source code inspection (wiki-mcp index.ts, langchain_mcp_adapters sessions.py)
- Tool API surface: HIGH - All 6 tools read from source, all parameters and return formats documented

**Research date:** 2026-05-12
**Valid until:** 2026-06-12 (stable - all dependencies already installed)
