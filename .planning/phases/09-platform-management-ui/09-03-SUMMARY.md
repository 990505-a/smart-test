---
phase: 09-platform-management-ui
plan: 03
subsystem: ui
tags: [next.js, react, swr, @dnd-kit, @tanstack/react-table, shadcn, zod, typescript]

# Dependency graph
requires:
  - phase: 08-fastapi-backend-database
    provides: "FastAPI CRUD API endpoints for folders and test cases"
  - phase: 09-platform-management-ui (plans 01-02)
    provides: "API client, TypeScript types, DataTable, ManagementLayout, SWR hooks pattern"
provides:
  - "Folder tree page at /folders with @dnd-kit drag-drop and CRUD"
  - "Test case list page at /cases with DataTable and pagination"
  - "Test case editor at /cases/[id] with BDD mode toggle"
  - "StepEditor component for test step add/remove/reorder"
  - "SWR hooks for folder and test case CRUD operations"
affects: [09-04, frontend-management-pages]

# Tech tracking
tech-stack:
  added: ["@dnd-kit/core@6.3.1", "@dnd-kit/sortable@10.0.0", "@dnd-kit/utilities@3.2.2", "@tanstack/react-table@8.21.3", "zod@4.4.3", "recharts@3.8.1"]
  patterns: ["SWR mutation with cache revalidation via mutate() matcher", "@dnd-kit same-level SortableContext for hierarchical trees", "zod v4 safeParse with .issues[0].message for validation errors", "CaseDetailForm wrapping StepEditor for standard/BDD mode toggle"]

key-files:
  created:
    - webui/src/lib/api/useFolders.ts
    - webui/src/lib/api/useTestCases.ts
    - webui/src/app/folders/page.tsx
    - webui/src/app/folders/components/FolderTree.tsx
    - webui/src/app/folders/components/FolderTreeNodeItem.tsx
    - webui/src/app/folders/components/CreateFolderDialog.tsx
    - webui/src/app/cases/page.tsx
    - webui/src/app/cases/components/CaseColumns.tsx
    - webui/src/app/cases/components/CreateCaseDialog.tsx
    - webui/src/app/cases/[id]/page.tsx
    - webui/src/app/cases/[id]/components/StepEditor.tsx
    - webui/src/app/cases/[id]/components/CaseDetailForm.tsx
  modified:
    - webui/src/app/types/api.ts

key-decisions:
  - "Added template field to TestCaseUpdate type for BDD/standard mode switching in editor"
  - "Used FolderTreeLevel recursive component with per-level DndContext for same-level reorder only"
  - "Used @base-ui/react render prop pattern instead of asChild for Button+Link composition"
  - "zod v4 uses error.issues (not error.errors) for validation error access"
  - "Created prerequisite infrastructure from plans 09-01/09-02 to resolve parallel execution dependency"

patterns-established:
  - "SWR hooks: useSWRMutation + mutate(key => Array.isArray(key) && key[0] === endpoint) for cache revalidation"
  - "Column definitions: createXxxColumns(onEdit, onDelete) factory pattern for DataTable"
  - "Folder tree flatten: flattenNodes() helper for select dropdown rendering"
  - "BDD toggle: Switch component toggles template between test_case and test_case_bdd"

requirements-completed: [PLAT-10, PLAT-11]

# Metrics
duration: 29min
completed: 2026-05-15
---

# Phase 09 Plan 03: Folder Tree and Test Case Editor Summary

**Folder tree navigation with @dnd-kit same-level drag-drop reordering, and test case editor with standard steps / BDD mode toggle using SWR mutation hooks**

## Performance

- **Duration:** 29 min
- **Started:** 2026-05-15T02:19:26Z
- **Completed:** 2026-05-15T02:48:26Z
- **Tasks:** 2
- **Files modified:** 24

## Accomplishments
- Folder tree page at /folders with hierarchical expand/collapse and @dnd-kit drag-drop for same-level reorder
- Folder CRUD operations (create, edit, delete) with zod-validated dialogs and AlertDialog confirmation
- Test case list page at /cases with TanStack DataTable, project selector, folder filter, and pagination
- Test case editor at /cases/[id] with breadcrumb navigation, step editor (add/remove/reorder), and BDD mode toggle
- Created prerequisite infrastructure from plans 09-01/09-02 (API client, types, layout components, npm dependencies)

## Task Commits

Each task was committed atomically:

1. **Task 1: Folder tree page with @dnd-kit drag-drop and folder CRUD** - `300f950` (feat)
2. **Task 2: Test case list and editor with BDD mode support** - `210171b` (feat)

## Files Created/Modified

### Plan 09-03 task files:
- `webui/src/lib/api/useFolders.ts` - SWR hooks for folder CRUD and tree (useFolderTree, useCreateFolder, useUpdateFolder, useDeleteFolder)
- `webui/src/lib/api/useTestCases.ts` - SWR hooks for test case CRUD with pagination
- `webui/src/app/folders/page.tsx` - Folder management page with project selector and tree
- `webui/src/app/folders/components/FolderTree.tsx` - Recursive tree with @dnd-kit DndContext per level
- `webui/src/app/folders/components/FolderTreeNodeItem.tsx` - Sortable tree node with grip handle, expand/collapse
- `webui/src/app/folders/components/CreateFolderDialog.tsx` - Folder create/edit dialog with zod validation
- `webui/src/app/cases/page.tsx` - Test case list with DataTable, filters, pagination
- `webui/src/app/cases/components/CaseColumns.tsx` - Column definitions with priority/state badges
- `webui/src/app/cases/components/CreateCaseDialog.tsx` - Case create dialog with zod validation
- `webui/src/app/cases/[id]/page.tsx` - Case editor with breadcrumb, uses useParams
- `webui/src/app/cases/[id]/components/StepEditor.tsx` - Step editing with add/remove/auto-numbering
- `webui/src/app/cases/[id]/components/CaseDetailForm.tsx` - Full case form with BDD toggle
- `webui/src/app/types/api.ts` - Added template field to TestCaseUpdate

### Prerequisite files (from plans 09-01/09-02, created to resolve dependency):
- `webui/src/lib/api-client.ts` - API client with X-Space-Id header injection
- `webui/src/app/components/Header.tsx` - Shared navigation header
- `webui/src/app/components/ManagementLayout.tsx` - Sidebar + content layout
- `webui/src/app/components/DataTable.tsx` - Generic TanStack Table component
- `webui/src/lib/api/useProjects.ts` - SWR hooks for project CRUD
- `webui/src/lib/config.ts` - Extended with fastapiUrl field
- `webui/src/app/components/ConfigDialog.tsx` - Added FastAPI URL field
- `webui/src/app/page.tsx` - Root redirect to /chat
- `webui/src/app/chat/page.tsx` - Chat page (moved from root)
- `webui/src/app/projects/page.tsx` - Placeholder project page
- `webui/src/app/runs/page.tsx` - Placeholder runs page

## Decisions Made
- Added `template` field to `TestCaseUpdate` type since the editor allows switching between standard and BDD modes, requiring the backend to persist the template change
- Used recursive `FolderTreeLevel` component instead of flat rendering to enable per-level `DndContext` for same-level reorder isolation (per RESEARCH Pitfall 4)
- Used `@base-ui/react` `render` prop pattern for Button+Link composition since shadcn v4 uses base-ui instead of Radix (no `asChild` support)
- Created all prerequisite infrastructure from plans 09-01 and 09-02 to resolve parallel execution dependency blocking

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Created prerequisite infrastructure from plans 09-01/09-02**
- **Found during:** Pre-execution setup
- **Issue:** Plans 09-01 and 09-02 (dependencies) had not been executed yet in this parallel worktree. Required files (api-client.ts, types/api.ts, DataTable.tsx, ManagementLayout.tsx, useProjects.ts) were missing.
- **Fix:** Created all prerequisite files from plans 09-01/09-02 specifications: API client, TypeScript types, shared components, routing restructure, npm dependencies, and shadcn components
- **Files modified:** 15 additional files beyond plan scope
- **Verification:** Next.js build passes with all routes

**2. [Rule 1 - Bug] Fixed zod v4 error property name**
- **Found during:** Task 1 (CreateFolderDialog build)
- **Issue:** zod v4 uses `error.issues` instead of `error.errors` for accessing validation errors
- **Fix:** Changed `result.error.errors[0].message` to `result.error.issues[0].message`
- **Files modified:** webui/src/app/folders/components/CreateFolderDialog.tsx
- **Committed in:** 300f950

**3. [Rule 1 - Bug] Fixed @base-ui Button asChild incompatibility**
- **Found during:** Task 2 (case detail page build)
- **Issue:** shadcn v4 Button uses @base-ui/react which does not support `asChild` prop
- **Fix:** Replaced `asChild` pattern with `render={<Link href="..." />}` prop pattern
- **Files modified:** webui/src/app/cases/[id]/page.tsx
- **Committed in:** 210171b

**4. [Rule 1 - Bug] Fixed @base-ui Select onValueChange type**
- **Found during:** Task 2 (cases list page build)
- **Issue:** @base-ui/react Select onValueChange passes `string | null`, not `string`
- **Fix:** Changed handler parameter type from `(val: string)` to `(val: string | null)`
- **Files modified:** webui/src/app/cases/page.tsx
- **Committed in:** 210171b

**5. [Rule 2 - Missing Critical] Added template to TestCaseUpdate**
- **Found during:** Task 2 (CaseDetailForm build)
- **Issue:** TestCaseUpdate type lacked `template` field, but the editor supports toggling between standard and BDD modes
- **Fix:** Added `template?: "test_case" | "test_case_bdd"` to TestCaseUpdate interface
- **Files modified:** webui/src/app/types/api.ts
- **Committed in:** 210171b

---

**Total deviations:** 5 auto-fixed (1 missing critical, 2 bugs from library version differences, 1 type fix, 1 blocking dependency)
**Impact on plan:** All auto-fixes necessary for correctness and build success. Prerequisite creation was required for parallel execution.

## Issues Encountered
- zod v4 API differs from v3 (issues vs errors) -- resolved by using correct property name
- @base-ui/react shadcn components use different API than Radix-based components (render prop vs asChild, nullable value changes) -- adapted code to match

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Folder tree and test case editor pages are complete and build successfully
- Plan 09-04 (test run management) can proceed using the same DataTable/SWR/ManagementLayout patterns
- Backend Phase 8 API endpoints must be running for full functionality testing

---
*Phase: 09-platform-management-ui*
*Completed: 2026-05-15*

## Self-Check: PASSED

All 12 plan-specified files verified present. Both task commits (300f950, 210171b) verified in git log. Next.js build passes with all routes (/folders, /cases, /cases/[id]).
