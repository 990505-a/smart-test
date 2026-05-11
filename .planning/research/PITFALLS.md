# Domain Pitfalls

**Domain:** AI-Powered Intelligent Test Platform (Agent + RAG + MCP + Skills + Tools)
**Researched:** 2026-05-11

## Critical Pitfalls

Mistakes that cause rewrites or major issues.

### Pitfall 1: LLM Hallucination in Test Case Generation Without RAG Guardrails

**What goes wrong:** The LLM fabricates test cases that appear plausible but reference non-existent requirements, invented business logic, or incorrect domain knowledge. In a testing platform, this is catastrophic because the output is trusted as authoritative test coverage. Users import hallucinated test cases into test management systems (Zentao/TestRail/Jira Xray) and execute them against production systems.

**Why it happens:** DeepSeek Chat has no inherent knowledge of the user's specific application domain. Without RAG-first enforcement, the model fills gaps with statistically plausible but factually wrong content. The MASTEST paper (arXiv:2511.18038) confirmed that while LLM-generated scripts achieve 100% syntax correctness, they still require "minimal manual edits for semantic correctness" -- meaning semantic errors survive syntactic validation.

**Consequences:** Test teams waste hours reviewing and correcting hallucinated cases. Trust in the platform erodes. Worse, hallucinated test cases may produce false negatives (passing tests that should fail) or false positives (failing tests for reasons that don't exist in the actual system).

**Prevention:**
- Enforce the RAG-First strategy as a mandatory middleware layer, not an optional toggle. Every test case generation request must go through RAG retrieval before the LLM generates output.
- Implement source attribution: each generated test case must reference the specific document section it was derived from.
- Add a "grounding score" to the quality assessment phase -- if the RAG retrieval returned no relevant context, refuse to generate test cases and instead prompt the user to upload documentation.
- In the 5-stage mandatory workflow, add an explicit check at the "quality self-check" stage that verifies each test case traces back to a retrieved RAG chunk.

**Detection:** Generated test cases contain terminology, feature names, or business rules not present in any uploaded document. Test cases reference modules or endpoints that do not exist in the system under test.

**Phase:** Must be addressed in Phase 1 (Test Case Generation Agent) -- the RAG middleware and source attribution are foundational.

---

### Pitfall 2: MCP Tool Integration Fragility Without Resilience Patterns

**What goes wrong:** The platform depends on three external MCP servers (Docling for document parsing, Graphify for code knowledge graphs, Playwright for browser automation). When any MCP server becomes unresponsive, the entire agent pipeline hangs or fails silently. The MCP protocol uses JSON-RPC 2.0 over stdio or Streamable HTTP transports -- both require explicit timeout, retry, and health-check handling that is easy to overlook.

**Why it happens:** The MCP specification describes tool invocation as a simple request-response pattern, but production reality involves: server process crashes, OOM kills on Docling (large PDF parsing), Graphify Neo4j connection pool exhaustion, and Playwright browser session leaks. Without connection pooling, retry logic with exponential backoff, and circuit breaker patterns, a single slow MCP server blocks the entire agent's ReAct loop.

**Consequences:** Agent loops hang indefinitely waiting for tool responses. Users see "generating..." with no feedback. Cascading failures when one MCP server's timeout fills the agent's context window with error messages, leaving no room for actual reasoning.

**Prevention:**
- Implement per-tool timeouts (Docling: 60s for large documents, Graphify: 30s for graph queries, Playwright: 120s for complex page interactions).
- Add health-check endpoints that the agent calls before invoking tools: the RAG MCP Server's 7 tools already include a health-check tool (extend this pattern).
- Implement circuit breaker pattern: after 3 consecutive failures to an MCP server, mark it as degraded and fall back to alternative strategies (e.g., skip Graphify, use only OpenAPI spec parsing for API tests).
- Log all MCP tool invocations with timing data to detect slow degradation before it becomes a total failure.
- Use MCP's Streamable HTTP transport with proper session management (Mcp-Session-Id) rather than stdio for the remote MCP servers, enabling better connection lifecycle control.

**Detection:** Agent response times spike unpredictably. Tool call success rate drops below 95%. Context window usage grows unexpectedly (error messages accumulating).

**Phase:** Must be addressed in Phase 1 (foundational MCP integration) and reinforced in Phase 2 (Web Agent) and Phase 3 (API Agent).

---

### Pitfall 3: Multi-Tenant Data Isolation Failure in RAG Knowledge Base

**What goes wrong:** Tenant A's documents are returned in Tenant B's RAG queries. In a test platform, this means one company's proprietary requirements and test strategies leak to another company. This is both a data security breach and a test quality issue (test cases generated from wrong company's context).

**Why it happens:** LightRAG and RAGAnything operate on shared vector stores (Milvus) and graph databases (Neo4j). The default query modes (naive, local, global, hybrid, combo, naive-rag) search across all indexed documents. Adding workspace-level filtering requires modifying the query pipeline at multiple layers: vector search metadata filters, graph traversal scope limits, and embedding namespace partitioning. It is tempting to add filtering "later" -- but by then, data is already cross-contaminated.

**Consequences:** Regulatory violations (GDPR, data residency). Loss of enterprise customer trust. Test cases containing sensitive business logic from other tenants. Complete data migration required to fix after-the-fact (costly and error-prone).

**Prevention:**
- Design workspace isolation from day one, not as a Phase 2 add-on. Every RAG query must include workspace_id as a mandatory filter parameter.
- Use Milvus collection-level or partition-level isolation (one partition per workspace, or separate collections for high-security tenants).
- In Neo4j, add workspace_id as a node property on every entity and relationship, and enforce it in all Cypher queries via query rewriting.
- Implement JWT + API Key dual authentication at the RAG MCP Server level, not just at the API gateway. The MCP server itself must validate tenant identity before executing any query.
- Add integration tests that verify cross-tenant data leakage is impossible: insert document for tenant A, query as tenant B, assert zero results from tenant A's data.

**Detection:** RAG query results contain document fragments the current tenant never uploaded. Knowledge graph entities reference other companies' projects.

**Phase:** Must be addressed in Phase 1 (RAG integration) -- it is architecturally foundational and nearly impossible to retrofit cleanly.

---

### Pitfall 4: Playwright CLI Session State Leakage Between Test Runs

**What goes wrong:** The Web Automation Agent generates Playwright test scripts and executes them via CLI. Browser sessions, cookies, localStorage, and authentication tokens persist between test runs. Test A (as admin) leaves behind state that Test B (as anonymous user) inherits, producing false test results. The 7-Agent Director Pipeline's "Continuity Lead" is supposed to manage this, but the CLI execution layer itself must enforce isolation.

**Why it happens:** Playwright's `storageState` persistence is designed for reuse (speed optimization), but in an AI-generated test context, the agent may not generate proper cleanup or context isolation code. The default Playwright behavior shares browser contexts within a test file. Additionally, video recording and trace files from previous runs consume disk space if not cleaned up.

**Consequences:** Flaky test results that pass locally but fail in CI (or vice versa). Security test false negatives (authenticated state leaking into unauthenticated tests). Disk space exhaustion from accumulated session recordings.

**Prevention:**
- Enforce Playwright's test isolation best practices: each generated test script must use `test.beforeEach` hooks to reset state, or use Playwright's built-in test isolation which creates a fresh browser context per test.
- Configure Playwright to use ephemeral browser contexts (`browser.newContext()`) with explicit `clearCookies()` and `clearStorageState()` between tests.
- Set `use.storageState` to undefined by default (no persisted auth), requiring explicit authentication steps in each test.
- Add automatic cleanup of video recordings and traces after test report generation.
- The "Stage Manager" agent in the 7-Agent pipeline should generate cleanup code as part of its output, not leave it to the user.

**Detection:** Tests pass when run individually but fail when run as a suite. Test results show authenticated behavior in tests that should be anonymous. Disk usage grows linearly with test run count.

**Phase:** Phase 2 (Web Automation Agent) -- this is specific to the Playwright integration.

---

### Pitfall 5: OpenAPI Spec Parsing Breaks on $ref Resolution and Complex Schemas

**What goes wrong:** The API Automation Agent fails to parse real-world OpenAPI/Swagger specifications. Common failure points: circular `$ref` references (recursive schemas), external `$ref` references to other files, `allOf`/`oneOf`/`anyOf` composition with conflicting properties, `$ref` pointing to definitions in external URLs, and specs with malformed JSON/YAML.

**Why it happens:** The OpenAPI specification allows complex schema composition patterns that are valid per spec but rarely handled correctly by simple JSON dereferencing. A naive `$ref` resolver that uses simple string replacement will fail on circular references (infinite recursion), miss remote references, and produce incorrect merged schemas for `allOf` with conflicting required fields. The MASTEST paper found that API operation coverage varied significantly between LLMs (GPT-4o was best), suggesting that the quality of spec parsing directly affects downstream test generation.

**Consequences:** API test generation fails silently on complex specs, producing incomplete test suites that miss critical edge cases. Users with large, real-world API specs (hundreds of endpoints) get partial coverage with no warning about what was skipped.

**Prevention:**
- Use a battle-tested OpenAPI parser library (not hand-rolled $ref resolution). In Python, `openapi-spec-validator` + `prance` or `jsonschema` for dereferencing. These handle circular refs, remote refs, and schema composition correctly.
- Add a pre-processing validation step: parse the spec, report unresolved references, warn on circular dependencies, and estimate coverage (how many endpoints were fully resolved).
- Implement a fallback strategy: if full $ref resolution fails for an endpoint, generate tests based on the raw (unresolved) schema with explicit TODO markers for manual completion.
- Test the parser against the full OpenAPI 3.0/3.1 test suite and real-world specs (Stripe API, GitHub API, Kubernetes API) before shipping.

**Detection:** Parser errors on specs that validate with Swagger Editor. Generated test scripts reference undefined schema names. API operation coverage drops below 80% on complex specs.

**Phase:** Phase 3 (API Automation Agent) -- this is the foundational parsing layer.

---

### Pitfall 6: Dual-Model Switching Latency and Context Loss

**What goes wrong:** The onion middleware architecture switches between DeepSeek Chat (text) and Doubao Vision (multimodal) based on content type. The switching introduces latency (model loading, API round-trip) and worse, loses context that was built in the previous model's session. A PDF with mixed text and images requires multiple switches, and each switch may lose nuanced understanding from the previous model's analysis.

**Why it happens:** The two models have different context windows, different tokenization, and different system prompt handling. When switching from DeepSeek to Doubao for image analysis, the accumulated text understanding (requirements, test strategy decisions) must be serialized into a prompt for the new model. This serialization is lossy -- complex reasoning chains do not survive the transfer intact.

**Consequences:** Test cases generated from multi-modal documents are inconsistent -- text sections are handled well but image-based requirements (diagrams, flowcharts, UI mockups) produce generic or irrelevant test cases. Total generation time doubles due to model switching overhead.

**Prevention:**
- Minimize model switches by batching content by modality first: extract all text sections, process them with DeepSeek, then extract all images, process them with Doubao Vision, and merge results.
- Design the context transfer format explicitly: create a structured "handoff document" that captures key decisions, entities, and constraints from the text model for the vision model.
- Add a "model switching cost" metric to the quality assessment -- if switching overhead exceeds 30% of total processing time, consider single-model fallback.
- Cache model responses per document section to avoid re-processing when the user adjusts parameters.
- Consider using DeepSeek's own vision capabilities (if available) for simpler images to avoid the switch entirely.

**Detection:** Total generation time exceeds 2x the single-model baseline. Test quality scores drop on documents with mixed text/image content compared to text-only documents.

**Phase:** Phase 1 (Test Case Generation Agent, middleware layer).

---

### Pitfall 7: Skills Middleware Chain Ordering and Context Accumulation

**What goes wrong:** The onion middleware architecture processes requests through Skills in a fixed order (Skills injection -> model selection -> PDF context -> RAG context). If the ordering is wrong, or if a middleware layer fails silently, downstream layers operate on incomplete or corrupted context. The 6 professional skills (requirements analysis, test strategy, case design, test data generation, quality review, output formatting) are designed as a pipeline, but the middleware layer can inject context in the wrong order, causing skills to receive stale or irrelevant information.

**Why it happens:** The onion (nested) middleware pattern wraps handlers like layers of an onion -- the outermost middleware executes first on the way in and last on the way out. If RAG context injection happens before PDF context injection, the RAG retrieval may miss keywords that the PDF context would have provided. If the model selection middleware runs before skill injection, the model may not know which skills are available and generate output that conflicts with skill-defined templates.

**Consequences:** Generated test cases ignore RAG-retrieved context (because it was overwritten by later middleware). Skills produce output in the wrong format because they received the wrong model's response. The 5-stage mandatory workflow skips stages because the skill activation logic received stale trigger conditions.

**Prevention:**
- Document the exact middleware execution order and make it enforceable via configuration, not code. The correct order for this platform is: RAG context (outermost, provides domain knowledge) -> PDF context (adds document specifics) -> Model selection (chooses appropriate model) -> Skills injection (innermost, provides task-specific guidance).
- Add middleware chain validation: each layer should log what context it received and what it added. If a layer receives context that contradicts what it expects, log a warning.
- Implement "context snapshot" at each middleware boundary for debugging -- store the full context state before and after each layer.
- Write integration tests that verify the full middleware chain produces correct output for known inputs (golden test cases).

**Detection:** Test quality scores are inconsistent for similar documents. Debugging reveals context keys being overwritten. Skills generate output that contradicts RAG-retrieved knowledge.

**Phase:** Phase 1 (Test Case Generation Agent, architecture foundation).

---

### Pitfall 8: Agent Context Window Exhaustion in Long Pipelines

**What goes wrong:** The ReAct Agent loop accumulates context with each tool call, skill execution, and middleware layer injection. For complex test generation requests (large PDFs, extensive API specs), the agent's context window fills up before completing the 5-stage workflow. The agent either truncates earlier context (losing the requirements analysis) or fails mid-generation.

**Why it happens:** A single test generation request might involve: initial user request (~500 tokens) + RAG retrieval results (~2000 tokens) + PDF context (~3000 tokens) + skill definitions for 6 skills (~1500 tokens) + intermediate agent reasoning across 5 stages (~5000 tokens) + tool call results (~2000 tokens). This totals ~14,000 tokens of input, and the generated output adds more. With DeepSeek's context limits, complex requests can hit the ceiling.

**Consequences:** The agent stops mid-workflow, producing partial test case sets. Earlier stages' analysis is lost when the window fills, so the agent "forgets" requirements while designing test cases. Users receive incomplete or incoherent output with no explanation.

**Prevention:**
- Implement progressive summarization: after each of the 5 workflow stages, summarize the key decisions and pass only the summary to the next stage (not the full reasoning chain).
- Use a "scratchpad" pattern: offload intermediate reasoning to external storage (Redis/database) and retrieve only what's needed for the current stage.
- Monitor context window usage in real-time during agent execution. If usage exceeds 70%, trigger aggressive summarization of earlier stages.
- Design each skill to produce concise, structured output (not verbose explanations) to minimize context consumption.
- Consider splitting the 5-stage workflow into separate agent calls with explicit handoffs, rather than a single long-running agent session.

**Detection:** Agent output quality degrades for complex inputs. Partial test case sets with missing stages. "Token limit exceeded" errors in agent logs.

**Phase:** Phase 1 (architectural pattern) and refined in Phase 2 and Phase 3 (7-Agent pipeline and MASTEST multi-agent system).

---

### Pitfall 9: Generated Playwright Scripts Are Brittle and Non-Portable

**What goes wrong:** The LLM generates Playwright TypeScript scripts that work on one specific page state but break when the target application changes even slightly. Common issues: CSS selector-based locators instead of user-facing attributes, hardcoded wait times instead of web-first assertions, missing error handling for network failures, and scripts that don't follow Playwright's isolation best practices.

**Why it happens:** LLMs generate Playwright code based on training data patterns, which often includes outdated practices (XPath selectors, `page.waitForTimeout`). The LLM does not see the actual page -- it reasons from the URL or source code description. Without the Playwright MCP Server's live page inspection, the generated selectors are guesses.

**Consequences:** Generated scripts have a high false-failure rate. Users spend more time fixing generated scripts than writing them manually. The platform's value proposition (AI-generated testing) is undermined.

**Prevention:**
- Enforce Playwright best practices in the system prompt and skill definitions: require `getByRole`, `getByText`, `getByTestId` locators (never CSS selectors or XPath). The Playwright official docs explicitly recommend "user-facing attributes to XPath or CSS selectors."
- Require web-first assertions (`await expect(locator).toBeVisible()`) instead of manual assertions (`expect(await locator.isVisible()).toBe(true)`).
- Include the Playwright MCP Server's live page inspection in the generation loop: generate a draft script, execute it in headed mode, inspect failures, and refine selectors before delivering to the user.
- For the component-aware mode (source code analysis), inject data-testid attributes into the generated test scripts based on source code analysis, ensuring deterministic element targeting.
- Add a "script quality" linter that checks generated scripts against Playwright best practices before delivery.

**Detection:** Generated scripts use `page.locator('css.selector')` or `page.waitForTimeout()`. Scripts fail on the first run more than 20% of the time. Scripts break when the target application's CSS changes.

**Phase:** Phase 2 (Web Automation Agent).

---

### Pitfall 10: SSE Transport Deprecation in MCP Integration

**What goes wrong:** The platform integrates MCP servers that may still use the legacy SSE transport (HTTP+SSE), which is now deprecated in favor of Streamable HTTP. If MCP server implementations (Docling, Graphify, Playwright MCP Server) use the deprecated transport, the platform will face breaking changes when the transport is removed from MCP clients.

**Why it happens:** The MCP specification deprecated the SSE transport. The official docs state that clients should attempt Streamable HTTP first and fall back to legacy SSE only for backward compatibility. New MCP server implementations should use Streamable HTTP exclusively. However, many existing MCP server libraries and tutorials still reference the SSE pattern.

**Consequences:** Platform breaks when upgrading MCP client libraries. Degraded performance with the legacy transport. Complex dual-transport support code that must be maintained.

**Prevention:**
- Verify which transport each MCP server uses (Docling, Graphify, Playwright). If any uses legacy SSE, plan migration to Streamable HTTP.
- Implement the transport detection pattern from the MCP docs: try Streamable HTTP POST first, fall back to legacy SSE GET if it fails with 4xx.
- For custom MCP servers (like the RAG MCP Server), implement Streamable HTTP from the start with proper session management (Mcp-Session-Id header).
- Add Origin header validation and localhost binding for all MCP transports as specified in the MCP security considerations.

**Detection:** MCP client library upgrade changelogs mention SSE removal. Transport fallback occurs frequently in logs.

**Phase:** Phase 1 (MCP integration foundation).

## Moderate Pitfalls

### Pitfall 11: RAG Knowledge Base Staleness

**What goes wrong:** Documents are indexed into the RAG knowledge base once but never updated. When requirements change, the RAG returns stale information, and the agent generates test cases based on outdated specifications.

**Prevention:** Implement document versioning in the RAG pipeline. When a document is re-uploaded, detect changes and re-index only the modified sections. Add a "last updated" timestamp to RAG query results and warn the user if the most recent document is older than a configurable threshold.

**Phase:** Phase 1 (RAG integration).

---

### Pitfall 12: 7-Agent Director Pipeline Coordination Failures

**What goes wrong:** The Web Automation Agent's 7-Agent Director Pipeline (Script Analyst, Stage Manager, Blocking Coach, Set Designer, Choreographer, Assistant Director, Continuity Lead) produces inconsistent output when agents disagree. For example, the Script Analyst identifies a complex interaction flow, but the Choreographer generates simplistic step definitions that don't match.

**Prevention:** Define clear contracts between each agent in the pipeline. Each agent's output must conform to a typed schema that the next agent can validate. Add a "director review" step where the Assistant Director validates that all agents' outputs are consistent before assembling the final script.

**Phase:** Phase 2 (Web Automation Agent).

---

### Pitfall 13: Test Case Numbering Collisions

**What goes wrong:** The TC-[PROJECT]-[MODULE]-[NNN] numbering scheme produces duplicate test case IDs when multiple users generate test cases for the same project/module combination simultaneously, or when regenerating test cases for an updated document.

**Prevention:** Implement a central test case ID registry (even a simple Redis counter per project/module prefix). Check for existing IDs before assigning new ones. Support configurable numbering strategies (sequential, hash-based, UUID-suffix) for different team workflows.

**Phase:** Phase 1 (Test Case Generation Agent).

---

### Pitfall 14: Excel Export Format Drift

**What goes wrong:** The multi-format Excel export (compatible with Zentao, TestRail, Jira Xray) produces files that don't import correctly due to subtle format differences between what these tools expect. Column headers change between versions of these tools, and the export templates break.

**Prevention:** Maintain separate export templates per target tool, validated against the tool's current import specification. Add integration tests that export sample test cases and verify they import successfully into each target tool's test environment. Version the export templates alongside the tool's API version.

**Phase:** Phase 1 (Test Case Generation Agent).

---

### Pitfall 15: Human-in-the-Loop Bottleneck

**What goes wrong:** The MASTEST methodology includes human review checkpoints, but the implementation creates bottlenecks: the agent pauses waiting for human approval on every test case, or provides no way to batch-approve similar cases. Users abandon the review process and accept all generated output without reading it.

**Prevention:** Implement smart batching for human review: group similar test cases and present them for batch approval. Use confidence scores from the quality assessment to auto-approve high-confidence cases and only escalate low-confidence ones. Provide a "review queue" with filtering and sorting (by confidence score, by test type, by module).

**Phase:** Phase 3 (API Automation Agent, Human-in-the-Loop integration).

## Minor Pitfalls

### Pitfall 16: Embedding Model Mismatch

**What goes wrong:** The platform uses Ollama qwen3-embedding:0.6b for RAG embeddings, but this small model produces low-quality embeddings for technical domain vocabulary, resulting in poor RAG retrieval accuracy.

**Prevention:** Evaluate embedding quality with domain-specific benchmarks before committing. Consider upgrading to a larger embedding model (e.g., bge-large, text-embedding-3-small) for production use. Keep qwen3-embedding:0.6b for development only.

**Phase:** Phase 1 (RAG integration).

---

### Pitfall 17: LangGraph Streaming Disconnects

**What goes wrong:** The frontend uses @langchain/langgraph-sdk for real-time streaming, but the SSE connection drops during long-running agent executions (complex test generation can take 30+ seconds). The user sees a frozen UI with no indication of whether the agent is still processing.

**Prevention:** Implement client-side reconnection with event ID tracking (as specified in MCP's Streamable HTTP resumability pattern). Add a "heartbeat" indicator showing the agent's current stage. Fall back to polling if streaming fails.

**Phase:** Phase 4 (Frontend).

---

### Pitfall 18: Port Conflicts in Docker Deployment

**What goes wrong:** The platform requires multiple services (LangGraph API :2026, Frontend :3000, LightRAG :9621, PostgreSQL, Neo4j, Redis, Milvus, Ollama). Port conflicts with existing services cause deployment failures that are hard to diagnose.

**Prevention:** Use Docker Compose with configurable port mappings via .env file. Default to the documented ports but allow overrides. Add a pre-flight check that scans for port availability before starting services.

**Phase:** Infrastructure/DevOps phase.

---

### Pitfall 19: DeepSeek API Rate Limiting Under Concurrent Users

**What goes wrong:** Multiple users generating test cases simultaneously hit DeepSeek API rate limits, causing 429 errors that the agent interprets as tool failures and retries aggressively, making the rate limiting worse.

**Prevention:** Implement request queuing with rate limiting at the application layer (not relying on the LLM provider's retry-after headers). Use Redis-based request deduplication for identical queries. Add user-visible queue position indicators.

**Phase:** Phase 1 (scaling consideration).

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| RAG Knowledge Base Integration | Multi-tenant isolation failure (Pitfall 3) | Design workspace-scoped queries from day one |
| MCP Server Integration | Transport fragility, SSE deprecation (Pitfalls 2, 10) | Implement health checks, circuit breakers, Streamable HTTP |
| Test Case Generation | LLM hallucination without grounding (Pitfall 1) | RAG-First mandatory, source attribution, grounding score |
| Onion Middleware Architecture | Context ordering errors (Pitfall 7) | Document and enforce middleware execution order |
| Playwright Web Automation | Session state leakage (Pitfall 4), brittle scripts (Pitfall 9) | Fresh contexts per test, enforce user-facing locators |
| OpenAPI Spec Parsing | $ref resolution failures (Pitfall 5) | Use battle-tested parser, pre-validate specs |
| Dual-Model Switching | Context loss and latency (Pitfall 6) | Batch by modality, explicit context handoff |
| Long Agent Pipelines | Context window exhaustion (Pitfall 8) | Progressive summarization, scratchpad pattern |
| 7-Agent Pipeline | Coordination failures (Pitfall 12) | Typed contracts between agents, director review |
| Frontend Streaming | SSE disconnects (Pitfall 17) | Reconnection with event IDs, heartbeat indicator |

## Sources

- MASTEST paper (arXiv:2511.18038) -- confirmed LLM test generation achieves 100% syntax correctness but requires semantic corrections
- MCP Official Documentation (modelcontextprotocol.io/docs/concepts/tools) -- tool error handling, session management, Streamable HTTP transport, SSE deprecation
- MCP Transports Documentation (modelcontextprotocol.io/docs/concepts/transports) -- Streamable HTTP session management, resumability, security considerations
- Playwright Best Practices (playwright.dev/docs/best-practices) -- test isolation, user-facing locators, web-first assertions
- LangChain Issues (github.com/langchain-ai/langchain/issues) -- RAG hallucination mitigation patterns, post-RAG verification approaches
- Project context (.planning/PROJECT.md) -- architecture decisions, technology choices, 12-week learning trajectory

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| LLM Hallucination Pitfalls | HIGH | Verified by MASTEST paper, well-documented in LangChain ecosystem |
| MCP Integration Pitfalls | HIGH | Direct from official MCP specification and transport docs |
| Multi-Tenant RAG Isolation | HIGH | Standard vector database partitioning patterns, well-understood failure mode |
| Playwright Session Management | HIGH | From official Playwright best practices documentation |
| OpenAPI Parsing Edge Cases | MEDIUM | Common knowledge in API tooling space, specific library behavior may vary |
| Dual-Model Switching | MEDIUM | Based on architectural analysis, not direct production experience with DeepSeek + Doubao pairing |
| Skills Middleware Ordering | MEDIUM | Based on onion middleware pattern analysis, specific to DeepAgents framework behavior |
| 7-Agent Pipeline Coordination | LOW | Novel architecture, no production post-mortems available; based on multi-agent system design principles |
