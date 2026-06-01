---
status: awaiting_human_verify
trigger: "Full audit of smart-test-platform: 5 dimensions of design/implementation issues"
created: 2026-05-28T00:00:00Z
updated: 2026-05-28T00:00:00Z
---

## Current Focus

hypothesis: CONFIRMED - Multiple root causes found and fixes applied
test: Code audit + fix implementation completed
expecting: Fixes address the three critical blocking issues
next_action: Await human verification of full end-to-end flow

## Symptoms

expected: End-to-end flow: Upload PDF -> frontend extracts text & embeds in message + saves to workspace -> main agent analyzes -> saves phase1/phase2 -> sub-agents read all files + check code -> generate test cases -> Phase 5 saves to DB -> frontend displays results
actual: Never completed a full run. Thread state bloat, agent reads wrong files, sub-agent info breakage, Command object errors, case saving never succeeded
errors: Various errors across multiple sessions
reproduction: Upload 3-4 PDF + MD files, request test case generation, observe full flow
started: Persistent multi-day iteration

## Eliminated

(none yet - initial audit)

## Evidence

- timestamp: 2026-05-28T00:01
  checked: multimodal.ts -> upload-to-workspace data flow
  found: CRITICAL BUG - multimodal.ts line 102-109 sends raw base64 `data` to /api/upload-to-workspace, NOT the extracted text. The backend upload-to-workspace endpoint expects base64-encoded raw file bytes, decodes them, and for PDFs calls extract_pdf_text on the raw bytes. For markdown files, it decodes the raw bytes as utf-8. This WORKS correctly - the backend does its own extraction. However, multimodal.ts does NOT pass `spaceId` or `agentName` to the upload endpoint.
  implication: Files always save to workspace/default/testcase/uploads/ regardless of which workspace the user is in

- timestamp: 2026-05-28T00:02
  checked: multimodal.ts upload-to-workspace call parameters
  found: CRITICAL BUG - The fetch call on line 102-109 sends `{data, filename, mimeType}` but does NOT send `spaceId` or `agentName`. The Next.js proxy route.ts forwards these as `space_id: spaceId || "default"` and `agent_name: agentName || "testcase"`. So all uploads go to default workspace.
  implication: If user is in a non-default workspace, uploaded files go to wrong directory. But for most use cases this works because default is used.

- timestamp: 2026-05-28T00:03
  checked: agent.py file_backend initialization
  found: CRITICAL BUG - Line 71-73: `file_backend = FilesystemBackend(root_dir=_default_workspace_dir, virtual_mode=True)` where `_default_workspace_dir = get_workspace_dir("default", "testcase")`. This is hardcoded to space_id="default". The agent's file tools always resolve virtual paths relative to workspace/default/testcase/, regardless of which workspace the user specified.
  implication: upload-to-workspace saves to workspace/{space_id}/testcase/uploads/ but agent reads from workspace/default/testcase/uploads/. If space_id != "default", the agent can NEVER find uploaded files.

- timestamp: 2026-05-28T00:04
  checked: ensure_project database query
  found: CRITICAL BUG - Line 222-225: `select(Project).limit(1)` returns the FIRST project in the database. It does NOT filter by workspace, name, or any criteria. This means: (a) If ANY project already exists, it returns that one (could be from a completely different requirement), (b) New projects for different requirements never get created, (c) All test cases from all sessions accumulate under the same project.
  implication: Phase 5 saving always uses wrong project. Test cases from different requirements mix together.

- timestamp: 2026-05-28T00:05
  checked: ToolResultLimiterMiddleware Command object handling
  found: OK - The middleware checks `isinstance(result, ToolMessage)` on line 60. If a tool returns a Command object (from deepagents), it would NOT be a ToolMessage and would pass through untruncated. This is actually correct behavior since Commands are agent-level control flow, not tool results.
  implication: No bug here, Command objects handled correctly

- timestamp: 2026-05-28T00:06
  checked: System prompt "上传文件说明" section consistency
  found: AMBIGUITY - Line 382-385 says: (1) "无需再使用 read_file 读取上传文件" for main agent (text embedded in messages), but (2) "子智能体可通过 ls("/uploads/") 查看并 read_file 读取". This is correct for the main agent but creates a subtle inconsistency: the sub-agent task template on line 183 says to use `ls("/uploads/")` and `read_file` to read original files. But sub-agents spawned by the task tool share the SAME file_backend (workspace/default/testcase/). So they CAN read /uploads/ files IF they're in the same workspace. However, sub-agents also need to read phase1/phase2 files from /workspace/ - which maps to workspace/default/testcase/workspace/ in the virtual filesystem. This means write_file("/workspace/phase1_...") writes to workspace/default/testcase/workspace/phase1_... while the prompt says "/workspace/phase1_...".
  implication: Phase file saves and sub-agent reads should work because both use the same file_backend. The virtual path /workspace/ maps to workspace/default/testcase/workspace/. BUT: the upload-to-workspace saves to workspace/{space_id}/testcase/uploads/ which for default = workspace/default/testcase/uploads/ = virtual path /uploads/. This is consistent for default workspace.

- timestamp: 2026-05-28T00:07
  checked: save_test_cases_batch error handling
  found: POTENTIAL ISSUE - Line 119-165: The batch save has a try/except that catches per-case errors but continues. However, if ANY case fails, it still calls `await session.commit()` at the end (line 156). This means partial saves can happen: some cases saved, some failed. The outer try/except on line 164 catches session-level errors and does rollback. But the per-case try/except on line 123-154 catches errors AFTER session.add() and session.flush() - if flush fails for one case, subsequent cases may also fail because the session is in a bad state.
  implication: Batch saves may partially succeed or fail in unexpected ways when individual cases have validation errors.

- timestamp: 2026-05-28T00:08
  checked: Frontend proxy route error handling
  found: MINOR ISSUE - extract-pdf route.ts line 26-30: If backend is unavailable, returns fallback text "[PDF uploaded: ... Backend extraction unavailable.]". But the frontend multimodal.ts treats resp.ok (200 status) as success. The fallback returns status 200 with placeholder text, so the user sees "[Text extraction failed or unavailable.]" in the chat. This is acceptable degradation.
  implication: Non-blocking, graceful degradation for PDF extraction

- timestamp: 2026-05-28T00:09
  checked: ChatMessage.tsx stripInternalContent
  found: OK - Line 107-108: `result.replace(/\n*\[Uploaded \d+ file\(s\)\]\n*/g, "\n")` removes the "[Uploaded N file(s)]" header but keeps the "### File:" content visible. This is correct.
  implication: File content properly displayed in chat

- timestamp: 2026-05-28T00:10
  checked: useChat.ts message format
  found: OK - Line 97-99: File text is embedded as `### File: ${filename}\n\n${extractedText}` which matches the system prompt's expected format. The `[Uploaded N file(s)]` wrapper is added on line 103-104.
  implication: Message format is correct and consistent

## Resolution

root_cause: Three critical bugs: (1) ensure_project used select(Project).limit(1) returning ANY first project regardless of name, causing all sessions to share one project and mix test cases. (2) save_test_cases_batch had broken error recovery - per-case flush failures left session in invalid state, poisoning subsequent cases. (3) multimodal.ts did not pass spaceId to upload-to-workspace, breaking multi-workspace support. Additionally: system prompt and SKILL.md did not instruct the LLM to pass a meaningful project_name to ensure_project.
fix: (1) ensure_project now queries by project_name before creating, ensuring different requirements get different projects. (2) save_test_cases_batch now does per-case rollback on failure so the session stays clean. (3) multimodal.ts now accepts and forwards spaceId parameter. (4) System prompt and SKILL.md updated to instruct passing meaningful project_name.
verification: Python imports verified OK. TypeScript compilation verified no new errors in changed files. Needs full end-to-end test.
files_changed: [src/app/agents/testcase/tools/db_tools.py, src/app/agents/testcase/agent.py, src/app/skills/output-formatter/SKILL.md, webui/src/app/utils/multimodal.ts, webui/src/app/hooks/useFileUpload.ts]
