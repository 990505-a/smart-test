---
status: investigating
trigger: "page-refresh-stream-reconnection"
created: 2026-05-29T00:00:00Z
updated: 2026-05-29T00:00:00Z
---

## Current Focus

hypothesis: After page refresh, `activeAgent` query param is NOT in the URL (only `threadId` is), so `activeAgent` defaults to "testcase". The `assistantId` is derived from `activeAgent` and should be present. The reconnect useEffect depends on `[threadId, assistantId]`. Both should be available. The issue is likely that `nuqs` useQueryState("threadId") returns null on first render during SSR/hydration before reading the URL, causing the useEffect to fire with null threadId (bail out), and then when threadId updates, the effect re-fires but something else prevents it from running.
test: Add strategic console.log at the very start of the reconnect useEffect, before any guard conditions, to see if it fires at all after refresh.
expecting: If the useEffect never fires, it's a dependency/render issue. If it fires but bails early, we'll see which guard catches it.
next_action: Trace the exact render sequence of useQueryState("threadId") after page refresh to understand when threadId becomes non-null.

## Symptoms

expected: User refreshes page during AI streaming, frontend reconnects to active run and continues showing streaming output (like ChatGPT behavior).
actual: After refresh, only already-saved messages show (from SQLite paginated load). No streaming reconnection happens. Console has NO [useChat] Reconnect logs and NO errors.
errors: None. No console errors at all.
reproduction: 1. Create new chat 2. Send message, AI starts streaming 3. Press F5 during streaming 4. After refresh, only existing messages visible, no streaming
started: Since reconnect logic was implemented. Thread switching works fine (background streaming normal).

## Eliminated

- hypothesis: Backend API issue (runs.list / runs.joinStream)
  evidence: Python SDK verification confirmed both runs.list() and runs.join_stream() work correctly during active runs.
  timestamp: 2026-05-29T00:00:00Z

## Evidence

- timestamp: 2026-05-29T00:00:00Z
  checked: Reconnect useEffect code in useChat.ts lines 181-321
  found: The useEffect depends on [threadId, assistantId]. Guard: `if (!threadId || !assistantId) return;`. Then checks `abortMapRef.current.has(threadId)`. Then calls `cli.runs.list()`.
  implication: If threadId is null on first render, effect bails immediately. Need to check if threadId is restored from URL.

- timestamp: 2026-05-29T00:00:00Z
  checked: How threadId is restored - useQueryState("threadId") from nuqs
  found: threadId comes from URL query param via nuqs. The chat page is wrapped in Suspense. After refresh, URL still has ?threadId=xxx. nuqs should read it from URL on mount.
  implication: nuqs useQueryState should restore threadId from URL, but timing during Next.js hydration could be an issue.

- timestamp: 2026-05-29T00:00:00Z
  checked: Component hierarchy and data flow for assistantId
  found: ChatPage -> Suspense -> HomePageContent (loads config) -> ClientProvider -> HomePageInner (reads activeAgent from useQueryState("agent")) -> ChatProvider (passes activeAssistant.assistant_id as assistantId) -> useChat. The `agent` query param may NOT be in the URL after refresh if user only had threadId in URL.
  implication: If `agent` param is not in URL, activeAgent defaults to "testcase", which still produces an assistantId. So assistantId should exist.

- timestamp: 2026-05-29T00:00:00Z
  checked: ClientProvider and client creation timing
  found: Client is created via useMemo in ClientProvider, depends on [deploymentUrl, apiKey]. These come from config state which is loaded asynchronously in HomePageContent via useEffect. Until config loads, ClientProvider is NOT rendered at all (HomePageContent returns early with config dialog). This means the client is always available when useChat runs.
  implication: Client should always be available when the reconnect effect runs. Not a timing issue for client.

## Resolution

root_cause:
fix:
verification:
files_changed: []
