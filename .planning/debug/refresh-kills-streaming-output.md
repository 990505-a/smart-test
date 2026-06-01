---
status: verifying
trigger: "refresh-kills-streaming-output"
created: 2026-05-29T00:00:00Z
updated: 2026-05-29T00:40:00Z
---

## Current Focus

hypothesis: CONFIRMED - Root cause is missing reconnection after page refresh. Fix implemented using runs.joinStream API.
test: TypeScript compiles clean. Need human to verify in browser.
expecting: After F5 refresh during streaming, the page detects the active run and reconnects, continuing to show AI output.
next_action: Present checkpoint to user for human verification.

## Symptoms

expected: Refresh page during AI streaming output, AI streaming should continue (like ChatGPT).
actual: Refresh page during streaming, only saved messages shown, AI output stops completely.
errors: No console errors.
reproduction: 1) Send message, 2) AI starts streaming, 3) Press F5, 4) Only existing messages shown, no more streaming.
started: Since removing useStream in favor of client.runs.stream().

## Eliminated

## Evidence

- timestamp: 2026-05-29T00:01:00Z
  checked: useChat.ts sendMessage flow
  found: sendMessage creates a new run via client.runs.stream() (line 278-293). This is a one-shot SSE connection that creates a new run AND streams its output. When page refreshes, the JS context (streamDataRef, abortMapRef) is destroyed. There is no reconnection logic anywhere in the hook.
  implication: The root cause is architectural - no reconnection mechanism exists.

- timestamp: 2026-05-29T00:05:00Z
  checked: LangGraph SDK client runs API (node_modules/@langchain/langgraph-sdk/dist/client/runs/index.d.ts)
  found: SDK provides three key APIs for reconnection:
    1. `client.threads.getState(threadId)` - Returns ThreadState with `next` field (non-empty = active run)
    2. `client.runs.list(threadId, {status: "running"})` - Lists runs, can filter by status
    3. `client.runs.joinStream(threadId, runId, {streamMode: "messages"})` - Reconnects to an ACTIVE run's stream via GET /threads/{threadId}/runs/{runId}/stream
    4. `client.threads.joinStream(threadId, {streamMode: "messages"})` - Thread-level join (GET /threads/{threadId}/stream)
  implication: The SDK DOES support reconnection via joinStream. The fix is to use these APIs.

- timestamp: 2026-05-29T00:10:00Z
  checked: LangGraph API thread status
  found: Thread search returns `status` field: "idle" | "busy" | "interrupted" | "error". A thread with status="busy" has an active run. We can also check ThreadState.next (non-empty array = run in progress).
  implication: We can detect active runs by checking thread status or getState.

- timestamp: 2026-05-29T00:15:00Z
  checked: Thread state size concern
  found: Thread states can be 167KB+ (observed). But we don't need to load the full state - we only need `next` field from getState, or even simpler, just check thread.status from threads.search(). The runs.list() API can find the specific run_id with status filter.
  implication: We can detect active runs WITHOUT loading the full thread state.

- timestamp: 2026-05-29T00:18:00Z
  checked: threads.joinStream vs runs.joinStream
  found: `threads.joinStream(threadId)` hits GET /threads/{threadId}/stream - thread-level stream. `runs.joinStream(threadId, runId)` hits GET /threads/{threadId}/runs/{runId}/stream - run-specific stream. Both use the same streamWithRetry generator, so event format is identical to runs.stream().
  implication: runs.joinStream is the right API for reconnecting to a specific active run.

- timestamp: 2026-05-29T00:20:00Z
  checked: runs.list API with status filter
  found: GET /threads/{threadId}/runs?status=running returns empty array [] for idle threads. The SDK passes status param directly. API returns runs with matching status only.
  implication: runs.list with status="running" is a lightweight way to detect active runs.

- timestamp: 2026-05-29T00:25:00Z
  checked: Race condition between sendMessage and reconnection useEffect
  found: When sendMessage creates a new thread and calls setThreadId(), the reconnection useEffect will fire. But sendMessage registers the thread in abortMapRef (line 380/414) BEFORE the stream starts. The reconnection checks abortMapRef.current.has(threadId) and skips if sendMessage is already streaming.
  implication: Race condition is handled via abortMapRef guard.

- timestamp: 2026-05-29T00:30:00Z
  checked: useEffect dependency optimization
  found: paginated object changes every render (from useSWRInfinite return). If included in dependency array, useEffect would run every render, making unnecessary API calls. Used reconnectDepsRef pattern to access unstable deps via ref while only depending on [threadId, assistantId].
  implication: Reconnection only triggers when threadId or assistantId changes.

## Resolution

root_cause: Page refresh destroys all frontend JS state (React refs for streaming data, SSE connections, abort controllers). Unlike the old useStream hook which had built-in reconnection, the current client.runs.stream() implementation is fire-and-forget with no recovery mechanism. LangGraph SDK provides reconnection APIs (runs.joinStream, runs.list) but they were not used.
fix: Added reconnection logic in useChat hook (lines 175-316):
  1. useEffect triggered on threadId/assistantId change
  2. Calls client.runs.list(threadId, {status: "running"}) to find active runs
  3. If active run found, calls client.runs.joinStream(threadId, runId, {streamMode: "messages"}) to reconnect
  4. Processes events identically to sendMessage's stream loop (messages/partial, messages/complete)
  5. Includes incremental persistence and all the same cleanup logic
  6. Race condition protection: skips reconnection if abortMapRef shows sendMessage is already streaming
  7. Dependency optimization: uses ref pattern to avoid re-running on every render
verification: TypeScript compiles clean. Need human to verify in browser.
files_changed:
  - webui/src/app/hooks/useChat.ts
