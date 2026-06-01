---
status: verifying
trigger: "streaming-messages-lost-on-switch-refresh"
created: 2026-05-29T00:00:00Z
updated: 2026-05-29T00:10:00Z
---

## Current Focus

hypothesis: CONFIRMED - Root cause is lack of incremental persistence during streaming.
test: Fix applied, TypeScript compiles clean. Need human to verify in browser.
expecting: Messages will survive page refresh (at least partially) and thread switching.
next_action: Present checkpoint to user for human verification.

## Symptoms

expected: AI streaming output should continue in the background. After refreshing or switching back to thread A, all messages (user question + AI response) should be visible. The experience should be identical to staying on thread A the entire time.
actual: After sending a message in thread A, if the user refreshes the page or switches threads and back, only the user's own message is visible. No AI response is shown at all.
errors: No console errors reported.
reproduction: 1) Open chat, send a message in thread A, 2) While AI is streaming response, refresh page (F5) OR switch to thread B and back to A, 3) Only the user message is visible, no AI response.
started: Started after the per-thread background streaming refactoring of useChat.ts.

## Eliminated

## Evidence

- timestamp: 2026-05-29T00:00:00Z
  checked: useChat.ts sendMessage flow (lines 143-329)
  found: Messages during streaming exist ONLY in streamDataRef (a React useRef). The finally block (lines 287-324) persists to SQLite via saveMessagesToLocalStore ONLY after the stream loop completes. The stream loop is a `for await` on the SSE connection (line 247). If the user refreshes mid-stream, the entire JavaScript context is destroyed, including all refs and the active SSE connection.
  implication: Page refresh during streaming guarantees total loss of all AI output messages. They were never persisted.

- timestamp: 2026-05-29T00:00:00Z
  checked: useChat.ts finally block (lines 296-299)
  found: The saveMessagesToLocalStore call is awaited in the finally block. But the finally block only runs when the `for await` loop exits, which happens when the stream completes or is aborted. There is NO incremental persistence - no messages are saved to SQLite until the ENTIRE stream finishes.
  implication: Even if only the user message were persisted early, the AI partial messages would still be lost on refresh.

- timestamp: 2026-05-29T00:00:00Z
  checked: useChat.ts thread switch behavior (lines 69-73)
  found: There is a comment "No thread switch effects needed - streams run independently per thread" but the code at line 72 reads `streamDataRef.current.get(threadId ?? "")`. When the user switches threads, the `threadId` query param changes, and the component re-renders with the new thread's data. The OLD thread's stream data remains in the ref map, but if the user switches BACK, the mergedMessages logic at line 76-106 will try to merge paginated.messages + activeStreamMessages.
  implication: For the thread switch scenario (without refresh), the stream data SHOULD still be in the ref. Need to verify why switching back doesn't show it.

- timestamp: 2026-05-29T00:00:00Z
  checked: useChat.ts activeStreamMessages calculation (line 72)
  found: `const activeStreamMessages = streamDataRef.current.get(threadId ?? "") ?? [];` - This is computed at render time. When the user switches to thread B and back to A, this line runs with threadId = "A" and should retrieve thread A's stream data from the ref map. The ref should still contain it since the stream is running in the background.
  implication: The ref should contain the data on switch-back. The problem might be in the mergedMessages useMemo or in the stream loop itself aborting when the component re-renders.

## Resolution

root_cause: Two related bugs cause message loss:

  Bug A (Page refresh): Streaming messages exist only in React refs (streamDataRef), which are wiped on page refresh. The only persistence point is the `finally` block after the entire stream completes. No incremental persistence occurs during streaming. If the user refreshes mid-stream, all AI output messages are lost. The paginated API falls back to LangGraph get_state(), which may only contain the user message (input) but not the in-progress AI response.

  Bug B (Thread switch + background completion): When a stream completes in the background while the user is on a different thread, the finally block: (1) saves to SQLite, (2) deletes from streamDataRef, (3) triggers SWR invalidate. But the SWR invalidate uses `revalidate: true` which is async. If the user switches back to thread A before revalidation completes, `activeStreamMessages` is empty (deleted from ref) and `paginated.messages` may still be stale (revalidation pending). This creates a transient gap where no messages are shown.

  Bug C (mergedMessages merge logic): The merge always overwrites paginated messages with stream messages (line 98: `merged.set(msg.id, msg)` unconditionally for existing IDs). But when activeStreamMessages is empty, it returns only paginated.messages. This is correct behavior, but the dependency on `activeStreamMessages` as a useMemo dependency means the reference changes every render (it is not memoized), which could cause unnecessary recalculations.

fix: Applied three changes to useChat.ts:
  1. **Incremental persistence during streaming**: Added periodic saves to SQLite every 15 SSE events or 2 seconds (whichever is slower). Uses fire-and-forget saves that don't block the stream loop. Constants: INCREMENTAL_SAVE_INTERVAL=15, INCREMENTAL_SAVE_MIN_INTERVAL_MS=2000.
  2. **Immediate user message save**: The user's message is saved to SQLite immediately after thread creation/confirmation, before the SSE stream even starts. This ensures the user message is always available from the backend after page refresh.
  3. **Thread switch revalidation**: Added a useEffect that detects threadId changes and calls paginated.mutate() to force SWR revalidation. This handles the case where a stream completed in the background and the user switches back to that thread.
  4. **SWR await in finally**: Changed the SWR global mutate in the finally block to use `await` (was previously fire-and-forget), ensuring the revalidation completes before marking the thread as done.
verification: TypeScript compiles clean (npx tsc --noEmit passes). Need human to verify in browser.
files_changed:
  - webui/src/app/hooks/useChat.ts
