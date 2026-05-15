# Phase 10: Agent-Database Integration - Context

**Gathered:** 2026-05-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Connect Agent results to the database for automatic persistence, add test report visualization in chat and management UI, and implement Human-in-the-Loop for critical decision points. This completes the end-to-end flow: chat with agent → generate cases → auto-save to DB → view in management UI → execute tests → see results.

This phase does NOT include new database tables (Phase 8), new management pages (Phase 9), or new Agent capabilities (Phases 2-6). It connects existing systems.

</domain>

<decisions>
## Implementation Decisions

### Auto-Save Trigger
- **D-01:** Agent automatically saves generated test cases to database at the end of its workflow. The `save_test_cases_batch` tool (Phase 8) is called during the output stage of the 5-stage workflow.
  - **Why:** Seamless user experience — no manual copy-paste. Agent tools already have direct DB access (Phase 8 D-05). Matches the "AI-first" design philosophy where the agent handles persistence.
  - **How to apply:** Update Agent system prompt to include `save_test_cases_batch` in the output stage instructions. Agent calls it after generating test cases. Save result (project_id, case identifiers, count) returned in chat message.

- **D-02:** Auto-save targets the current project (from workspace context) and a default folder. If no project exists, Agent creates one automatically.
  - **Why:** Agent needs a project to save cases into. Creating one automatically avoids requiring the user to set up projects before using the chat.
  - **How to apply:** Agent tools check for existing project by workspace_id. If none, create project with auto-generated name. Save cases to project's default folder.

### Human-in-the-Loop
- **D-03:** HITL via Agent text prompts in chat flow. Agent pauses at critical stages and asks user "是否继续？" or presents options. User responds via normal chat message. No LangGraph interrupt mechanism.
  - **Why:** Simpler implementation — no need for LangGraph interrupt infrastructure or frontend approval UI. Agent's existing chat-based interaction is sufficient. The "critical stages" are defined in SKILL.md files as natural conversation breakpoints.
  - **How to apply:** Update SKILL.md files to include HITL checkpoints (e.g., "在执行破坏性操作前，暂停并询问用户确认"). Agent naturally pauses when it asks a question and waits for user response.

- **D-04:** HITL applies to destructive operations only (delete test cases, overwrite existing data, execute test scripts). Non-destructive operations (generate, save, query) proceed automatically.
  - **Why:** Minimize interruption. User expects generation and saving to be automatic. Only actions that could lose data or cause side effects need approval.
  - **How to apply:** SKILL.md defines which operations require HITL. Agent uses conditional logic in tool calls — destructive tools include a confirmation prompt in their instructions.

### Chat Tool Call Visualization
- **D-05:** Agent DB operation results displayed as inline cards in ChatMessage component. Save success = green card with case count + link to management page. Save failure = red error card with retry suggestion.
  - **Why:** Visual feedback without leaving chat. Card format is scannable and actionable. Links to management UI bridge the chat ↔ CRUD gap.
  - **How to apply:** Parse AI message content for tool call result markers (e.g., JSON blocks or structured text from save operations). Render matching patterns as styled cards. Cards include: status icon, summary text, count/link.

- **D-06:** Card rendering uses regex/marker pattern matching on AI message content. No custom message types or LangGraph metadata needed.
  - **Why:** Simplest integration with existing streaming architecture. ChatMessage already renders markdown. Adding card detection as a post-processing step avoids changing the streaming pipeline.
  - **How to apply:** In ChatMessage component, scan message content for patterns like `✅ 已保存 N 条测试用例` or structured JSON from tool results. Replace matching sections with React card components.

### Test Report Visualization
- **D-07:** Use recharts (already installed in Phase 9) for test report charts. No antvis dependency.
  - **Why:** Style consistency with Phase 9 dashboard. recharts already handles bar/pie charts. Avoid adding another charting library with different styling. REQUIREMENTS.md mentions antvis but recharts covers the same needs.
  - **How to apply:** Create report chart components in `webui/src/app/runs/components/` or new `webui/src/app/reports/` route. Reuse existing PassRateChart and RunStatusChart patterns from Phase 9.

### Integration Points
- **D-08:** Agent tools (save_test_cases_batch, list_project_test_cases) are the primary integration mechanism. Frontend reads saved data via FastAPI SWR hooks (Phase 9 pattern). No new API endpoints needed.
  - **Why:** Phase 8 already built the Agent DB tools and FastAPI endpoints. Phase 10 wires them together. No new backend infrastructure.
  - **How to apply:** Agent calls save tool → data in DB → Frontend SWR hooks auto-refresh (mutate/revalidate) → user sees updated data in management pages.

- **D-09:** Chat ↔ Management navigation via deep links. After auto-save, chat message includes clickable link to `/cases?project={id}` or `/cases/{case_id}`.
  - **Why:** Bridges the two halves of the platform. User generates in chat, views in management UI. Deep links with query params enable direct navigation.
  - **How to apply:** ChatMessage card component renders `<Link href="/cases?project=PR-001">` using Next.js Link.

### Claude's Discretion
- Exact SKILL.md HITL checkpoint wording
- Card component styling details
- Report page layout and chart selection
- Error recovery behavior for failed saves
- Cache invalidation strategy after auto-save

### Folded Todos
None — no pending todos matched this phase's scope.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 8 (Database & API — consumed by this phase)
- `src/app/agents/testcase/tools/db_tools.py` — Agent DB tools (save_test_case_to_db, save_test_cases_batch, list_project_test_cases)
- `src/app/db/database.py` — Async engine, session factory
- `src/app/db/models/` — SQLAlchemy models (Projects, TestCases, TestSteps, etc.)
- `src/app/db/services/` — Service layer for CRUD operations
- `src/app/api/v2/` — FastAPI endpoints (projects, test_cases, test_runs, attachments)

### Phase 9 (Frontend UI — extended by this phase)
- `webui/src/app/components/ChatMessage.tsx` — Chat message rendering (add card detection)
- `webui/src/app/components/ChatInterface.tsx` — Chat interface (parent of ChatMessage)
- `webui/src/app/hooks/useChat.ts` — Chat hook (message streaming)
- `webui/src/lib/api-client.ts` — FastAPI client (for SWR revalidation)
- `webui/src/lib/api/useTestCases.ts` — SWR hooks for test cases
- `webui/src/lib/api/useProjects.ts` — SWR hooks for projects
- `webui/src/app/runs/components/PassRateChart.tsx` — Recharts bar chart (reuse pattern)
- `webui/src/app/runs/components/RunStatusChart.tsx` — Recharts pie chart (reuse pattern)

### Agent Configuration
- `src/app/agents/testcase/agent.py` — TestCase Agent entry point
- `src/app/agents/testcase/tools/__init__.py` — Tool registration
- `src/app/agents/testcase/skills/` — SKILL.md files (update with HITL + auto-save instructions)
- `src/app/agents/testcase/system_prompt.py` — System prompt (if exists, update with save instructions)

### Project Planning
- `.planning/REQUIREMENTS.md` — Requirements PLAT-14 through PLAT-17
- `.planning/ROADMAP.md` — Phase 10 details
- `.planning/phases/08-fastapi-backend-database/08-CONTEXT.md` — Phase 8 decisions (D-05/D-06 critical)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/app/agents/testcase/tools/db_tools.py` — 3 Agent DB tools already built. save_test_cases_batch handles batch creation with folder assignment and identifier generation.
- `webui/src/app/runs/components/PassRateChart.tsx` — Recharts BarChart pattern ready for report charts.
- `webui/src/app/runs/components/RunStatusChart.tsx` — Recharts PieChart pattern ready for report charts.
- `webui/src/app/components/ChatMessage.tsx` — Already renders markdown with react-markdown. Extension point for card detection.
- `webui/src/lib/api/useTestCases.ts` — SWR hooks with mutate() for cache revalidation after Agent saves.

### Established Patterns
- **Agent Tools**: @tool decorator with async_session_factory() for DB access (Phase 8 D-05)
- **Chat Streaming**: SSE via @langchain/langgraph-sdk useStream hook
- **Message Rendering**: react-markdown with remark-gfm in ChatMessage
- **SWR Revalidation**: mutate() after mutations for cache updates
- **Workspace**: X-Space-Id header propagation across all API calls

### Integration Points
- Agent → DB: save_test_cases_batch tool (already exists, needs to be called by agent automatically)
- DB → Frontend: FastAPI SWR hooks (already exist, need cache revalidation trigger)
- Chat → Management: Deep links in chat messages (new, via card component)
- Agent → Chat: Tool call results in AI message content (new, via card markers)

</code_context>

<specifics>
## Specific Ideas

- Auto-save card shows: ✅ status, case count, project name, folder name, and a clickable link to `/cases?project={id}`
- HITL defined in SKILL.md as conversation prompts — no code-level interrupt needed
- Report charts reuse recharts patterns from Phase 9 PassRateChart/RunStatusChart
- ChatMessage card detection uses regex on AI message content (look for structured save result text)
- After Agent auto-saves, trigger SWR mutate on useTestCases/useProjects hooks to refresh management UI

</specifics>

<deferred>
## Deferred Ideas

- Real-time WebSocket updates for management pages (polling/SWR revalidation sufficient for now)
- Agent-generated test execution (Phase 10 only handles case persistence, not test running)
- Advanced HITL with approval UI (LangGraph interrupt — deferred to future if needed)
- antvis chart library (recharts covers all current needs)
- Email/notification for completed Agent workflows
- Agent result diff comparison (before/after edits)

---

*Phase: 10-agent-database-integration*
*Context gathered: 2026-05-15*
