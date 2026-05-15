---
phase: 09-platform-management-ui
plan: 01
subsystem: ui
tags: [next.js, react, typescript, api-client, app-router, routing, shadcn]

# Dependency graph
requires:
  - phase: 08-fastapi-backend-database
    provides: FastAPI CRUD endpoints and Pydantic schemas for projects, folders, test cases, test runs
provides:
  - Multi-page App Router with /chat route and root redirect
  - Shared Header component with navigation links to management pages
  - ManagementLayout with sidebar + content area
  - API client (apiClient) with X-Space-Id header for workspace isolation
  - TypeScript types matching Phase 8 backend Pydantic schemas
  - Extended StandaloneConfig with fastapiUrl field
affects: [09-02, 09-03, 09-04]

# Tech tracking
tech-stack:
  added: ["@tanstack/react-table@8.21.3", "recharts@3.8.1", "@dnd-kit/core@6.3.1", "@dnd-kit/sortable@10.0.0", "@dnd-kit/utilities@3.2.2", "zod@4.4.3"]
  patterns: ["API client with workspace header injection", "Shared Header with active route highlighting", "ManagementLayout sidebar pattern"]

key-files:
  created:
    - webui/src/app/chat/page.tsx
    - webui/src/app/components/Header.tsx
    - webui/src/app/components/ManagementLayout.tsx
    - webui/src/lib/api-client.ts
    - webui/src/app/types/api.ts
    - webui/src/components/ui/table.tsx
    - webui/src/components/ui/card.tsx
    - webui/src/components/ui/breadcrumb.tsx
    - webui/src/components/ui/collapsible.tsx
    - webui/src/components/ui/alert-dialog.tsx
  modified:
    - webui/src/app/page.tsx
    - webui/src/lib/config.ts
    - webui/src/app/components/ConfigDialog.tsx

key-decisions:
  - "Header uses children slot for chat-specific controls (AgentTabs, WorkspaceSelect) instead of separate props"
  - "ThemeToggle extracted into Header component, removing it from chat page"
  - "TestStepResultInfo and TestResultCreate aligned with actual backend schema (step_index not step_number, test_run_id in create)"
  - "TestCaseUpdate includes folder_id and custom_fields fields matching backend schema"

patterns-established:
  - "API client reads config from localStorage on every request for immediate workspace switch reflection"
  - "Management pages use ManagementLayout wrapper; chat page uses Header directly"
  - "Navigation items highlight active route via usePathname() comparison"

requirements-completed: [PLAT-13]

# Metrics
duration: 17min
completed: 2026-05-15
---

# Phase 9 Plan 01: Platform Management UI Foundation Summary

**Multi-page App Router restructure with shared Header/ManagementLayout, FastAPI API client with workspace header, and TypeScript types aligned to Phase 8 backend schemas**

## Performance

- **Duration:** 17 min
- **Started:** 2026-05-15T01:54:22Z
- **Completed:** 2026-05-15T02:11:50Z
- **Tasks:** 2
- **Files modified:** 15

## Accomplishments
- Root URL (/) redirects to /chat; all existing chat functionality preserved
- Shared Header component with navigation links using active route highlighting
- ManagementLayout with sidebar navigation and content area for management pages
- API client with X-Space-Id workspace header, backward-compatible config reading
- TypeScript types precisely aligned with Phase 8 Pydantic backend schemas
- All Phase 9 dependencies installed (@tanstack/react-table, recharts, @dnd-kit, zod)
- Five shadcn UI components added (table, card, breadcrumb, collapsible, alert-dialog)

## Task Commits

Each task was committed atomically:

1. **Task 1: Routing restructure, config extension, and shared components** - `57cc63c` (feat)
2. **Task 2: API client, TypeScript types, and new dependency installation** - `c91f6c9` (feat)

## Files Created/Modified
- `webui/src/app/page.tsx` - Server-side redirect to /chat
- `webui/src/app/chat/page.tsx` - Chat page with full existing functionality, using Header component
- `webui/src/app/components/Header.tsx` - Shared Header with nav links and children slot
- `webui/src/app/components/ManagementLayout.tsx` - Sidebar + content layout for management pages
- `webui/src/lib/config.ts` - Extended StandaloneConfig with fastapiUrl field
- `webui/src/app/components/ConfigDialog.tsx` - Added FastAPI URL input field
- `webui/src/lib/api-client.ts` - API client with workspace header and typed methods
- `webui/src/app/types/api.ts` - TypeScript types matching Phase 8 backend schemas
- `webui/src/components/ui/table.tsx` - Shadcn table component
- `webui/src/components/ui/card.tsx` - Shadcn card component
- `webui/src/components/ui/breadcrumb.tsx` - Shadcn breadcrumb component
- `webui/src/components/ui/collapsible.tsx` - Shadcn collapsible component
- `webui/src/components/ui/alert-dialog.tsx` - Shadcn alert-dialog component

## Decisions Made
- Header uses `children` React slot for chat-specific controls (AgentTabs, WorkspaceSelect, settings buttons) so management pages can leave it empty while chat passes its controls
- ThemeToggle moved from chat page into Header component -- shared across all pages
- TestStepResultInfo aligned with actual backend `test_result.py` schema: uses `step_index` and `test_result_id` (not `step_number`, `action`, `expected_result` as in the plan)
- TestResultCreate includes `test_run_id` field matching the backend schema (plan omitted it)
- TestCaseUpdate includes `folder_id` and `custom_fields` matching the backend `TestCaseUpdate` schema

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Aligned TypeScript types with actual backend schemas**
- **Found during:** Task 2 (TypeScript type creation)
- **Issue:** Plan's `TestStepResultInfo` had fields (`step_number`, `action`, `expected_result`, `actual_result`) that don't match the backend's actual fields (`step_index`, `test_result_id`, `description`). Plan's `TestResultCreate` omitted `test_run_id`. Plan's `TestCaseUpdate` omitted `folder_id` and `custom_fields`.
- **Fix:** Matched TypeScript types to the actual Phase 8 Pydantic schemas in `src/app/db/schemas/`
- **Files modified:** webui/src/app/types/api.ts
- **Verification:** Build succeeds, types match backend schema fields exactly

**2. [Rule 1 - Bug] Removed unused WORKSPACES import from chat page**
- **Found during:** Task 1 (build verification)
- **Issue:** `WORKSPACES` was imported but not used in chat/page.tsx (only `WorkspaceId` needed), causing ESLint warning
- **Fix:** Changed import to `{ WorkspaceId }` only
- **Files modified:** webui/src/app/chat/page.tsx

---

**Total deviations:** 2 auto-fixed (2 bug fixes)
**Impact on plan:** Both auto-fixes improve correctness. Type alignment prevents runtime API mismatches.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Routing structure, API client, and shared components ready for Plans 02-04
- Plan 02 (Project Management) can immediately use apiClient, ManagementLayout, and ProjectInfo types
- Plan 03 (Folder + Test Case views) can use apiClient with FolderInfo/TestCaseInfo types
- Plan 04 (Test Run dashboard) can use apiClient with TestRunInfo/TestResultInfo types and recharts

---
*Phase: 09-platform-management-ui*
*Completed: 2026-05-15*

## Self-Check: PASSED

All 10 key files verified present. Both task commits (57cc63c, c91f6c9) verified in git log.
