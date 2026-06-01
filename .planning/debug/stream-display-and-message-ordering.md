---
status: verifying
trigger: "stream-display-and-message-ordering: streaming output doesn't display in real-time, page goes blank, wrong message ordering after refresh"
created: 2026-05-28T00:00:00Z
updated: 2026-05-28T00:03:00Z
---

## Current Focus

hypothesis: CONFIRMED - Two root causes found. (1) SSE event parsing logic completely mismatched with LangGraph SDK event format - code treats Message[] as [event_type, data] tuple, silently losing all messages during streaming. (2) After streaming ends and paginated data is reloaded, messages may be ordered incorrectly due to Map insertion order vs chronological order.
test: Trace the exact SSE event format through the SDK code
expecting: Events from streamMode:"messages" have structure {event: "messages/partial", data: Message[]}, but code does Array.isArray -> [,data]=parsed which destructures the Message array incorrectly
next_action: Implement fix for both issues

## Symptoms

expected: After sending a message, the agent's streaming response should appear token-by-token in real-time. Messages should be ordered chronologically: user question first, then agent answer below it.
actual: When user sends a message, the page goes blank during streaming. User must manually refresh the page to see the agent's output. After refresh, the agent's response appears ABOVE the user's question instead of below it.
errors: No explicit console errors reported. Page goes blank during streaming and shows wrong ordering after refresh.
reproduction: 1) Open chat UI, 2) Send any message, 3) Observe page goes blank/empty, 4) Wait for agent to finish, 5) Refresh page - agent answer appears before user question.
started: Started immediately after the useChat.ts rewrite that replaced useStream with client.runs.stream() + usePaginatedMessages. Never worked correctly with the new architecture.

## Eliminated

## Evidence

- timestamp: 2026-05-28T00:00:00Z
  checked: Read all 4 key files (useChat.ts, messages.ts, ChatInterface.tsx, messages.py)
  found: >
    useChat.ts lines 79-101: mergedMessages useMemo uses Map keyed by message ID.
    Map preserves insertion order: paginated messages inserted first, then streamMessages.
    If paginated.messages is empty during streaming (new thread, no API call yet), only streamMessages appear.
    The merge logic looks correct IF both sources produce messages with correct IDs.
  implication: The bug is likely in the SSE event parsing or in how paginated messages interact with streaming.

- timestamp: 2026-05-28T00:01:00Z
  checked: LangGraph SDK v1.9.9 SSE event format - traced through SSEDecoder, streamWithRetry, types.stream.d.ts
  found: >
    The SSEDecoder in utils/sse.js already parses JSON from SSE data fields (line 74: decodeArraysToJson).
    So event.data is ALREADY a parsed object, not a string.

    For streamMode:"messages", the SDK yields MessagesStreamEvent objects with structure:
    - { event: "messages/partial", data: Message[] }  -- incremental message updates
    - { event: "messages/complete", data: Message[] } -- final complete messages
    - { event: "messages/metadata", data: {[id]: {metadata}} } -- metadata

    The useChat.ts parsing code (lines 193-229) does:
    1. eventData = event.data (already a parsed object)
    2. parsed = typeof eventData === "string" ? JSON.parse(eventData) : eventData (takes else branch, parsed = eventData)
    3. Array.isArray(parsed) -> TRUE for Message[] data from partial/complete events
    4. const [, data] = parsed -> DESTRUCTURES the Message array! Takes index 1 (second Message), skips first
    5. Checks data.id && data.type -> For single-message events, data is undefined, SILENTLY FAILS

    This means streaming messages are NEVER correctly added to streamMessages during streaming.
    Only the optimistic human message (added at line 164) exists in streamMessages.
  implication: >
    BUG 1 (blank page during streaming): The event parsing is completely wrong for the actual format.
    All streaming messages from the agent are silently dropped. Only the optimistic human message exists.
    When the agent starts processing, the page likely shows only the human message, and any
    intermediate state changes cause the display to go blank or show stale data.

- timestamp: 2026-05-28T00:02:00Z
  checked: Post-refresh message ordering (messages.py + messages.ts)
  found: >
    After refresh, messages come from the paginated API (messages.py).
    The API returns messages in chronological order from LangGraph state.
    The usePaginatedMessages hook (messages.ts line 60-62) does:
    [...data.flatMap(page => page?.messages ?? []).filter(Boolean)].reverse()
    This reverses the flattened pages to get chronological order.

    The messages.py backend uses _serialize_message which preserves original order from state.
    The API returns messages oldest-first within each page, pages newest-first.
    The .reverse() should produce correct chronological order.

    However, looking at the backend (line 263-264):
    state_values = state.get("values", {})
    raw_messages = state_values.get("messages", []) if isinstance(state_values, dict) else []

    This correctly accesses state.values.messages via state.get("values", {}).get("messages", []).
    This was already fixed from the original bug mentioned in known_context.
  implication: >
    BUG 2 (wrong ordering after refresh): After investigation, the ordering logic looks correct in theory.
    The actual ordering issue might be caused by how the backend serializes messages or by the
    streamMessages overriding paginated ones in the merge with wrong data. Need to verify with
    actual API response. But the primary fix should be BUG 1 first - if streaming works correctly,
    the refresh ordering issue may be less visible or may be a separate pagination edge case.

    UPDATE on BUG 2: After deeper analysis, the ordering issue is likely a secondary symptom.
    When streaming fails and user refreshes, the paginated API loads fresh data correctly ordered.
    The user might be confused by the display ordering if the ChatInterface processesMessages
    function doesn't properly handle tool messages. But the core data from the API should be ordered correctly.

## Resolution

root_cause: >
  BUG 1 (primary - blank page during streaming): The SSE event parsing in useChat.ts (lines 193-229)
  is completely mismatched with the LangGraph SDK v1.9.9 event format for streamMode:"messages".
  The code assumes events come as [event_type, data] tuples, but the SDK yields objects with
  {event: "messages/partial"|"messages/complete"|"messages/metadata", data: Message[]}.
  The Array.isArray check + destructuring as [, data] = parsed treats Message objects as tuple
  elements, silently losing all agent streaming output.

  BUG 2 (secondary - ordering after refresh): The mergedMessages Map uses insertion order.
  When paginated messages are loaded after streaming ends, the Map merge first inserts paginated
  (oldest to newest) then streaming messages override by ID. If a streaming message has a different
  ID format than the paginated one, duplicates could appear out of order. This needs investigation
  but is secondary to BUG 1.
fix: >
  1. Rewrote the SSE event parsing loop to dispatch based on event.event type:
     - "messages/partial" and "messages/complete": iterate over Message[] in event.data
     - "metadata": extract thread_id from event.data
     - "error": log to console
     Removed the incorrect [event_type, data] tuple destructuring.

  2. Rewrote the mergedMessages useMemo to use an ordered ID array + Map pattern
     that preserves stable chronological ordering. Paginated messages establish
     the initial order, streaming messages update in-place or append at the end.

  TypeScript compilation passes with zero errors.
verification: TypeScript compiles cleanly. Needs manual testing in browser.
files_changed: [webui/src/app/hooks/useChat.ts]
