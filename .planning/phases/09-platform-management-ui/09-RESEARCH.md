# Phase 9: Platform Management UI - Research

**Researched:** 2026-05-14
**Domain:** Next.js 15 multi-page routing, SWR CRUD, TanStack Table, recharts, @dnd-kit
**Confidence:** HIGH

## Summary

Phase 9 transforms the existing single-page chat-only frontend (`webui/src/app/page.tsx`) into a multi-page test management system. The frontend will consume the FastAPI :8000 CRUD endpoints built in Phase 8. The existing codebase uses Next.js 15.4.4, React 19, Tailwind CSS 4, shadcn/ui, SWR 2.4, and nuqs 2.8 -- all of which remain in place and are extended.

The core refactoring challenge is moving from a single `app/page.tsx` to an App Router multi-page structure (`/chat`, `/projects`, `/cases/[id]`, `/runs`, `/folders`) while preserving the existing ChatProvider, ClientProvider, and chat components untouched. The new pages add CRUD data management via SWR hooks, a reusable DataTable component (TanStack Table + shadcn), a folder tree with drag-drop (@dnd-kit), a test case editor supporting both standard and BDD modes, and an execution dashboard (recharts).

All new libraries (TanStack Table 8.21, recharts 3.8, @dnd-kit/core 6.3, @dnd-kit/sortable 10) are verified compatible with React 19. No version conflicts exist.

**Primary recommendation:** Restructure to App Router pages first, then build a shared API client layer, then implement pages incrementally (projects list, folder tree, case editor, run dashboard).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Next.js App Router file-based routing: `app/chat/page.tsx`, `app/projects/page.tsx`, `app/cases/page.tsx`, `app/runs/page.tsx`, `app/folders/page.tsx`. Root `app/page.tsx` redirects to `/chat`.
- **D-02:** Header unified across all pages. Chat page preserves Agent Tabs + Workspace Selector. Management pages get a "return to chat" link.
- **D-03:** Management pages use left sidebar + right content layout. Left sidebar ~200px fixed, shows navigation menu.
- **D-04:** Extend existing SWR pattern for FastAPI CRUD. Use `useSWR` for reads, `useSWRMutation` for create/update/delete. Create `webui/src/lib/api-client.ts` and `webui/src/lib/api/` directory.
- **D-05:** FastAPI base URL configurable via existing ConfigDialog, stored alongside LangGraph URL. Add `fastapiUrl` to StandaloneConfig.
- **D-06:** Folder tree: shadcn Collapsible + custom recursive component + @dnd-kit for drag-drop. Install `@dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities`.
- **D-07:** Data tables: TanStack Table (Headless) + shadcn Table component. Create reusable `DataTable` component.
- **D-08:** Charts: recharts for test execution dashboard. BarChart for Pass/Fail, PieChart for coverage, TrendChart.
- **D-09:** Workspace ID propagates to FastAPI API calls via query parameter or header. Consistent with Phase 7.
- **D-10:** Test case editor is standalone page `/cases/[id]`. Dynamic route with SWR data loading.

### Claude's Discretion
- Exact component file structure within each page directory
- shadcn/ui component additions (Dialog, Sheet, DropdownMenu, etc.)
- Form validation library choice (zod vs yup vs native)
- BDD editor mode implementation details
- Pagination component design
- Loading/error state patterns
- Mobile responsiveness level

### Deferred Ideas (OUT OF SCOPE)
- Agent chat to auto-save to DB (Phase 10)
- Test report visualization with antvis (Phase 10 may revisit)
- Human-in-the-Loop UI interrupts (Phase 10)
- Advanced drag-drop in folder tree (cross-level moves) -- basic same-level reorder first
- Real-time test execution updates (WebSocket) -- polling first
- Mobile responsive design -- desktop-first for management pages
- BDD test case execution mode -- BDD editing first, execution later
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PLAT-09 | Project list page (create/edit/delete projects, project card display) | SWR CRUD hooks (useProjects), TanStack Table DataTable component, shadcn Dialog for create/edit forms |
| PLAT-10 | Folder navigation component (tree structure, drag-drop reorder, expand/collapse) | @dnd-kit sortable for drag-drop, shadcn Collapsible for expand/collapse, recursive FolderTreeNode component |
| PLAT-11 | Test case editor (step editing, expected results, priority, BDD mode) | Dynamic route `/cases/[id]`, SWR useTestCase hook, step editor component with add/remove/reorder, BDD Given/When/Then template |
| PLAT-12 | Test execution dashboard (run history, Pass/Fail statistics, results detail) | recharts BarChart/PieChart, SWR useTestRuns hook, PaginatedResponse handling |
| PLAT-13 | Navigation system (chat interface to management pages switch, breadcrumb navigation) | Next.js App Router Link, ManagementLayout with left sidebar, usePathname for active state |
</phase_requirements>

## Standard Stack

### Core (Already Installed)
| Library | Version | Purpose | Status |
|---------|---------|---------|--------|
| next | 15.4.4 | App Router, SSR, routing | Installed |
| react | 19.1.0 | UI library | Installed |
| swr | 2.4.1 | Server state / data fetching | Installed |
| tailwindcss | 4.x | Styling | Installed |
| shadcn | 4.7.0 | Component library (Radix-based) | Installed |
| nuqs | 2.8.9 | URL state management | Installed |
| lucide-react | 1.14.0 | Icons | Installed |
| sonner | 2.0.7 | Toast notifications | Installed |
| date-fns | 4.1.0 | Date formatting | Installed |

### New Dependencies (To Install)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| @tanstack/react-table | 8.21.3 | Headless table logic | shadcn/ui official recommendation. Sorting, filtering, pagination, row selection built-in. React >=16 compatible. |
| recharts | 3.8.1 | Chart components (BarChart, PieChart) | Most popular React charting library. React 19 compatible (peer dep `^19.0.0`). Declarative API. |
| @dnd-kit/core | 6.3.1 | Drag-drop core engine | Leading React drag-drop library. Accessible, performant. React >=16.8 compatible. |
| @dnd-kit/sortable | 10.0.0 | Sortable preset for @dnd-kit | Requires @dnd-kit/core ^6.3.0 (met). Provides useSortable hook for reorder. |
| @dnd-kit/utilities | 3.2.2 | Utility functions for @dnd-kit | Required peer of @dnd-kit/core 6.3.1. CSS utilities, transforms. |

### Discretionary (Recommended)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| zod | 4.4.3 | Form validation schemas | For create/edit forms (project, test case, test run). Replaces manual validation. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| recharts | antvis (G2) | antvis is in CLAUDE.md stack but recharts is simpler for our bar/pie charts. antvis better for complex dashboards (Phase 10 may revisit). |
| @dnd-kit | react-beautiful-dnd | react-beautiful-dnd is deprecated/unmaintained. @dnd-kit is actively maintained, more flexible. |
| zod | native validation | zod provides type-safe schema validation matching TypeScript types. Native requires manual error handling. |
| TanStack Table | AG Grid | AG Grid is heavy and commercial. TanStack is headless, free, pairs with shadcn/ui perfectly. |

**Installation:**
```bash
cd webui
npm install @tanstack/react-table recharts @dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities zod
npx shadcn@latest add table card breadcrumb collapsible alert-dialog
```

**Version verification (2026-05-14):**
- @tanstack/react-table: 8.21.3 (npm registry confirmed)
- recharts: 3.8.1 (npm registry confirmed, React 19 peer dep)
- @dnd-kit/core: 6.3.1 (npm registry confirmed)
- @dnd-kit/sortable: 10.0.0 (npm registry confirmed, requires @dnd-kit/core ^6.3.0)
- zod: 4.4.3 (npm registry confirmed)

## Architecture Patterns

### Recommended Project Structure
```
webui/src/
├── app/
│   ├── layout.tsx              # Root layout (ThemeProvider, NuqsAdapter, Toaster) -- EXTEND
│   ├── page.tsx                # Redirect to /chat (replace current content)
│   ├── globals.css             # Global styles -- UNCHANGED
│   ├── chat/
│   │   └── page.tsx            # Move current page.tsx content here
│   ├── projects/
│   │   ├── page.tsx            # Project list page
│   │   ├── loading.tsx         # Loading skeleton
│   │   └── components/         # Project-specific components
│   ├── cases/
│   │   ├── page.tsx            # Test cases list (with folder context)
│   │   ├── [id]/
│   │   │   └── page.tsx        # Test case editor (dynamic route)
│   │   └── components/         # Case editor components (StepEditor, BDDMode)
│   ├── runs/
│   │   ├── page.tsx            # Test execution dashboard
│   │   └── components/         # Dashboard charts (PassRateChart, TrendChart)
│   ├── folders/
│   │   └── page.tsx            # Folder tree management
│   ├── components/             # Shared components (EXISTING)
│   │   ├── ChatInterface.tsx   # UNCHANGED
│   │   ├── ChatMessage.tsx     # UNCHANGED
│   │   ├── ThreadList.tsx      # UNCHANGED
│   │   ├── ConfigDialog.tsx    # EXTEND (add fastapiUrl field)
│   │   ├── AgentTabs.tsx       # UNCHANGED
│   │   ├── WorkspaceSelect.tsx # REUSE in management pages
│   │   ├── Header.tsx          # NEW: Extract from page.tsx
│   │   └── ManagementLayout.tsx # NEW: Sidebar + content wrapper
│   ├── hooks/                  # Shared hooks (EXISTING)
│   │   ├── useChat.ts          # UNCHANGED
│   │   ├── useThreads.ts       # UNCHANGED
│   │   ├── useFileUpload.ts    # UNCHANGED
│   │   └── ...                 # NEW hooks added alongside
│   ├── types/
│   │   └── types.ts            # EXTEND with API response types
│   └── utils/
│       └── multimodal.ts       # UNCHANGED
├── components/
│   └── ui/                     # shadcn/ui components -- ADD table, card, breadcrumb, etc.
├── lib/
│   ├── config.ts               # EXTEND: add fastapiUrl to StandaloneConfig
│   ├── utils.ts                # UNCHANGED (cn utility)
│   ├── api-client.ts           # NEW: Base fetch wrapper for FastAPI
│   └── api/                    # NEW: SWR hooks per entity
│       ├── useProjects.ts
│       ├── useFolders.ts
│       ├── useTestCases.ts
│       └── useTestRuns.ts
├── providers/
│   ├── ClientProvider.tsx       # UNCHANGED
│   ├── ChatProvider.tsx         # UNCHANGED
│   └── ThemeProvider.tsx        # UNCHANGED
```

### Pattern 1: App Router Multi-Page Routing
**What:** Refactor single page.tsx into route-based pages under `app/` directory.
**When to use:** This is the core architectural change for Phase 9.
**Key considerations:**
- Root `app/page.tsx` becomes a redirect: `redirect('/chat')` or `useRouter().push('/chat')`
- Current page.tsx content moves to `app/chat/page.tsx`
- `app/layout.tsx` remains the root layout (ThemeProvider, NuqsAdapter, Toaster)
- Each management page is a separate `page.tsx` with `"use client"` directive
- Next.js `loading.tsx` files provide per-route loading states
- Next.js `error.tsx` files provide per-route error boundaries
- Chat page needs ClientProvider and ChatProvider -- these wrap only the chat page, not all pages

**Example (root redirect):**
```typescript
// app/page.tsx -- NEW: simple redirect
import { redirect } from "next/navigation";
export default function Home() {
  redirect("/chat");
}
```

**Example (chat page preserves existing structure):**
```typescript
// app/chat/page.tsx -- moved from app/page.tsx
// The existing HomePageContent / HomePageInner / HomePage components
// move here intact, wrapped in Suspense
"use client";
// ... existing imports and code from current page.tsx ...
```

### Pattern 2: SWR CRUD Hooks
**What:** Standardized hooks for each entity using useSWR (reads) and useSWRMutation (writes).
**When to use:** All management pages that read/write to FastAPI :8000.

**Example (useProjects hook):**
```typescript
// lib/api/useProjects.ts
"use client";

import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { apiClient } from "@/lib/api-client";
import type { ProjectInfo, ProjectCreate, ProjectUpdate } from "@/app/types/api";

// List projects (paginated)
export function useProjects(page: number = 1, pageSize: number = 30) {
  return useSWR(
    [`/projects`, page, pageSize],
    ([url, p, ps]) => apiClient.getPaginated(url, { p, page_size: ps })
  );
}

// Create project
export function useCreateProject() {
  return useSWRMutation(
    `/projects`,
    async (url: string, { arg }: { arg: ProjectCreate }) => {
      return apiClient.post(url, arg);
    }
  );
}

// Update project
export function useUpdateProject() {
  return useSWRMutation(
    `/projects`,
    async (_url: string, { arg }: { arg: { identifier: string; data: ProjectUpdate } }) => {
      return apiClient.patch(`/projects/${arg.identifier}`, arg.data);
    }
  );
}

// Delete project
export function useDeleteProject() {
  return useSWRMutation(
    `/projects`,
    async (_url: string, { arg }: { arg: string }) => {
      return apiClient.delete(`/projects/${arg}`);
    }
  );
}
```

### Pattern 3: DataTable Component (TanStack + shadcn)
**What:** Reusable generic DataTable following shadcn/ui official data table pattern.
**When to use:** Projects list, test cases list, test runs list.

**Example:**
```typescript
// app/components/DataTable.tsx
"use client";

import { ColumnDef, flexRender, getCoreRowModel, useReactTable } from "@tanstack/react-table";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

interface DataTableProps<TData, TValue> {
  columns: ColumnDef<TData, TValue>[];
  data: TData[];
}

export function DataTable<TData, TValue>({ columns, data }: DataTableProps<TData, TValue>) {
  const table = useReactTable({ data, columns, getCoreRowModel: getCoreRowModel() });

  return (
    <Table>
      <TableHeader>
        {table.getHeaderGroups().map((hg) => (
          <TableRow key={hg.id}>
            {hg.headers.map((h) => (
              <TableHead key={h.id}>
                {h.isPlaceholder ? null : flexRender(h.column.columnDef.header, h.getContext())}
              </TableHead>
            ))}
          </TableRow>
        ))}
      </TableHeader>
      <TableBody>
        {table.getRowModel().rows?.length ? (
          table.getRowModel().rows.map((row) => (
            <TableRow key={row.id}>
              {row.getVisibleCells().map((cell) => (
                <TableCell key={cell.id}>
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </TableCell>
              ))}
            </TableRow>
          ))
        ) : (
          <TableRow>
            <TableCell colSpan={columns.length} className="h-24 text-center">No results.</TableCell>
          </TableRow>
        )}
      </TableBody>
    </Table>
  );
}
```

### Pattern 4: API Client Wrapper
**What:** Centralized fetch wrapper for FastAPI :8000 with workspace header injection and error handling.
**When to use:** All SWR hooks use this client instead of raw fetch.

```typescript
// lib/api-client.ts
import { getConfig } from "@/lib/config";

interface PaginatedResponse<T> {
  success: boolean;
  data: T[];
  info: { page: number; page_size: number; total: number; count: number; prev: string | null; next: string | null };
}

interface SuccessResponse<T> {
  success: boolean;
  data: T;
}

interface MessageResponse {
  success: boolean;
  message: string;
}

class ApiClient {
  private getBaseUrl(): string {
    const config = getConfig();
    return config?.fastapiUrl || "http://localhost:8000";
  }

  private getWorkspaceId(): string {
    const config = getConfig();
    return config?.workspaceId || "default";
  }

  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const baseUrl = this.getBaseUrl();
    const workspaceId = this.getWorkspaceId();

    const res = await fetch(`${baseUrl}/api/v2${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        "X-Space-Id": workspaceId,
        ...options.headers,
      },
    });

    if (!res.ok) {
      const error = await res.json().catch(() => ({ message: "Request failed" }));
      throw new Error(error.message || `HTTP ${res.status}`);
    }

    return res.json();
  }

  async get<T>(path: string, params?: Record<string, string>): Promise<SuccessResponse<T>> {
    const query = params ? "?" + new URLSearchParams(params).toString() : "";
    return this.request<SuccessResponse<T>>(`${path}${query}`);
  }

  async getPaginated<T>(path: string, params?: Record<string, string | number>): Promise<PaginatedResponse<T>> {
    const query = params ? "?" + new URLSearchParams(
      Object.entries(params).map(([k, v]) => [k, String(v)])
    ).toString() : "";
    return this.request<PaginatedResponse<T>>(`${path}${query}`);
  }

  async post<T>(path: string, body: unknown): Promise<SuccessResponse<T>> {
    return this.request<SuccessResponse<T>>(path, { method: "POST", body: JSON.stringify(body) });
  }

  async patch<T>(path: string, body: unknown): Promise<SuccessResponse<T>> {
    return this.request<SuccessResponse<T>>(path, { method: "PATCH", body: JSON.stringify(body) });
  }

  async delete(path: string): Promise<MessageResponse> {
    return this.request<MessageResponse>(path, { method: "DELETE" });
  }
}

export const apiClient = new ApiClient();
```

### Pattern 5: ManagementLayout with Sidebar
**What:** Shared layout component for all management pages with left sidebar navigation.
**When to use:** Projects, Folders, Cases list, Runs pages.

```typescript
// app/components/ManagementLayout.tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { FolderKanban, FileText, PlayCircle, FolderTree, MessageSquare, Settings } from "lucide-react";
import { WorkspaceSelect } from "@/app/components/WorkspaceSelect";

const NAV_ITEMS = [
  { href: "/projects", label: "项目列表", icon: FolderKanban },
  { href: "/folders", label: "文件夹", icon: FolderTree },
  { href: "/cases", label: "测试用例", icon: FileText },
  { href: "/runs", label: "测试执行", icon: PlayCircle },
];

export function ManagementLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex h-screen">
      <aside className="w-[200px] flex-shrink-0 border-r bg-muted/40 p-4">
        <nav className="space-y-1">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-accent",
                pathname.startsWith(item.href) ? "bg-accent font-medium" : "text-muted-foreground"
              )}
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="mt-6 border-t pt-4">
          <Link href="/chat" className="flex items-center gap-2 px-3 py-2 text-sm text-muted-foreground hover:bg-accent">
            <MessageSquare className="h-4 w-4" />
            返回聊天
          </Link>
        </div>
      </aside>
      <main className="flex-1 overflow-auto p-6">{children}</main>
    </div>
  );
}
```

### Anti-Patterns to Avoid
- **Moving ClientProvider/ChatProvider to root layout:** These are chat-specific providers. Management pages do not need LangGraph client. Keep them wrapping only the chat page.
- **Using SWR for chat data:** SWR is for FastAPI CRUD data. Chat continues using the existing useChat hook with LangGraph SDK streaming.
- **Creating a monolithic management page:** Each page (projects, cases, runs, folders) should be its own route with independent loading/error states.
- **Polling with useSWR for static data:** Set `revalidateOnFocus: false` for reference data (projects list when user is not actively managing). Use `refreshInterval` only for test run status polling.
- **Hardcoding FastAPI URL in multiple places:** All API calls go through `apiClient` which reads from config.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Data table with sorting/pagination | Custom table with useState | TanStack Table + shadcn Table | TanStack handles sorting, pagination, filtering, row selection, column visibility. ~300 lines of headless logic. |
| Folder tree drag-drop | Custom mouse event handlers | @dnd-kit/core + @dnd-kit/sortable | Drag-drop is deceptively complex (touch, keyboard, accessibility, collision detection, animations). @dnd-kit handles all edge cases. |
| Chart rendering | Canvas/SVG from scratch | recharts | SVG-based, responsive, composable, handles tooltips, legends, animations out of the box. |
| Form validation | Manual if/else chains | zod | Type-safe schemas, reusable between client and future server, automatic error messages. |
| API client error handling | Try/catch in every component | apiClient wrapper + SWR error handling | Centralized error handling, workspace header injection, consistent response unwrapping. |
| Toast notifications for mutations | alert() or custom toast | sonner (already installed) | toast.success(), toast.error() already available. |

**Key insight:** The existing codebase already avoids hand-rolling. SWR is installed for data fetching, shadcn for UI, sonner for toasts. This phase extends the same philosophy to new concerns (tables, charts, drag-drop).

## Common Pitfalls

### Pitfall 1: Provider Scope Mismatch
**What goes wrong:** Wrapping ClientProvider/ChatProvider in root layout makes management pages crash because they depend on LangGraph SDK client that is not needed.
**Why it happens:** Natural instinct to put providers at the highest level.
**How to avoid:** ClientProvider and ChatProvider wrap ONLY the chat page. Management pages use their own data fetching (SWR + apiClient).
**Warning signs:** "useClient must be used within ClientProvider" errors on /projects page.

### Pitfall 2: StandaloneConfig Backward Compatibility
**What goes wrong:** Adding `fastapiUrl` to StandaloneConfig causes existing saved configs to not have this field, leading to undefined behavior.
**Why it happens:** localStorage configs are saved at Phase 1 and not updated when schema changes.
**How to avoid:** Make `fastapiUrl` optional with a default value (`http://localhost:8000`). Use `config?.fastapiUrl || "http://localhost:8000"` pattern everywhere.
**Warning signs:** apiClient requests to `undefined/api/v2/projects`.

### Pitfall 3: SWR Cache Key Collisions
**What goes wrong:** Multiple useSWR calls with different params return stale or wrong data.
**Why it happens:** SWR caches by key. If two hooks use the same key string with different params, they share cache.
**How to avoid:** Include all relevant params in the key array: `useSWR(['/projects', page, pageSize, projectId], ...)`.
**Warning signs:** Navigating between projects shows cached data from previous project.

### Pitfall 4: @dnd-kit Sortable with Nested Trees
**What goes wrong:** Drag-drop in hierarchical tree causes items to disappear or jump between levels unexpectedly.
**Why it happens:** @dnd-kit's sortable is designed for flat lists. Tree structures need custom collision detection and drop logic for parent-child relationships.
**How to avoid:** Per D-06 and deferred items, implement basic same-level reorder only. Cross-level moves are deferred. Use separate sortable containers per level.
**Warning signs:** Dragging a folder causes its children to be orphaned.

### Pitfall 5: Next.js 15 Redirect vs useRouter
**What goes wrong:** Using `redirect()` from `next/navigation` in a client component throws an error.
**Why it happens:** `redirect()` is a server-side function. In client components, use `useRouter().push()`.
**How to avoid:** Root `app/page.tsx` can use server-side `redirect('/chat')` since it's not a client component. All management page navigation uses `<Link>` or `useRouter()`.
**Warning signs:** "redirect() is not a function" or SERVER error in browser console.

### Pitfall 6: SWR Mutation Cache Revalidation
**What goes wrong:** After creating/updating/deleting a record, the list still shows old data.
**Why it happens:** useSWRMutation does not automatically revalidate related queries.
**How to avoid:** Use `mutate()` from SWR global cache to revalidate the list after mutation. Pattern: `import { mutate } from 'swr'; ... mutate('/projects')` after create/update/delete.
**Warning signs:** User creates project but it does not appear in list until page refresh.

### Pitfall 7: FastAPI Paginated Response Unwrapping
**What goes wrong:** Components receive `{ success: true, data: [...], info: {...} }` instead of the array they expect.
**Why it happens:** FastAPI wraps all responses in `SuccessResponse<T>` or `PaginatedResponse<T>`. Frontend must unwrap `.data`.
**How to avoid:** apiClient methods should unwrap the response envelope. SWR hooks return the inner data directly.
**Warning signs:** `.map is not a function` error when trying to iterate over API response.

## Code Examples

### FastAPI Response Types (matching Phase 8 backend schemas)
```typescript
// app/types/api.ts -- Type definitions matching backend Pydantic schemas

// === Pagination ===
export interface PaginationInfo {
  page: number;
  page_size: number;
  count: number;
  total: number;
  prev: string | null;
  next: string | null;
}

export interface PaginatedResponse<T> {
  success: boolean;
  data: T[];
  info: PaginationInfo;
}

export interface SuccessResponse<T> {
  success: boolean;
  data: T;
}

export interface MessageResponse {
  success: boolean;
  message: string;
}

// === Project ===
export interface ProjectInfo {
  id: string;
  identifier: string;  // e.g. "PR-0001"
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface ProjectCreate {
  name: string;
  description?: string;
}

export interface ProjectUpdate {
  name?: string;
  description?: string;
}

// === Folder ===
export interface FolderInfo {
  id: string;
  project_id: string;
  parent_id: string | null;
  name: string;
  description: string | null;
  folder_type: "test_case" | "api_test";
  created_at: string;
  updated_at: string | null;
}

export interface FolderTreeNode extends FolderInfo {
  children: FolderTreeNode[];
}

export interface FolderCreate {
  project_id: string;
  parent_id?: string | null;
  name: string;
  description?: string;
  folder_type?: "test_case" | "api_test";
}

// === Test Case ===
export interface TestStepInfo {
  id: string;
  step_number: number;
  action: string;
  expected_result: string | null;
}

export interface TestCaseInfo {
  id: string;
  project_id: string;
  folder_id: string | null;
  identifier: string;
  name: string;
  description: string | null;
  preconditions: string | null;
  priority: "low" | "medium" | "high" | "critical";
  state: "new" | "review_pending" | "reviewed" | "not_run" | "passed" | "failed" | "blocked" | "skipped";
  test_case_type: string;
  template: "test_case" | "test_case_bdd";
  feature: string | null;
  scenario: string | null;
  background: string | null;
  automation_status: string | null;
  custom_fields: Record<string, unknown> | null;
  version: number;
  steps: TestStepInfo[];
  created_at: string;
  updated_at: string | null;
}

// === Test Run ===
export interface TestRunTestCaseInfo {
  id: string;
  test_run_id: string;
  test_case_id: string;
  latest_status: "passed" | "failed" | "skipped" | "blocked" | "not_executed";
  created_at: string;
  updated_at: string | null;
}

export interface TestRunInfo {
  id: string;
  project_id: string;
  identifier: string;
  name: string;
  description: string | null;
  run_state: "new_run" | "in_progress" | "under_review" | "rejected" | "done" | "closed";
  active_state: "active" | "closed";
  test_cases_count: number;
  passed_count: number;
  failed_count: number;
  skipped_count: number;
  blocked_count: number;
  not_executed_count: number;
  test_run_cases: TestRunTestCaseInfo[];
  created_at: string;
  updated_at: string | null;
}

// === Test Result ===
export interface TestResultInfo {
  id: string;
  test_run_id: string;
  test_case_id: string;
  status: "passed" | "failed" | "skipped" | "blocked" | "not_executed";
  description: string | null;
  duration_ms: number | null;
  step_results: TestStepResultInfo[];
  created_at: string;
  updated_at: string | null;
}
```

### SWR Hook for Folder Tree
```typescript
// lib/api/useFolders.ts
"use client";

import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { apiClient } from "@/lib/api-client";
import type { FolderInfo, FolderTreeNode, FolderCreate } from "@/app/types/api";

export function useFolders(projectId: string | null) {
  return useSWR(
    projectId ? [`/folders/project/${projectId}`, projectId] : null,
    () => apiClient.get<FolderInfo[]>(`/folders/project/${projectId!}`)
  );
}

export function useFolderTree(projectId: string | null) {
  return useSWR(
    projectId ? [`/folders/project/${projectId}/tree`, projectId] : null,
    () => apiClient.get<FolderTreeNode[]>(`/folders/project/${projectId!}/tree`)
  );
}

export function useCreateFolder() {
  return useSWRMutation(
    "/folders",
    async (url: string, { arg }: { arg: FolderCreate }) => apiClient.post<FolderInfo>(url, arg)
  );
}
```

### recharts Dashboard Components
```typescript
// app/runs/components/PassRateChart.tsx
"use client";

import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import type { TestRunInfo } from "@/app/types/api";

export function PassRateChart({ runs }: { runs: TestRunInfo[] }) {
  const data = runs.map((run) => ({
    name: run.name.length > 15 ? run.name.slice(0, 15) + "..." : run.name,
    passed: run.passed_count,
    failed: run.failed_count,
    skipped: run.skipped_count,
    blocked: run.blocked_count,
    notExecuted: run.not_executed_count,
  }));

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="name" />
        <YAxis />
        <Tooltip />
        <Legend />
        <Bar dataKey="passed" fill="#22c55e" name="Passed" />
        <Bar dataKey="failed" fill="#ef4444" name="Failed" />
        <Bar dataKey="skipped" fill="#f59e0b" name="Skipped" />
        <Bar dataKey="blocked" fill="#6b7280" name="Blocked" />
      </BarChart>
    </ResponsiveContainer>
  );
}
```

### @dnd-kit Folder Tree Node (Same-Level Reorder)
```typescript
// app/folders/components/FolderTreeNodeItem.tsx
"use client";

import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { ChevronRight, ChevronDown, Folder, GripVertical } from "lucide-react";
import { cn } from "@/lib/utils";

interface FolderTreeNodeItemProps {
  node: FolderTreeNode;
  depth: number;
  isExpanded: boolean;
  onToggle: () => void;
}

export function FolderTreeNodeItem({ node, depth, isExpanded, onToggle }: FolderTreeNodeItemProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: node.id,
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    paddingLeft: `${depth * 20}px`,
  };

  return (
    <div ref={setNodeRef} style={style} className={cn("flex items-center gap-1 py-1 px-2 hover:bg-accent", isDragging && "opacity-50")}>
      <button {...attributes} {...listeners} className="cursor-grab">
        <GripVertical className="h-4 w-4 text-muted-foreground" />
      </button>
      <button onClick={onToggle} className="p-0.5">
        {node.children.length > 0 ? (
          isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />
        ) : (
          <span className="w-4" />
        )}
      </button>
      <Folder className="h-4 w-4 text-muted-foreground" />
      <span className="text-sm">{node.name}</span>
    </div>
  );
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SWR `useSWRInfinite` for all data | `useSWR` for paginated + `useSWRMutation` for writes | SWR 2.x | Cleaner separation of reads/writes. Automatic revalidation control. |
| @dnd-kit v5 | @dnd-kit v6 (core) + v10 (sortable) | 2024-2025 | New peer dependency structure (@dnd-kit/accessibility added). Same API. |
| recharts 2.x | recharts 3.x | Late 2024 | React 19 support. Same API. New `react-is` peer dep. |
| Next.js pages router | App Router (stable since 14) | 2023-2024 | File-based routing, layouts, loading/error states, server components. |
| TanStack Table 7 (React Table) | TanStack Table 8 | 2023 | Headless API, framework-agnostic, `ColumnDef` type system. |

**Deprecated/outdated:**
- react-beautiful-dnd: Deprecated by author. Use @dnd-kit instead.
- AG Grid Community: Heavy, opinionated. TanStack Table is lighter and pairs with shadcn.
- react-table v7: Renamed to @tanstack/react-table v8. New API.

## Open Questions

1. **Test Case Editor: Steps vs BDD Mode Toggle**
   - What we know: Backend supports `template: "test_case" | "test_case_bdd"` and BDD fields (feature, scenario, background).
   - What's unclear: Whether the BDD editor should be a separate route or a mode toggle within the same editor.
   - Recommendation: Mode toggle within `/cases/[id]` editor. Simpler routing, shared header/metadata fields. Steps table swaps to Given/When/Then text areas.

2. **Test Case Creation Flow**
   - What we know: Test cases belong to a project and optionally a folder. Creating requires project_id.
   - What's unclear: Whether creation happens via a dialog modal or a dedicated `/cases/new` page.
   - Recommendation: Dialog modal from the cases list page, similar to project creation. Simpler UX, fewer routes to manage.

3. **Folder Tree Page vs Sidebar Component**
   - What we know: D-03 specifies left sidebar + right content layout for management pages. D-10 says folder tree is a component.
   - What's unclear: Whether folder tree appears only on `/folders` page or as a sidebar widget on multiple pages.
   - Recommendation: Full folder tree on `/folders` page. Compact folder selector (dropdown) on cases list page for filtering. This matches D-03 sidebar pattern.

4. **Workspace Filtering in FastAPI**
   - What we know: Phase 8 backend has `DEFAULT_USER_ID` pattern and workspace-based data separation. Phase 7 established `X-Space-Id` header for LangGraph.
   - What's unclear: Whether Phase 8 endpoints actually read `X-Space-Id` header or require `space_id` query parameter.
   - Recommendation: Check Phase 8 backend code during implementation. The apiClient should send both header and query param to be safe.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node.js | Frontend build | Yes | Check needed | -- |
| npm | Package management | Yes | Check needed | -- |
| FastAPI :8000 | CRUD API data | Needs running | Phase 8 backend | Mock data for development |
| PostgreSQL | Backend database | Needs running | Phase 8 setup | -- |
| Next.js :3000 | Frontend dev server | Yes | 15.4.4 | -- |

**Missing dependencies with no fallback:**
- FastAPI backend must be running for management pages to show real data. Development can proceed with error/loading states until backend is available.
- PostgreSQL must be running for FastAPI backend.

**Missing dependencies with fallback:**
- None identified. All frontend tooling is in place.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | None installed -- Wave 0 setup needed |
| Config file | None -- needs creation |
| Quick run command | `cd webui && npx vitest run --reporter=verbose` (after setup) |
| Full suite command | `cd webui && npx vitest run` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PLAT-09 | Project list renders, CRUD operations work | integration | `npx vitest run tests/project-page.test.tsx` | No -- Wave 0 |
| PLAT-10 | Folder tree renders, drag-drop reorders | unit | `npx vitest run tests/folder-tree.test.tsx` | No -- Wave 0 |
| PLAT-11 | Test case editor loads, step editing works | unit | `npx vitest run tests/case-editor.test.tsx` | No -- Wave 0 |
| PLAT-12 | Dashboard charts render with run data | unit | `npx vitest run tests/run-dashboard.test.tsx` | No -- Wave 0 |
| PLAT-13 | Navigation between pages works | integration | `npx vitest run tests/navigation.test.tsx` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `npx vitest run --reporter=verbose`
- **Per wave merge:** `npx vitest run`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] Install vitest: `npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom`
- [ ] Create `webui/vitest.config.ts` -- vitest configuration with jsdom environment
- [ ] Create `webui/tests/setup.ts` -- test setup with @testing-library/jest-dom
- [ ] Create `webui/tests/navigation.test.tsx` -- covers PLAT-13
- [ ] Create `webui/tests/project-page.test.tsx` -- covers PLAT-09
- [ ] Create `webui/tests/folder-tree.test.tsx` -- covers PLAT-10
- [ ] Create `webui/tests/case-editor.test.tsx` -- covers PLAT-11
- [ ] Create `webui/tests/run-dashboard.test.tsx` -- covers PLAT-12

## Sources

### Primary (HIGH confidence)
- npm registry -- verified current versions of all new dependencies (2026-05-14)
- Phase 8 backend source code -- exact API endpoint signatures and response schemas
- Existing frontend codebase -- established patterns (SWR, shadcn, nuqs, providers)

### Secondary (MEDIUM confidence)
- shadcn/ui official documentation -- DataTable pattern (training data, verified against installed shadcn 4.7.0)
- @tanstack/react-table documentation -- API patterns (training data, verified against npm v8.21.3)
- @dnd-kit documentation -- sortable API (training data, verified against npm v6.3.1 / v10.0.0)
- recharts documentation -- component API (training data, verified against npm v3.8.1)

### Tertiary (LOW confidence)
- None -- all findings verified via npm registry or source code inspection

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all versions verified via npm registry, all peer deps confirmed compatible with React 19
- Architecture: HIGH -- based on direct reading of existing codebase (page.tsx, layout.tsx, providers, hooks, config)
- Pitfalls: HIGH -- based on known Next.js 15 App Router patterns and SWR behavior
- API types: HIGH -- extracted directly from Phase 8 Pydantic schema source files
- Code examples: MEDIUM -- patterns follow established conventions but not yet tested in this specific codebase

**Research date:** 2026-05-14
**Valid until:** 2026-06-14 (stable libraries, low churn expected)
