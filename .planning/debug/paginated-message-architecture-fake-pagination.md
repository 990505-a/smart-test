---
status: awaiting_human_verify
trigger: "paginated-message-architecture-fake-pagination"
created: 2026-05-28T00:00:00Z
updated: 2026-05-28T00:00:00Z
---

## Current Focus

hypothesis: CONFIRMED AND FIX IMPLEMENTED
test: All backend tests pass (model CRUD, save endpoint, retrieval endpoint, fallback, backfill). Frontend save-on-stream-complete implemented.
expecting: User verifies that the fix works end-to-end in their workflow.
next_action: Request human verification

## Symptoms

expected: Any thread, regardless of size (even 25MB+), should load its message history via paginated API. The user should be able to scroll through all historical messages.
actual: For large threads (25MB+), client.threads.get_state() returns 500 from LangGraph API. Both get_state() AND get_history() fail with 500 for the same large thread. The paginated endpoint is useless for large threads.
errors: LangGraph API returns 500 Internal Server Error when calling get_state() or get_history() on large threads.
reproduction: 1) Run a full agent workflow (5-phase + 6 sub-agents) that creates a large thread, 2) After completion, try to load the thread's messages via the paginated API, 3) Backend calls get_state() which returns 500 from LangGraph API
started: Architecture issue present since the paginated endpoint was created. The "pagination" never actually solved the core problem for large threads.

## Eliminated

- hypothesis: LangGraph API has a partial state loading endpoint
  evidence: Tested all endpoints (get_state, get_state/{checkpoint_id}, history with limit/before). Every endpoint returns the FULL accumulated state at that checkpoint. For a 25MB thread, even checkpoint N-1 would be ~24.9MB. No query parameter limits the state size.
  timestamp: 2026-05-28T00:10:00Z

- hypothesis: Use checkpoint diffing to extract individual messages incrementally
  evidence: While checkpoint diffing works (can identify new messages between consecutive checkpoints), the latest checkpoint still has ALL messages. For large threads, even loading the latest checkpoint via history fails. The history endpoint also returns full state per checkpoint (27 checkpoints = 288KB for a 13-message thread; would be enormous for 500+ messages).
  timestamp: 2026-05-28T00:12:00Z

## Evidence

- timestamp: 2026-05-28T00:00:00Z
  checked: messages.py backend endpoint
  found: The endpoint calls client.threads.get_state(thread_id) which loads FULL state, then slices in Python. This is fake pagination.
  implication: Need to replace get_state() with something that can load partial data or store messages separately.

- timestamp: 2026-05-28T00:00:00Z
  checked: useChat.ts streaming display
  found: SSE event parsing handles messages/partial and messages/complete events correctly (lines 205-248). Event data is already JSON-parsed. Updates streamMessages state via Map-based dedup.
  implication: Issue 2 (streaming display) appears already fixed.

- timestamp: 2026-05-28T00:00:00Z
  checked: messages.ts frontend pagination
  found: Uses [...data].reverse().flatMap() on line 61, which is the correct order (reverse pages first, then flatten).
  implication: Issue 3 (message ordering) appears already fixed.

- timestamp: 2026-05-28T00:05:00Z
  checked: LangGraph API OpenAPI spec at http://localhost:2026/openapi.json
  found: LangGraph API v0.8.7. Thread endpoints: /threads/{id}/state (GET, accepts checkpoint_id, subgraphs), /threads/{id}/history (GET, accepts limit, before), /threads/{id}/state/{checkpoint_id} (GET). Store endpoints: /store/items (PUT, GET, DELETE), /store/items/search (POST).
  implication: No endpoint supports partial state loading. Store API is a separate key-value store, not useful for thread messages.

- timestamp: 2026-05-28T00:08:00Z
  checked: Response sizes for different API calls on thread 019e6e82 (13 messages)
  found: get_state() = 18,712 bytes. history(limit=1) = 18,714 bytes. history(limit=100) = 288,753 bytes (27 checkpoints, each with full accumulated state). state/{early_checkpoint_id} with 1 msg = 1,731 bytes.
  implication: For large threads, EVERY approach that loads the latest checkpoint will fail. The only approach that works is avoiding get_state() entirely for message retrieval.

- timestamp: 2026-05-28T00:12:00Z
  checked: Database infrastructure
  found: SQLite with SQLAlchemy async (aiosqlite). Full model/repo/service pattern exists. Settings use sqlite_db config. init_db() creates all tables on startup. FastAPI app uses lifespan to call init_db().
  implication: Can add a ThreadMessage model to the existing database setup easily.

- timestamp: 2026-05-28T00:14:00Z
  checked: Frontend streaming architecture
  found: Frontend connects directly to LangGraph SDK at deploymentUrl (localhost:2026). ClientProvider wraps the app. useChat.ts calls client.runs.stream() for SSE. After streaming, calls paginated.mutate() to refresh history from backend.
  implication: Frontend has all messages after streaming. Can POST them to backend for storage. This is the cleanest approach that doesn't require a streaming proxy.

## Resolution

root_cause: LangGraph API stores thread state as full snapshots at every checkpoint. get_state() loads the ENTIRE accumulated state (all messages) into memory. For large threads (25MB+), this causes the LangGraph API server itself to return 500 Internal Server Error. The current paginated messages endpoint (messages.py) calls get_state() and then slices in Python -- this is "fake pagination" because the server still loads everything. There is NO LangGraph API endpoint that supports partial state loading.
fix: Implement a local SQLite message store. Frontend POSTs completed messages to backend after streaming. Messages endpoint reads from SQLite instead of calling get_state(). Fallback to get_state() for backward compatibility with threads that existed before this change. Backfill from LangGraph API to SQLite on first access for existing threads.
verification: Tested with real threads (019e6e82 with 13 messages, 019e6e7d with 4 messages). Save endpoint returns correct counts. Retrieval endpoint returns paginated messages in chronological order. Cursor-based pagination works. Structured content (tool_calls, additional_kwargs, name) preserved. Fallback to LangGraph API works for threads without local data. Backfill saves messages to local store on first access.
files_changed:
  - src/app/db/models/thread_message.py (NEW)
  - src/app/db/models/__init__.py (MODIFIED - added ThreadMessage import)
  - src/app/api/v2/messages.py (REWRITTEN - local store + fallback)
  - webui/src/app/hooks/useChat.ts (MODIFIED - added saveMessagesToLocalStore)
