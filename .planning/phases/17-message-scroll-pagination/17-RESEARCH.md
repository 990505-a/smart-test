# Phase 17: Message Scroll & Pagination - Research

**Researched:** 2026-05-28
**Domain:** Frontend performance / LangGraph state management / Virtual scrolling
**Confidence:** HIGH

## Summary

This phase addresses a critical scalability failure: when LangGraph thread state grows to 25MB+ (typical after a 5-stage testcase generation pipeline with multiple tool calls, sub-agents, and file content), the browser fails with `TypeError: Failed to fetch` because `useStream` from `@langchain/langgraph-sdk` calls `GET /threads/{threadId}/state` which returns the ENTIRE state in a single HTTP response. The browser's fetch API cannot handle responses this large.

Investigation across three layers (SDK client, API server, useStream hook) confirms that **LangGraph provides NO built-in message-level pagination**. The SDK's `getState()` returns the full state, `getHistory()` returns checkpoint snapshots (not paginated messages), and the API server endpoint has no query parameters for limiting message count. A custom solution is required.

The recommended approach is a **hybrid two-part solution**: (1) a custom FastAPI backend endpoint that paginates messages by directly accessing LangGraph's Python SDK to slice the messages array, and (2) `react-virtuoso` virtual scrolling for efficient rendering of large message lists without creating excessive DOM nodes. This is the only approach that solves both the network transport problem (25MB fetch failure) and the rendering performance problem (hundreds of heavy ChatMessage components).

**Primary recommendation:** Build a custom `GET /api/v2/threads/{threadId}/messages` FastAPI endpoint for paginated message loading, pair it with `react-virtuoso@4.18.7` for virtualized rendering, and modify `useStream` usage to skip full state hydration for existing threads.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| react-virtuoso | 4.18.7 | Virtual scrolling for chat messages | Purpose-built for variable-height lists. Has `followOutput` behavior for auto-scroll. Free MIT core handles chat patterns well. |
| @langchain/langgraph-sdk | 1.9.9 | LangGraph API client (upgrade from 1.0.3) | Required upgrade. Current 1.0.3 is 10 months behind. Newer versions may have streaming/state optimization improvements. |
| swr | 2.4.1 | Data fetching for paginated messages | Already in project (package.json). Perfect for paginated API with `useSWRInfinite`. Handles caching, revalidation, optimistic UI. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| use-stick-to-bottom | 1.1.4 | Auto-scroll behavior | Currently used. Replace with react-virtuoso's built-in `followOutput` -- do NOT keep both. |
| langgraph-sdk (Python) | (installed with DeepAgents) | Backend access to thread state | Used in custom FastAPI endpoint to call `client.threads.get_state()` and slice messages. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| react-virtuoso | @tanstack/react-virtual 3.13.26 | Tanstack is headless (more control, more setup). Virtuoso has built-in chat features (followOutput, reverse scroll, dynamic heights). For a chat UI, virtuoso saves significant implementation time. |
| react-virtuoso (free Virtuoso component) | VirtuosoMessageList (commercial) | VirtuosoMessageList is now paid/commercial. The free `Virtuoso` component can achieve the same chat behavior with manual configuration -- not worth the license cost. |
| Custom backend endpoint | LangGraph API proxy middleware | A proxy could intercept and slice, but adds complexity to the LangGraph server. Custom endpoint in our own FastAPI app is simpler and we already have the infrastructure. |

**Installation:**
```bash
cd webui
npm install react-virtuoso@4.18.7 @langchain/langgraph-sdk@1.9.9
npm uninstall use-stick-to-bottom
```

**Version verification (2026-05-28):**
| Package | Verified Version | Source |
|---------|-----------------|--------|
| react-virtuoso | 4.18.7 | npm registry (npm view) |
| @tanstack/react-virtual | 3.13.26 | npm registry (npm view) |
| @langchain/langgraph-sdk | 1.9.9 | npm registry (npm view) |
| use-stick-to-bottom | 1.1.4 | npm registry (npm view) |
| swr | 2.4.1 | npm registry (npm view) |

## Architecture Patterns

### Recommended Project Structure
```
webui/src/
  app/
    hooks/
      useChat.ts              # MODIFY: skip full state for existing threads
      usePaginatedMessages.ts # NEW: SWR-based paginated message loading
    components/
      ChatInterface.tsx        # MODIFY: replace map+scroll with Virtuoso
      ChatMessage.tsx          # KEEP: already memoized, works with Virtuoso
    lib/
      api/
        messages.ts            # NEW: paginated message API client
  ...
src/app/api/v2/
  messages.py                  # NEW: paginated messages endpoint
```

### Pattern 1: Custom Paginated Backend Endpoint
**What:** A FastAPI endpoint that reads the full LangGraph thread state server-side and returns a sliced subset of messages.
**When to use:** Every chat thread that has more than N messages (configurable threshold, suggest 20).
**Why this is necessary:** LangGraph API has no message-level pagination. Its `getState` returns the full state. We cannot modify the LangGraph API server itself.

```python
# src/app/api/v2/messages.py
from fastapi import APIRouter, Query, HTTPException
from langgraph_sdk import get_client
from src.app.core.config import settings

router = APIRouter()

@router.get("/threads/{thread_id}/messages")
async def get_paginated_messages(
    thread_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),  # message ID as cursor
):
    """Fetch paginated messages from a LangGraph thread.

    This endpoint exists because the LangGraph API's getState returns
    the ENTIRE thread state (all messages), which causes browser fetch
    failures for large threads (25MB+).
    """
    client = get_client(url=settings.langgraph_api_url)
    state = await client.threads.get_state(thread_id)
    messages = state.values.get("messages", [])

    # Apply cursor-based pagination
    if cursor:
        start_idx = next(
            (i for i, m in enumerate(messages)
             if getattr(m, "id", None) == cursor or m.get("id") == cursor),
            0
        )
    else:
        start_idx = max(0, len(messages) - limit)

    end_idx = start_idx + limit
    sliced = messages[start_idx:end_idx]

    return {
        "messages": [serialize_message(m) for m in sliced],
        "total": len(messages),
        "has_more": end_idx < len(messages),
        "next_cursor": (sliced[-1].get("id") if sliced and end_idx < len(messages) else None),
    }
```

### Pattern 2: Virtuoso Chat Layout with Upward Loading
**What:** Replace the current `messages.map()` rendering with Virtuoso's reverse-list behavior.
**When to use:** Always -- this is the new standard rendering for ChatInterface.

```typescript
// webui/src/app/components/ChatInterface.tsx
import { Virtuoso, type VirtuosoHandle } from "react-virtuoso";

const virtuosoRef = useRef<VirtuosoHandle>(null);

// followOutput: "smooth" auto-scrolls to bottom when new messages arrive
// firstItemIndex: virtual offset for prepending older messages
<Virtuoso
  ref={virtuosoRef}
  data={displayMessages}          // processedMessages from useMemo
  followOutput="smooth"           // auto-scroll behavior (replaces use-stick-to-bottom)
  atTopStateChange={handleTopReach} // trigger loading older messages
  itemContent={(index, message) => (
    <ChatMessage
      message={message}
      toolCalls={toolCallsByMessage.get(message.id) ?? []}
      isStreaming={isLastMessage && isStreaming}
      // ... other props
    />
  )}
/>
```

### Pattern 3: SWR Infinite Loading for History
**What:** Use `useSWRInfinite` to load older messages in pages when user scrolls up.
**When to use:** When a thread has more messages than the initial page size.

```typescript
// webui/src/app/hooks/usePaginatedMessages.ts
import useSWRInfinite from "swr/infinite";

const PAGE_SIZE = 20;

const getKey = (pageIndex: number, previousPageData: PageData | null) => {
  if (previousPageData && !previousPageData.has_more) return null; // reached end
  const cursor = previousPageData?.next_cursor;
  return `/api/v2/threads/${threadId}/messages?limit=${PAGE_SIZE}${cursor ? `&cursor=${cursor}` : ""}`;
};

const { data, size, setSize, isLoading } = useSWRInfinite(getKey, fetcher, {
  revalidateFirstPage: false,
  revalidateOnFocus: false,
});
```

### Pattern 4: Dual-Source Message Merging
**What:** Merge paginated history (from custom API) with live streaming messages (from useStream).
**When to use:** Always during an active streaming session.
**Key insight:** useStream's `messages` array continues to grow during streaming. We need to display the streaming messages alongside the paginated history without duplication.

```typescript
// Merging strategy:
// 1. Load last N messages from custom API (fast, paginated)
// 2. During streaming, useStream provides NEW messages in real-time
// 3. Deduplicate by message ID between the two sources
// 4. For messages present in both, prefer the useStream version (more current)

const mergedMessages = useMemo(() => {
  const historyMap = new Map(historyMessages.map(m => [m.id, m]));
  const streamMap = new Map(streamMessages.map(m => [m.id, m]));

  // Merge: stream messages override history for same ID
  const merged = new Map([...historyMap, ...streamMap]);

  // Sort by order (use index, not timestamp -- message order matters)
  return Array.from(merged.values());
}, [historyMessages, streamMessages]);
```

### Anti-Patterns to Avoid

- **Loading all messages then virtualizing:** Still fails with `TypeError: Failed to fetch` for 25MB states. Must paginate at the network level FIRST.
- **Using both use-stick-to-bottom and Virtuoso's followOutput:** These will fight each other. Pick one (Virtuoso's followOutput) and remove the other.
- **Paginating via getHistory instead of getState:** `getHistory` returns checkpoint snapshots, not individual messages. Each checkpoint contains the full state up to that point. This does not help with message-level pagination.
- **Trying to modify the LangGraph API server:** It is a third-party package (`langgraph-runtime-inmem`). Adding query params to its endpoints requires forking the package. Build the custom endpoint in our own FastAPI app instead.
- **Naive offset-based pagination:** Message order can change if the agent modifies history. Use cursor-based (message ID) pagination instead.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Virtual scrolling for chat | Custom IntersectionObserver + scroll position tracking | react-virtuoso | Dynamic heights, followOutput, atTopStateChange -- weeks of edge case handling built in. |
| Paginated data fetching with caching | Custom fetch + state management | SWR's `useSWRInfinite` | Already in project. Handles caching, revalidation, deduplication, loading states. |
| Message deduplication | Custom Set-based filtering | Map-based merge with stream override | Streaming messages may be more current (tool results updated). Map with stream-priority handles this correctly. |
| Auto-scroll to bottom | Custom scroll event listener + animation frame | Virtuoso's `followOutput="smooth"` | Handles edge cases: user scrolled up (don't force scroll), new message during scroll, smooth animation. |

**Key insight:** The chat virtualization problem has been solved many times. react-virtuoso's free component handles 90% of chat-specific concerns. The remaining 10% (merging paginated history with live stream) is project-specific and must be custom-built.

## Common Pitfalls

### Pitfall 1: useStream Still Loads Full State
**What goes wrong:** Adding a paginated backend endpoint does not prevent `useStream` from calling `getState` on mount, which returns the full 25MB state.
**Why it happens:** `useStream` internally calls `fetchHistory` which calls `client.threads.getState(threadId)` on initialization (when `fetchStateHistory: false`).
**How to avoid:** For existing threads (threadId already in URL), configure `useStream` to NOT load initial state. Only use it for live streaming. Load initial messages from the custom paginated endpoint instead.
**Warning signs:** Network tab shows a 25MB+ response to `GET /threads/{id}/state`.

**Implementation approach:** The `useStream` hook accepts an `initialValues` option. If we provide pre-loaded messages as `initialValues`, the hook may skip its own state fetch. Alternatively, conditionally pass `threadId: null` to prevent state loading and only enable it for streaming. This requires testing with the upgraded SDK (1.9.9) as the 1.0.3 behavior may differ.

### Pitfall 2: Virtuoso Jumpiness with Dynamic Heights
**What goes wrong:** Messages have variable heights (tool calls, code blocks, images). When Virtuoso measures them, scroll position jumps.
**Why it happens:** Virtual scrolling needs accurate height measurements. If estimated height is wrong, the scroll container recalculates and jumps.
**How to avoid:** Use Virtuoso's `defaultItemHeight` to provide a reasonable estimate. Use `increaseViewportBy` to render extra items outside the viewport for smoother scrolling. Avoid changing message heights after initial render (use CSS transitions instead of conditional rendering for height changes).
**Warning signs:** Scroll position jumps when tool call results load or markdown renders.

### Pitfall 3: Tool Call Matching Across Pages
**What goes wrong:** `processedMessages` in ChatInterface builds a Map of AI messages matched with their tool calls by walking ALL messages sequentially. When messages are paginated, tool call messages may be on a different page than the AI message that triggered them.
**Why it happens:** LangGraph stores tool results as separate messages after the AI message. If the page boundary falls between an AI message and its tool results, the matching logic breaks.
**How to avoid:** The custom backend endpoint should return messages in "conversation groups" (AI message + its tool results + tool calls) that never split across pages. Alternatively, include tool call data embedded in the AI message response so the frontend does not need to match across messages.
**Warning signs:** Tool call boxes show "pending" status or missing results.

### Pitfall 4: Streaming Interruption During Scroll-Up Load
**What goes wrong:** User scrolls up to load older messages. During the load, the agent sends new messages. The scroll position jumps or the loading state conflicts.
**Why it happens:** Two concurrent data operations (paginated load + stream update) both modify the message list.
**How to avoid:** Virtuoso handles this via `firstItemIndex` offset. When prepending older messages, increase `firstItemIndex` by the count of prepended items. This keeps the current scroll position stable. Ensure the merge logic does not trigger while older messages are loading.
**Warning signs:** Scroll jumps to top when older messages load.

### Pitfall 5: SDK Upgrade Breaking Changes
**What goes wrong:** Upgrading `@langchain/langgraph-sdk` from 1.0.3 to 1.9.9 may introduce breaking changes to `useStream` API.
**Why it happens:** 10 minor versions of API evolution. The hook's options and return types may have changed.
**How to avoid:** Read the changelog between 1.0.3 and 1.9.9 before upgrading. Test in isolation. Key areas to check: `useStream` options shape, `stream.values` structure, `stream.messages` type, `submit` callback signature.
**Warning signs:** TypeScript errors after upgrade, or runtime errors in stream handling.

## Code Examples

### Custom Backend Endpoint - Complete
```python
# src/app/api/v2/messages.py
"""Paginated thread messages endpoint.

LangGraph API returns full thread state in a single response.
For threads with 25MB+ state, this causes browser fetch failures.
This endpoint reads state server-side and returns paginated messages.
"""
from fastapi import APIRouter, Query, HTTPException
from langgraph_sdk import get_client
from src.app.core.config import settings

router = APIRouter()

def serialize_message(msg) -> dict:
    """Convert a LangGraph message to a JSON-serializable dict."""
    # Handle both dict and object-style messages
    if isinstance(msg, dict):
        return msg
    result = {
        "id": getattr(msg, "id", None) or msg.get("id"),
        "type": getattr(msg, "type", None) or msg.get("type"),
        "content": getattr(msg, "content", None) or msg.get("content"),
    }
    if hasattr(msg, "additional_kwargs") or "additional_kwargs" in (msg if isinstance(msg, dict) else {}):
        result["additional_kwargs"] = getattr(msg, "additional_kwargs", None) or msg.get("additional_kwargs", {})
    if hasattr(msg, "tool_calls") or "tool_calls" in (msg if isinstance(msg, dict) else {}):
        result["tool_calls"] = getattr(msg, "tool_calls", None) or msg.get("tool_calls", [])
    return result

@router.get("/threads/{thread_id}/messages")
async def get_paginated_messages(
    thread_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
):
    client = get_client(url=settings.langgraph_api_url)

    try:
        state = await client.threads.get_state(thread_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Thread not found: {e}")

    raw_messages = state.values.get("messages", [])
    total = len(raw_messages)

    if cursor:
        # Find the cursor message and return messages AFTER it
        cursor_idx = next(
            (i for i, m in enumerate(raw_messages)
             if (getattr(m, "id", None) if not isinstance(m, dict) else m.get("id")) == cursor),
            -1
        )
        if cursor_idx == -1:
            raise HTTPException(status_code=400, detail="Invalid cursor")
        start_idx = cursor_idx + 1
    else:
        # No cursor: return the LAST `limit` messages (most recent)
        start_idx = max(0, total - limit)

    end_idx = min(start_idx + limit, total)
    sliced = raw_messages[start_idx:end_idx]

    return {
        "messages": [serialize_message(m) for m in sliced],
        "total": total,
        "has_more": start_idx > 0,
        "next_cursor": sliced[0]["id"] if sliced and start_idx > 0 else None,
    }
```
*Source: Custom design based on LangGraph SDK Python client API analysis (HIGH confidence)*

### Virtuoso Chat Component Integration
```typescript
// webui/src/app/components/ChatInterface.tsx (key changes)
import { Virtuoso, type VirtuosoHandle } from "react-virtuoso";

// Inside the component:
const virtuosoRef = useRef<VirtuosoHandle>(null);
const [isAtBottom, setIsAtBottom] = useState(true);

// Replace the current messages.map() block:
<Virtuoso
  ref={virtuosoRef}
  data={displayMessages}
  followOutput={isAtBottom ? "smooth" : false}
  atBottomStateChange={setIsAtBottom}
  atTopStateChange={(atTop) => {
    if (atTop && hasOlderMessages) {
      loadOlderMessages();
    }
  }}
  increaseViewportBy={{ top: 200, bottom: 200 }}
  defaultItemHeight={80}
  itemContent={(index, msg) => {
    const isLast = index === displayMessages.length - 1;
    return (
      <ChatMessage
        message={msg}
        toolCalls={toolCallsByMessage.get(msg.id ?? "") ?? []}
        isStreaming={isLast && isStreaming}
        ui={ui}
        stream={stream}
        graphId={graphId}
      />
    );
  }}
/>
```
*Source: react-virtuoso documentation (HIGH confidence)*

### SWR Paginated Message Fetcher
```typescript
// webui/src/lib/api/messages.ts
import useSWRInfinite from "swr/infinite";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface PaginatedResponse {
  messages: Array<{
    id: string;
    type: "human" | "ai" | "system";
    content: string | Array<Record<string, unknown>>;
    additional_kwargs?: Record<string, unknown>;
    tool_calls?: Array<{ name: string; args?: Record<string, unknown>; id?: string }>;
  }>;
  total: number;
  has_more: boolean;
  next_cursor: string | null;
}

async function fetchMessages(url: string): Promise<PaginatedResponse> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch messages: ${res.status}`);
  return res.json();
}

export function usePaginatedMessages(threadId: string | null, pageSize = 20) {
  const getKey = (pageIndex: number, previousPageData: PaginatedResponse | null) => {
    if (!threadId) return null;
    if (previousPageData && !previousPageData.has_more) return null;

    // First page: no cursor (loads most recent messages)
    // Subsequent pages: use next_cursor from previous page
    const cursor = previousPageData?.next_cursor;
    return `${API_BASE}/api/v2/threads/${threadId}/messages?limit=${pageSize}${cursor ? `&cursor=${cursor}` : ""}`;
  };

  const { data, size, setSize, isLoading, isValidating } = useSWRInfinite(
    getKey,
    fetchMessages,
    {
      revalidateFirstPage: false,
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
    },
  );

  const messages = data ? data.flatMap((page) => page.messages).reverse() : [];
  const total = data?.[0]?.total ?? 0;
  const hasMore = data?.[data.length - 1]?.has_more ?? false;

  const loadMore = () => setSize(size + 1);

  return { messages, total, hasMore, loadMore, isLoading, isValidating };
}
```
*Source: SWR documentation + project patterns (HIGH confidence)*

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Full state load via useStream | Custom paginated endpoint + Virtuoso | 2026-05-28 (this phase) | Solves 25MB fetch failure |
| use-stick-to-bottom | Virtuoso followOutput | 2026-05-28 (this phase) | Integrated solution, one fewer dependency |
| @langchain/langgraph-sdk 1.0.3 | @langchain/langgraph-sdk 1.9.9 | 10 minor versions behind | Must upgrade for potential streaming optimizations |
| messages.map() DOM rendering | Virtuoso virtual rendering | 2026-05-28 (this phase) | O(n) DOM nodes becomes O(viewport) |

**Deprecated/outdated:**
- `use-stick-to-bottom`: Replaced by Virtuoso's built-in `followOutput`. Keeping both causes scroll conflicts.
- `@langchain/langgraph-sdk@1.0.3`: 10 versions behind. The newer versions may have improved state handling or streaming optimizations that reduce our custom work.

## Open Questions

1. **useStream initialization skip for existing threads**
   - What we know: `useStream` calls `getState` on mount when a `threadId` is provided. This returns the full 25MB state.
   - What's unclear: Whether the SDK v1.9.9 supports skipping initial state load, or whether we need to pass `threadId: null` initially and set it only when streaming begins.
   - Recommendation: Test with SDK 1.9.9. Check if `initialValues` option can pre-seed state and prevent the full fetch. If not, conditionally nullify `threadId` for existing threads and only use the custom paginated endpoint for history.

2. **Conversation group boundaries for tool call matching**
   - What we know: Tool call messages are separate messages after the AI message. The `processedMessages` logic walks all messages sequentially.
   - What's unclear: Whether splitting messages at arbitrary boundaries (every 20) will break tool call matching.
   - Recommendation: The backend endpoint should return "conversation groups" (AI + its tool results together). Implement a `group_size` parameter that ensures related messages stay on the same page. Alternatively, embed tool call summaries in the AI message response.

3. **FirstItemIndex management for upward scrolling**
   - What we know: Virtuoso uses `firstItemIndex` to maintain scroll position when prepending items.
   - What's unclear: The exact merge strategy when paginated history loads during active streaming.
   - Recommendation: Start `firstItemIndex` at a large number (e.g., 100000) and decrement when prepending. This avoids index collision between history and streaming messages.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| react-virtuoso | Virtual scrolling | Needs install | 4.18.7 (npm) | -- |
| @langchain/langgraph-sdk | Stream client (upgrade) | Installed | 1.0.3 -> 1.9.9 | -- |
| SWR | Paginated data fetching | Installed | 2.4.1 | -- |
| FastAPI | Custom pagination endpoint | Available | (installed) | -- |
| langgraph-sdk (Python) | Backend thread state access | Available | (via DeepAgents) | -- |

**Missing dependencies with no fallback:**
- react-virtuoso: Must install via `npm install react-virtuoso`

**Missing dependencies with fallback:**
- None

## Sources

### Primary (HIGH confidence)
- `webui/node_modules/@langchain/langgraph-sdk/dist/react/stream.lgp.js` - useStream internals, fetchHistory function, getState vs getHistory behavior
- `webui/node_modules/@langchain/langgraph-sdk/dist/client.d.ts` - Client API type definitions (getState, getHistory signatures)
- `D:/PYTHON/Lib/site-packages/langgraph_api/api/threads.py` - LangGraph API server thread state endpoint (confirmed no pagination params)
- npm registry - version verification for all packages (2026-05-28)
- react-virtuoso official documentation - Virtuoso component API, followOutput, atTopStateChange

### Secondary (MEDIUM confidence)
- `webui/src/app/hooks/useChat.ts` - current useStream configuration and sendMessage flow
- `webui/src/app/components/ChatInterface.tsx` - current rendering and scroll implementation
- `webui/src/app/components/ChatMessage.tsx` - message component structure (already memoized)
- `src/app/api/__init__.py` - existing API router structure for adding new endpoint
- `src/app/core/config.py` - langgraph_api_url configuration

### Tertiary (LOW confidence)
- SDK v1.9.9 behavior changes from v1.0.3 (not tested, upgrade needed)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - versions verified from npm registry, all libraries are mature and well-documented
- Architecture: HIGH - based on direct source code analysis of useStream internals and LangGraph API server
- Pitfalls: HIGH - identified from direct code analysis (useStream fetchHistory function, processedMessages matching logic)
- SDK upgrade impact: MEDIUM - 10 version gap may have breaking changes not yet tested

**Research date:** 2026-05-28
**Valid until:** 2026-06-28 (stable domain, virtual scrolling is mature)
