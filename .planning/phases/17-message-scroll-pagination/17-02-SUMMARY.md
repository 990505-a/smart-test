---
phase: 17-message-scroll-pagination
plan: 02
subsystem: ui
tags: [virtual-scroll, react-virtuoso, paginated-messages, dual-source-merge, useStream]

# Dependency graph
requires:
  - phase: 17-01
    provides: "usePaginatedMessages hook, PaginatedMessage types, react-virtuoso package"
provides:
  - "useChat with paginated message loading and dual-source merge"
  - "ChatInterface with Virtuoso virtual scroll and load-more-on-scroll-up"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns: [dual-source-merge, threadId-null-prevention, virtuoso-followOutput]

key-files:
  created: []
  modified:
    - webui/src/app/hooks/useChat.ts
    - webui/src/app/components/ChatInterface.tsx

key-decisions:
  - "Pass threadId:null to useStream to prevent getState fetch for existing threads; set threadId via setThreadId before submit"
  - "Virtuoso replaces manual scroll management with followOutput and atTopStateChange for auto-scroll and load-more"

patterns-established:
  - "Dual-source merge: paginated messages as base map, streaming messages override by id"
  - "Virtuoso virtual scroll with followOutput='smooth' when at bottom, false when scrolled up"

requirements-completed: [MSG-PAG-04, MSG-PAG-05, MSG-PAG-06]

# Metrics
duration: 5min
completed: 2026-05-28
---

# Phase 17 Plan 02: Frontend UI Wiring Summary

**Dual-source message merge with Virtuoso virtual scroll -- existing threads load only 20 messages, no 25MB+ state fetch**

## Performance

- **Duration:** 5 min
- **Started:** 2026-05-28T09:11:44Z
- **Completed:** 2026-05-28T09:17:20Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- useChat hook uses usePaginatedMessages for existing thread history, avoiding full state fetch
- Dual-source merge: paginated messages as base, streaming messages override during active runs
- useStream receives threadId:null to prevent getState loading, threadId set before submit
- ChatInterface uses Virtuoso for virtual scrolling with load-more-on-scroll-up
- Loading indicator shown when fetching older messages
- Auto-scroll to bottom during streaming with followOutput, paused when user scrolls up

## Task Commits

Each task was committed atomically:

1. **Task 1: Modify useChat for paginated loading** - `e7b9ef0` (feat)
2. **Task 2: Replace ChatInterface rendering with Virtuoso** - `acf74ae` (feat)

## Files Created/Modified
- `webui/src/app/hooks/useChat.ts` - Added usePaginatedMessages import, dual-source merge logic, threadId:null to useStream, new return values (isLoadingHistory, hasOlderMessages, loadOlderMessages)
- `webui/src/app/components/ChatInterface.tsx` - Replaced scroll refs and manual auto-scroll with Virtuoso component, added atTopStateChange for load-more, loading indicator header

## Decisions Made
- Pass `threadId: null` to useStream instead of the real threadId. This prevents useStream from calling `client.threads.getState()` which fetches the full 25MB+ thread state. Before submitting, `setThreadId(realThreadId)` is called so useStream's submit function uses the correct thread.
- Virtuoso `followOutput="smooth"` when `isAtBottom` is true provides smooth auto-scroll during streaming; set to `false` when user scrolls up so new messages don't force scroll.
- Empty state (no messages) rendered outside Virtuoso to avoid rendering Virtuoso with zero items.

## Deviations from Plan

None - plan executed exactly as written.

## Next Phase Readiness
- Task 3 (human-verify checkpoint) requires manual testing of all 8 scenarios
- Backend must be running for verification: `python -m src.app.main`
- Frontend must be running: `cd webui && npm run dev`
- Test scenarios: new chat streaming, existing thread paginated load, scroll-up history, streaming+scroll interaction, tool call display

## Self-Check: PASSED

- webui/src/app/hooks/useChat.ts: FOUND
- webui/src/app/components/ChatInterface.tsx: FOUND
- Commit e7b9ef0 (Task 1): FOUND
- Commit acf74ae (Task 2): FOUND

---
*Phase: 17-message-scroll-pagination*
*Completed: 2026-05-28*
