# Architecture Patterns

**Domain:** AI-Powered Intelligent Testing Platform (Agent + RAG + MCP + Skills)
**Researched:** 2026-05-11
**Confidence:** HIGH (based on direct analysis of 12 weeks of reference codebase)

## Recommended Architecture

The platform uses a **Three-Domain Agent Architecture** with a shared middleware pipeline, unified by the DeepAgents framework and exposed through a single LangGraph API server. Each domain (TestCase, Web, API) is an independent agent with its own Skills, tools, and middleware stack, but they share core infrastructure (LLM routing, RAG knowledge base, MCP services, workspace filesystem).

```
+------------------------------------------------------------------+
|                     Frontend (Next.js 16)                         |
|  Chat UI / File Upload / Thread Management / Theme / RAG Toggle   |
+------------------------------------------------------------------+
         | @langchain/langgraph-sdk (SSE streaming)
         v
+------------------------------------------------------------------+
|                  LangGraph API Server (port 2026)                 |
|  graph.json routes to agent: ./src/app/agents/{domain}/agent.py  |
+------------------------------------------------------------------+
         |
         +------------------+------------------+
         |                  |                  |
         v                  v                  v
+-----------------+ +----------------+ +-------------------+
| TestCase Agent  | |  Web Agent     | |  API Agent        |
| (6 Skills)      | |  (Dual Mode)   | |  (MASTEST)        |
| 5-phase flow    | |  Mode A: QA    | | 7-stage pipeline  |
|                 | |  Mode B: Comp  | |                   |
+-----------------+ +----------------+ +-------------------+
     |      |            |      |           |        |
     v      v            v      v           v        v
+--------+ +------+ +--------+ +------+ +--------+ +------+
|Skills  | |Tools | |Skills  | |Tools | |Skills  | |Tools |
|MW      | |      | |MW      | |      | |MW      | |      |
+--------+ +------+ +--------+ +------+ +--------+ +------+
     |                                |                |
     +----------+---------------------+                |
                |                                     |
                v                                     v
+---------------------------+    +---------------------------+
|  Onion Middleware Stack   |    |   MCP External Services   |
|  Skills -> Model Select   |    |                           |
|  -> PDF Context -> RAG    |    |  +-- RAG MCP Server (8008)|
+---------------------------+    |  +-- Playwright MCP (stdio)|
                                 |  +-- Graphify MCP (stdio)  |
                                 |  +-- Docling MCP (stdio)   |
                                 |  +-- Chart MCP (stdio)     |
                                 +---------------------------+
         |                                    |
         v                                    v
+---------------------------+    +---------------------------+
|  LLM Layer               |    |  Knowledge Layer          |
|  DeepSeek Chat (text)    |    |  LightRAG Server (9621)   |
|  Doubao Vision (multi)   |    |  +-- PostgreSQL 16        |
|  Dynamic model selection |    |  +-- Neo4j (graph)        |
+---------------------------+    |  +-- Milvus (vectors)     |
                                 |  +-- Redis (cache)        |
                                 +---------------------------+
```

### Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| **Frontend (Next.js)** | Chat interface, file upload, RAG toggle, thread management, theme switching | LangGraph API via @langchain/langgraph-sdk |
| **LangGraph API Server** | Agent orchestration, streaming, thread state persistence, tool interrupt handling | Frontend (SSE), Agents (graph execution) |
| **TestCase Agent** | Requirements analysis, test strategy, test case design, quality review, export | Skills MW, Tools, Middleware stack |
| **Web Agent** | Exploratory QA testing (Mode A), Component-aware test generation (Mode B) | Skills MW, Playwright CLI/Agent-Browser |
| **API Agent** | OpenAPI spec parsing, MASTEST methodology, Playwright script generation | Skills MW, MCP Playwright, Coverage tools |
| **SkillsMiddleware** | Loads SKILL.md files from workspace filesystem, injects skill knowledge into context | FilesystemBackend (workspace directory) |
| **PDFContextMiddleware** | Extracts PDF attachments from messages, saves to workspace, prompts agent to parse | File system (workspace/uploads/) |
| **RAGMiddleware** | Dynamically injects/removes RAG tools based on enable_rag context flag | MCP RAG Server (SSE on port 8008) |
| **DynamicModelSelection** | Detects images in messages, switches between text and vision models | LLM layer (DeepSeek / Doubao) |
| **RAG MCP Server** | 7-tool MCP service wrapping LightRAG API with multi-tenant isolation | LightRAG Server (port 9621) |
| **LightRAG Server** | Knowledge graph + vector search, 6 query modes, document indexing | PostgreSQL, Neo4j, Milvus, Redis, Ollama |
| **FilesystemBackend** | Virtual filesystem for workspace: skills, uploads, outputs, artifacts | Agent (via DeepAgents framework) |
| **CompositeBackend** | Routes filesystem ops to FilesystemBackend, shell ops to LocalShellBackend | FilesystemBackend + LocalShellBackend |

### Data Flow

**1. Test Case Generation Flow (most complex):**

```
User uploads PDF/URL/image
  -> Frontend sends via langgraph-sdk (messages + attachments in additional_kwargs)
    -> LangGraph API routes to TestCase Agent
      -> PDFContextMiddleware: saves PDF, injects parse prompt
      -> DynamicModelSelection: switches to Doubao Vision if images detected
      -> SkillsMiddleware: loads relevant SKILL.md from workspace
      -> RAGMiddleware: injects RAG tools if enable_rag=true
      -> Agent (ReAct loop):
           Phase 1: activate requirement-analysis skill -> parse doc -> output analysis
           Phase 2: activate test-strategy skill -> design strategy
           Phase 3: activate test-case-design + test-data-generator skills
           Phase 4: activate quality-review skill -> score >= 75 or loop back
           Phase 5: activate output-formatter skill -> Excel/Markdown/CSV
      -> Tools called: extract_pdf_text_from_file, export_test_cases_to_excel, rag_query_data
      -> Stream results back to frontend via SSE
```

**2. Web Automation Flow (dual mode):**

```
User provides URL or repo path
  -> detect_test_mode tool: determines MODE_A (URL) or MODE_B (repo)
  -> Mode A: Load pw-dogfood skill -> 6-phase exploratory QA
             -> Playwright CLI or Agent-Browser for browser control
             -> Save evidence (screenshots/traces/videos) to web-output/
  -> Mode B: Load component-aware-web-automation skill -> 7-Agent Pipeline
             -> Script Analyst -> Stage Manager -> Blocking Coach ->
                Set Designer -> Choreographer -> Assistant Director -> Continuity Lead
             -> Generate TypeScript test scripts + POM files
```

**3. API Testing Flow (MASTEST methodology):**

```
User provides OpenAPI/Swagger spec URL
  -> parse_openapi_spec tool: fetch + resolve $ref + extract operations
  -> test-scenario-design skill: generate unit + system scenarios
  -> Human-in-the-Loop: pause for user review of scenarios
  -> playwright-api-testing skill: generate .spec.ts files
  -> Human-in-the-Loop: pause for user review of scripts
  -> check_script_syntax tool: validate TypeScript
  -> Execute scripts via Playwright MCP tools or npx playwright test
  -> api-test-quality skill: LLM-based data type + status code coverage analysis
  -> compute_coverage tool: deterministic metrics
  -> Final quality report
```

**4. RAG Query Flow:**

```
Agent needs knowledge context
  -> RAGMiddleware detects enable_rag=true in runtime context
  -> Injects RAG tool descriptions into system prompt
  -> Agent calls rag_query_data / rag_graph_search / rag_graph_get
  -> MCP SSE client -> RAG MCP Server (port 8008)
  -> RAGServiceClient: JWT auth -> LightRAG API (port 9621)
  -> LightRAG: vector search (Milvus) + graph traversal (Neo4j)
  -> Returns structured results (entities, relations, chunks, references)
```

## Patterns to Follow

### Pattern 1: Three-Domain Agent Isolation
**What:** Each testing domain (TestCase, Web, API) is an independent agent with its own system prompt, tools, skills, and middleware configuration. No cross-agent state sharing.
**When:** Always. The domains have fundamentally different workflows, tool sets, and output formats.
**Why:** Prevents single-agent complexity explosion. Each agent stays focused. TestCase agent has 6 skills and 5-phase flow; Web agent has dual-mode routing; API agent has 7-stage MASTEST pipeline. Combining them would create an unmaintainable monolith.

```python
# Each agent follows this structure (from reference code):
from deepagents import create_deep_agent as create_agent
from deepagents.middleware import SkillsMiddleware

agent = create_agent(
    model=llm,
    tools=[...],           # Domain-specific tools
    backend=composite,      # Shared workspace backend
    middleware=[...],       # Onion middleware stack
    system_prompt=SYSTEM_PROMPT,  # Domain-specific prompt
    context_schema=Context  # Optional runtime context
)
```

### Pattern 2: Onion Middleware Architecture
**What:** Middleware layers wrap the model call in a specific order. Each layer can modify the request (messages, tools, system prompt) before passing it to the next layer. The order matters: outer layers run first on the way in, last on the way out.
**When:** Every agent uses middleware. TestCase agent uses all four layers; other agents use subsets.

```python
# Middleware order matters -- this IS the onion:
middleware=[
    skills_middleware,          # Layer 1 (outermost): Inject SKILL.md content
    dynamic_model_selection,    # Layer 2: Switch text/vision model
    RAGMiddleware(),            # Layer 3: Inject/remove RAG tools
    PDFContextMiddleware()      # Layer 4 (innermost): Extract PDF attachments
]
# Request flows: Skills -> Model -> RAG -> PDF -> LLM
# Response flows: LLM -> PDF -> RAG -> Model -> Skills
```

**Execution flow:**
1. SkillsMiddleware loads SKILL.md files and appends to system message
2. DynamicModelSelection inspects messages for images, overrides model
3. RAGMiddleware checks enable_rag context flag, injects or removes RAG tools
4. PDFContextMiddleware extracts PDF attachments, saves to disk, adds parse prompt

### Pattern 3: Skills System (SKILL.md)
**What:** Modular professional capabilities defined as SKILL.md files in the workspace filesystem. Each skill has a YAML frontmatter (name, description) and structured content (activation scenarios, execution steps, output templates). The SkillsMiddleware loads skills on demand via `read_file` tool.
**When:** All complex agent behaviors. Skills replace hardcoded system prompt instructions with modular, discoverable, versionable knowledge units.

```markdown
# SKILL.md structure (from reference code):
---
name: requirement-analysis
description: Activation conditions and purpose
---
# Skill Title
## Activation Scenarios
- When to activate this skill
## Execution Flow
### Step 1: ...
### Step 2: ...
## Output Template
## Quality Criteria
```

**Skill directories by domain:**
- TestCase: `/testcase/skills/` (6 skills: requirement-analysis, test-strategy, test-case-design, test-data-generator, quality-review, output-formatter)
- Web: `/web/skills/` (pw-dogfood, component-aware-web-automation, agent-browser, playwright-cli, etc.)
- API: `/api/skills/` (test-scenario-design, playwright-api-testing, api-test-quality)
- RAG: `/rag/skills/` (rag-query)

### Pattern 4: Dual-Model Strategy
**What:** Two LLM providers are used -- a cost-efficient text model (DeepSeek Chat) for all text processing, and a multimodal vision model (Doubao Vision) for image/PDF understanding. A middleware layer automatically detects images in messages and switches models.

**When:** Any agent that handles multimodal input (currently TestCase agent only).

```python
@wrap_model_call
async def dynamic_model_selection(request, handler):
    if _has_image_in_messages(request):
        model = image_llm_model  # Doubao Vision
    else:
        model = deepseek_model   # DeepSeek Chat
    return await handler(request.override(model=model))
```

### Pattern 5: MCP Protocol for External Services
**What:** All external tool services are integrated via the Model Context Protocol (MCP), providing a standardized tool interface. The agent discovers tools at runtime via MCP clients (SSE or stdio transport).

**When:** Any integration with external services (RAG, Playwright, Graphify, Docling, Chart visualization).

```python
# SSE transport (RAG server):
MultiServerMCPClient({
    "rag-server": {
        "url": "http://localhost:8008/sse",
        "transport": "sse",
    }
})

# Stdio transport (Playwright, Chart):
MultiServerMCPClient({
    "playwright-api": {
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@executeautomation/playwright-mcp-server"],
    }
})
```

### Pattern 6: Human-in-the-Loop via LangGraph Interrupts
**What:** The LangGraph framework supports interrupt mechanisms that pause agent execution before or after specific nodes (typically tool calls). The frontend renders interrupt actions (approve/reject/edit) and resumes the stream.

**When:** Critical decision points in API testing (scenario review, script review) and tool approval for destructive operations.

```typescript
// Frontend side (from useChat.ts):
stream.submit(undefined, {
  interruptBefore: ["tools"],  // Pause before tool execution
  // or
  interruptAfter: ["tools"],   // Pause after tool execution
});

// Resume with user decision:
stream.submit(null, { command: { resume: value } });
```

### Pattern 7: Multi-Tenant RAG Isolation
**What:** Knowledge base access is isolated per workspace using X-Space-Id headers. Authentication uses JWT tokens (OAuth2 password flow) with automatic re-login on expiry, or API Key as fallback.

**When:** All RAG operations in multi-tenant deployments.

```python
# RAG MCP Server handles isolation:
headers = {"Content-Type": "application/json"}
if self._jwt_token:
    headers["Authorization"] = f"Bearer {self._jwt_token}"
if self.default_space_id:
    headers["X-Space-Id"] = self.default_space_id
```

### Pattern 8: Composite Backend for Workspace Operations
**What:** DeepAgents provides a CompositeBackend that routes operations: filesystem operations (read_file, write_file, glob, grep) go to FilesystemBackend (virtual or real), shell operations (execute) go to LocalShellBackend.

**When:** All agents that need both file management and shell command execution (Web agent, API agent).

```python
CompositeBackend(
    default=shell_backend,      # Default: shell commands
    routes={"/": file_backend},  # Root path: filesystem ops
)
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: God Agent (Single Agent for All Domains)
**What:** Putting test case generation, web automation, and API testing into one agent with all tools and skills.
**Why bad:** Context window pollution, tool selection confusion, system prompt becomes unmaintainable (would exceed 10K tokens), agent cannot reason effectively about which workflow to follow.
**Instead:** Three separate agents, each with focused system prompt, domain-specific tools, and domain-specific skills. Route at the LangGraph server level via graph.json.

### Anti-Pattern 2: Hardcoded Workflow in System Prompt
**What:** Embedding detailed step-by-step instructions (Playwright CLI commands, test thresholds, output templates) directly in the system prompt.
**Why bad:** Token bloat (system prompts already ~3K tokens for TestCase agent), instructions become stale, cannot update without changing code.
**Instead:** Use SKILL.md files. The system prompt only references skill names and activation rules. The agent loads skill content on demand via `read_file` tool. This keeps system prompts concise while making skills independently versionable.

### Anti-Pattern 3: Synchronous RAG Tool Initialization
**What:** Creating MCP clients and fetching tools synchronously at module import time.
**Why bad:** `asyncio.run()` at module level can fail in async contexts, blocks startup, and creates fragile coupling to service availability.
**Instead:** Use `@lru_cache` on tool initialization functions, as the reference code does. The first call establishes the connection; subsequent calls return cached tools.

```python
# Correct (from reference code):
@lru_cache(maxsize=1)
def _cached_rag_tools() -> tuple[BaseTool, ...]:
    client = MultiServerMCPClient({...})
    tools = asyncio.run(client.get_tools())
    return tuple(tools)
```

### Anti-Pattern 4: Skipping Human-in-the-Loop
**What:** Running the entire MASTEST pipeline or 7-Agent web pipeline without pausing for human review between stages.
**Why bad:** Error amplification -- a bad scenario design leads to bad scripts leads to bad test execution. LLM hallucinations in one stage compound in subsequent stages.
**Instead:** Mandatory pause points after each stage that produces user-facing artifacts (scenarios, scripts, quality reports). The MASTEST system prompt explicitly requires: "PAUSE and ask the user to review before proceeding."

### Anti-Pattern 5: Tight Coupling to Single LLM Provider
**What:** Using DeepSeek-specific or Doubao-specific API calls directly in agent code.
**Why bad:** Cannot switch providers, cannot use different models for different tasks, breaks when provider APIs change.
**Instead:** Use `langchain.chat_models.init_chat_model("deepseek:deepseek-chat")` for provider abstraction. The DynamicModelSelection middleware switches models without agent code knowing about specific providers.

### Anti-Pattern 6: Inline PDF Processing in Agent
**What:** Parsing PDF content directly inside the agent's ReAct loop.
**Why bad:** PDF parsing is slow (can take 30+ seconds for large files with images), blocks the agent's reasoning loop, and the parsed content is often too large for the context window.
**Instead:** PDFContextMiddleware extracts PDF before the model call, saves it to disk, and instructs the agent to use the `extract_pdf_text_from_file` tool on demand. The processor uses caching (MD5 hash key) to avoid re-parsing.

## Scalability Considerations

| Concern | At Single User | At Team (10 users) | At Enterprise (100+ users) |
|---------|---------------|--------------------|---------------------------|
| **LangGraph Server** | Single uvicorn process, in-memory state | Add Redis for state, increase N_JOBS_PER_WORKER | Kubernetes deployment, horizontal scaling |
| **LLM API calls** | Sequential, ~2-5 calls per task | Rate limiting needed (DeepSeek has RPM limits) | Queue-based (Celery/RQ), API key rotation |
| **RAG queries** | Single LightRAG instance sufficient | Connection pooling (httpx.AsyncClient already in place) | Separate RAG service cluster, read replicas |
| **MCP services** | All local subprocess (stdio) | Containerize each MCP service, network transport | Service mesh, health monitoring, circuit breakers |
| **Workspace storage** | Local filesystem, single workspace_dir | Per-user workspace isolation needed | Object storage (S3/MinIO), workspace namespacing |
| **Knowledge isolation** | X-Space-Id header (already implemented) | Per-team spaces with JWT auth | Organization -> Team -> Project hierarchy in LightRAG |
| **File uploads** | Temp files on local disk | Upload size limits, cleanup cron | S3 presigned URLs, async processing pipeline |

## Build Order Implications

Based on the component dependency graph, the recommended build order is:

```
Phase 1: Core Infrastructure (no dependencies)
  - Project scaffolding (Python 3.13 + Next.js 16)
  - LangGraph API server setup (graph.json, start_server.py)
  - Core config (Settings, LLM factory, environment variables)
  - FilesystemBackend + CompositeBackend
  - Frontend shell (Next.js + Shadcn/ui + langgraph-sdk)

Phase 2: TestCase Agent Foundation (depends on Phase 1)
  - TestCase agent with basic system prompt
  - SkillsMiddleware + first 3 skills (requirement-analysis, test-case-design, output-formatter)
  - PDF processing pipeline (PyMuPDF4LLM + PDFContextMiddleware)
  - Excel export tool
  - Frontend chat interface with file upload

Phase 3: RAG Knowledge System (depends on Phase 1)
  - LightRAG server deployment (Docker: PostgreSQL + Neo4j + Milvus + Redis + Ollama)
  - RAG MCP Server (7 tools, SSE transport)
  - RAGMiddleware (dynamic tool injection)
  - Frontend RAG toggle integration

Phase 4: Advanced TestCase (depends on Phase 2 + 3)
  - Remaining skills (test-strategy, test-data-generator, quality-review)
  - DynamicModelSelection middleware (Doubao Vision integration)
  - Full 5-phase workflow with quality gates
  - Multi-format export (CSV, JSON, Zentao/TestRail/Jira Xray formats)

Phase 5: Web Automation Agent (depends on Phase 1)
  - Web agent with dual-mode detection
  - Playwright CLI integration (LocalShellBackend)
  - Mode A: Exploratory QA skills (pw-dogfood)
  - Mode B: Component-aware 7-Agent pipeline skills
  - Frontend mode selection UI

Phase 6: API Automation Agent (depends on Phase 1)
  - API agent with MASTEST methodology
  - OpenAPI parser tool (with $ref resolution)
  - Test scenario design + Playwright script generation
  - Coverage metrics tool
  - Human-in-the-Loop integration
  - Chart visualization (antvis MCP)

Phase 7: Multi-Tenant Hardening (depends on all above)
  - JWT authentication for RAG service
  - Workspace-level isolation
  - API Key fallback auth
  - Connection pooling and retry logic
```

**Dependency rationale:**
- Phase 1 must come first because every agent depends on the LangGraph server, backend, and frontend shell.
- Phases 2, 3, and 5+6 can proceed in parallel after Phase 1, but TestCase (Phase 2) is the most mature domain and best starting point.
- Phase 4 requires both Phase 2 (agent foundation) and Phase 3 (RAG system) to be complete.
- Phase 7 is last because multi-tenancy is a cross-cutting concern best added once individual features work.

## Sources

- Direct analysis of reference codebase: `D:/test_agent/2026-05-07-ai-test-agent-system/` (latest, all three agents)
- TestCase agent: `src/app/agents/testcase/agent.py` -- middleware stack, skills, tools, system prompt
- Web agent: `src/app/agents/web/agent.py` -- dual-mode routing, skills middleware
- API agent: `src/app/agents/api/agent.py` -- MASTEST workflow, composite backend
- RAG MCP Server: `src/app/mcp/rag_server.py` -- 7 tools, multi-tenant JWT, retry logic
- Middleware: `src/app/middleware/pdf_context.py`, `src/app/middleware/rag_context.py`
- Frontend: `D:/test_agent/2026-04-09-testing-deep-agents-ui/` -- useChat.ts, useStream hook
- Skills: `D:/test_agent/2026-03-25-testing-agent-system/` -- SKILL.md structure examples
- LightRAG: `D:/test_agent/2026-04-11-anything-chat-rag/` -- knowledge graph infrastructure

**Confidence: HIGH** -- All architectural patterns are directly extracted from working reference code, not theoretical designs.
