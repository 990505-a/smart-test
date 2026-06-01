# Phase 9: Platform Management UI - Context

**Gathered:** 2026-05-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Add frontend management pages for project list, test case editor, folder navigation, and test execution dashboard — transforming the platform from chat-only to a full test management system. The frontend consumes the FastAPI :8000 CRUD endpoints built in Phase 8.

This phase does NOT include Agent-database auto-save integration (Phase 10) or new backend endpoints.

</domain>

<decisions>
## Implementation Decisions

### Routing Architecture
- **D-01:** Next.js App Router file-based routing for management pages.
  - **Why:** Current frontend is single-page (page.tsx only). Phase 9 needs multiple views (chat, projects, cases, runs, folders). App Router gives URL-based navigation, browser history, direct linking, and code splitting. Matches Next.js best practices.
  - **How to apply:** Restructure app/ directory: `app/chat/page.tsx` (chat), `app/projects/page.tsx` (project list), `app/cases/page.tsx` (case editor), `app/runs/page.tsx` (execution dashboard), `app/folders/page.tsx` (folder tree). Root `app/page.tsx` redirects to `/chat`. Shared layout in `app/layout.tsx` with Header and Providers.

- **D-02:** Header remains unified across all pages. Chat page preserves current Agent Tabs + Workspace Selector. Management pages get a "← 返回聊天" link.
  - **Why:** Consistent top navigation. Chat interface is the primary entry point; management pages are secondary. Avoids duplicate header logic.
  - **How to apply:** `app/layout.tsx` contains `<Header />` component. Chat-specific elements (AgentTabs, ThreadList toggle) render conditionally based on route.

### Navigation Layout
- **D-03:** Management pages use left sidebar + right content layout. Left sidebar shows navigation menu (项目列表, 文件夹, 测试执行, 返回聊天).
  - **Why:** Standard management dashboard pattern. Left sidebar provides context and quick navigation. Right content area adapts to each page's needs (table, editor, dashboard).
  - **How to apply:** Create `ManagementLayout` component with flex layout. Left sidebar ~200px fixed width, right content fills remaining space. Use Next.js Link for navigation.

### API Client & Data Layer
- **D-04:** Extend existing SWR pattern for FastAPI :8000 CRUD operations. Use `useSWR` for reads, `useSWRMutation` for create/update/delete.
  - **Why:** SWR already installed and used for thread list. Consistent pattern across the app. No new dependency. `useSWRMutation` handles POST/PATCH/DELETE with automatic cache revalidation.
  - **How to apply:** Create `webui/src/lib/api-client.ts` with base URL `http://localhost:8000/api/v2` from config. Create `webui/src/lib/api/` directory with SWR hooks per entity (useProjects, useFolders, useTestCases, useTestRuns). Use global fetcher with error handling.

- **D-05:** FastAPI base URL configurable via existing ConfigDialog, stored alongside LangGraph URL.
  - **Why:** Deployment URLs vary per environment. Centralized config avoids hardcoded URLs.
  - **How to apply:** Add `fastapiUrl` field to StandaloneConfig in `webui/src/lib/config.ts`. Default `http://localhost:8000`.

### UI Component Selection
- **D-06:** Folder tree: shadcn Collapsible + custom recursive component + @dnd-kit for drag-drop reordering.
  - **Why:** Full style control matching existing UI. shadcn Collapsible already available. @dnd-kit is the leading React drag-drop library (maintained, accessible, performant). No heavy third-party tree library.
  - **How to apply:** Create `FolderTree` component with recursive `FolderTreeNode`. Use @dnd-kit/core + @dnd-kit/sortable for drag-drop. Install `@dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities`.

- **D-07:** Data tables: TanStack Table (Headless) + shadcn Table component for styling.
  - **Why:** Industry-standard headless table library. shadcn/ui official documentation recommends TanStack Table. Supports sorting, filtering, pagination, row selection without UI opinions. Declarative API.
  - **How to apply:** Install `@tanstack/react-table`. Create reusable `DataTable` component following shadcn data table pattern. Use in Projects list, Test Cases list, Test Runs list.

- **D-08:** Charts: recharts for test execution dashboard.
  - **Why:** Most popular React charting library. Declarative API, responsive, composable. Works well with Tailwind/shadcn styling. Simpler than antvis for our use case (bar charts for Pass/Fail, pie for coverage).
  - **How to apply:** Install `recharts`. Create dashboard components in `app/run/` page: PassRateChart, CoverageChart, TrendChart.

### Integration Points
- **D-09:** Workspace ID (space_id) propagates to FastAPI API calls via query parameter or header. Consistent with Phase 7 workspace isolation.
  - **Why:** Phase 7 established workspace isolation for LangGraph. FastAPI Phase 8 supports workspace filtering. Management pages must respect current workspace.
  - **How to apply:** Read current workspace from config/state, include in all FastAPI API calls as `?space_id=xxx` or `X-Space-Id` header.

- **D-10:** Test case editor opens from both project list (click case) and Agent chat (Phase 10 link). Editor is a standalone page `/cases/[id]`.
  - **Why:** Editor needs direct URL access for bookmarking and linking. Phase 10 will add "save to DB" links from chat to editor.
  - **How to apply:** Dynamic route `app/cases/[id]/page.tsx`. Load case data via SWR from FastAPI endpoint.

### Claude's Discretion
- Exact component file structure within each page directory
- shadcn/ui component additions (Dialog, Sheet, DropdownMenu, etc.)
- Form validation library choice (zod vs yup vs native)
- BDD editor mode implementation details
- Pagination component design
- Loading/error state patterns
- Mobile responsiveness level

### Folded Todos
- Phase 7 Plan 07-02 (frontend workspace UI) — user confirmed bugs fixed, workspace selector already works

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Classroom Reference Code
- `d:/test_agent/2026-05-13-ai-test-agent-system-platform/frontend/src/` — Classroom frontend reference (if exists)
- `d:/test_agent/2026-05-13-ai-test-agent-system-platform/backend/app/api/` — Classroom API routes (reference for endpoint patterns)

### Project Planning
- `.planning/REQUIREMENTS.md` — Requirements PLAT-09 through PLAT-13
- `.planning/ROADMAP.md` — Phase 9 details and success criteria
- `.planning/phases/08-fastapi-backend-database/08-CONTEXT.md` — Phase 8 decisions (API endpoints, DB models, file storage)

### Existing Frontend Codebase (MUST reuse)
- `webui/src/app/page.tsx` — Current single-page layout (refactor into chat page)
- `webui/src/app/layout.tsx` — Root layout (extend with shared Header)
- `webui/src/app/components/` — Existing components (ChatInterface, ThreadList, AgentTabs, WorkspaceSelect, ConfigDialog)
- `webui/src/providers/` — ClientProvider, ChatProvider, ThemeProvider
- `webui/src/app/hooks/` — useChat, useThreads, useFileUpload
- `webui/src/lib/config.ts` — StandaloneConfig (add fastapiUrl)
- `webui/src/components/ui/` — shadcn/ui components (Button, Tabs, Switch, etc.)
- `webui/src/app/types/types.ts` — Type definitions

### Phase 8 Backend (API endpoints to consume)
- `src/app/api/v2/projects.py` — 5 endpoints (list, get, create, update, delete)
- `src/app/api/v2/folders.py` — 5 endpoints (list, tree, create, update, delete)
- `src/app/api/v2/test_cases.py` — 5 endpoints (list, get, create, update, delete)
- `src/app/api/v2/test_runs.py` — 6 endpoints (list, get, create, update, add_result, delete)
- `src/app/api/v2/attachments.py` — 4 endpoints (upload, list, download, delete)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Frontend Assets
- `webui/src/app/components/WorkspaceSelect.tsx` — Workspace dropdown (reuse in management pages)
- `webui/src/app/components/ConfigDialog.tsx` — Settings dialog (extend with FastAPI URL)
- `webui/src/lib/config.ts` — Config persistence (extend with fastapiUrl)
- `webui/src/app/hooks/useThreads.ts` — SWR infinite loading pattern (reference for data fetching)
- `webui/src/components/ui/` — All shadcn components available for extension

### Established Frontend Patterns
- **State**: nuqs for URL state, React state for local UI, SWR for server data
- **Providers**: ClientProvider → ChatProvider → Components
- **Theme**: next-themes with light/dark toggle
- **Layout**: flex column (header + content), flex row (sidebar + main)
- **Icons**: lucide-react
- **Notifications**: sonner (Toaster)
- **Styling**: Tailwind CSS 4 + shadcn/ui + CVA

### Phase 8 Backend API Summary
All endpoints under `http://localhost:8000/api/v2/`:
- `GET/POST /projects` — List (paginated) / Create
- `GET/PATCH/DELETE /projects/{id}` — Get / Update / Delete
- `GET/POST /folders` — List / Create (parent_id for hierarchy)
- `GET /folders/tree` — Tree structure
- `GET/PATCH/DELETE /folders/{id}` — Get / Update / Delete
- `GET/POST /test-cases` — List / Create
- `GET/PATCH/DELETE /test-cases/{id}` — Get / Update / Delete
- `GET/POST /test-runs` — List / Create
- `GET/PATCH/DELETE /test-runs/{id}` — Get / Update / Delete
- `POST /test-runs/{id}/results` — Add test result
- `POST /attachments/upload` — Upload file
- `GET/DELETE /attachments/{id}` — Download / Delete

</code_context>

<specifics>
## Specific Ideas

- Follow shadcn/ui data table pattern from official docs for all list views
- Use Next.js loading.tsx and error.tsx for route-level loading/error states
- Create shared `apiClient` wrapper with fetch + error handling + workspace header
- Folder tree uses recursive component with expand/collapse animation
- Test case editor supports both standard (steps table) and BDD (Given/When/Then) modes
- Dashboard uses recharts BarChart for Pass/Fail, PieChart for coverage metrics

</specifics>

<deferred>
## Deferred Ideas

- Agent chat → auto-save to DB (Phase 10)
- Test report visualization with antvis (Phase 10 may revisit)
- Human-in-the-Loop UI interrupts (Phase 10)
- Advanced drag-drop in folder tree (cross-level moves) — basic same-level reorder first
- Real-time test execution updates (WebSocket) — polling first
- Mobile responsive design — desktop-first for management pages
- BDD test case execution mode — BDD editing first, execution later

</deferred>

---

*Phase: 09-platform-management-ui*
*Context gathered: 2026-05-14*
