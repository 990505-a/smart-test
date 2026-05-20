# Phase 13: Workspace Management - Research

**Researched:** 2026-05-20
**Domain:** Backend CRUD API + Frontend workspace selector + Directory provisioning
**Confidence:** HIGH

## Summary

Phase 13 adds dynamic workspace CRUD to a system that currently has a hardcoded single workspace ("default"). The backend already has the `get_space_id()` / `get_workspace_dir()` helpers in `src/app/core/workspace.py` that resolve workspace directories from LangGraph's configurable mechanism, and the frontend already has a `WorkspaceSelect` component backed by a hardcoded `WORKSPACES` constant in `types.ts`. The `apiClient` already sends `X-Space-Id` headers on every request. What's missing is: (1) a database `workspaces` table and CRUD API to manage workspaces dynamically, (2) replacing the hardcoded frontend `WORKSPACES` with a data-driven approach fetched from the API, (3) directory auto-provisioning that creates the `api/`, `web/`, `testcase/`, `attachments/`, `scripts/` subdirectories when a new workspace is created, and (4) skill directory scaffolding (copying default workspace skills into new workspaces).

The existing architecture provides excellent foundations: the three-layer FastAPI pattern (Routes -> Services -> Repositories), the `BaseRepository` generic class, the Pydantic schema pattern, the SWR hooks pattern, and the `apiClient` class. This phase follows the same patterns -- the main work is adding a new model/table, CRUD endpoints, and connecting the frontend to the API.

**Primary recommendation:** Follow the existing Project CRUD pattern exactly -- add a `Workspace` SQLAlchemy model, repository, service, schemas, and FastAPI routes. Replace the hardcoded `WORKSPACES` constant with an SWR hook that fetches from `/api/v2/workspaces`. Add directory provisioning in the workspace service's `create` method.

## Standard Stack

### Core (already in project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.136.1 | REST API framework | Existing Phase 8+ pattern |
| SQLAlchemy | 2.0.49 | Async ORM | Existing database layer (SQLite via aiosqlite) |
| Pydantic | 2.12.4 | Schema validation | Existing request/response models |
| SWR | latest | Frontend data fetching | Existing useProjects/useTestCases hooks |
| Shadcn/ui Select | latest | Workspace selector component | Already used in WorkspaceSelect.tsx |

### Supporting (already in project)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| aiosqlite | >=0.21.0 | SQLite async driver | Database backend (no PostgreSQL needed) |
| pathlib | stdlib | Directory operations | Auto-provisioning workspace directories |
| shutil | stdlib | Directory copy | Copying skills from default workspace |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| SQLite workspaces table | Filesystem-based manifest.json | SQLite already used, provides query/transaction support, consistent with existing pattern |
| Copy skills on create | Symlink to default skills | Symlinks are fragile on Windows; explicit copy gives each workspace independent skills |
| Per-workspace database isolation | Shared database with workspace_id FK | Shared database is simpler, workspace_id column approach is sufficient for this scale |

**Installation:**
No new packages required. All dependencies are already in pyproject.toml and package.json.

**Version verification:** Confirmed installed versions via `python -c "import ..."`.
- SQLAlchemy: 2.0.49
- FastAPI: 0.136.1
- Pydantic: 2.12.4

## Architecture Patterns

### Existing Three-Layer Pattern (follow exactly)
```
Backend:
  src/app/db/models/workspace.py         # SQLAlchemy model
  src/app/db/schemas/workspace.py         # Pydantic schemas (Create, Update, Info)
  src/app/db/repositories/workspace_repo.py  # Repository with BaseRepository[Workspace]
  src/app/db/services/workspace_service.py   # Business logic (CRUD + dir provisioning)
  src/app/api/v2/workspaces.py           # FastAPI router

Frontend:
  webui/src/app/types/api.ts             # TypeScript types (WorkspaceInfo, WorkspaceCreate)
  webui/src/lib/api/useWorkspaces.ts     # SWR hooks (useWorkspaces, useCreateWorkspace, etc.)
  webui/src/app/components/WorkspaceSelect.tsx  # Updated component
```

### Pattern 1: Workspace Model
**What:** SQLAlchemy model following existing UUIDMixin + TimestampMixin pattern
**When to use:** Database table for workspace metadata
**Example:**
```python
# Follows src/app/db/models/project.py pattern exactly
class Workspace(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "workspaces"
    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(default=False, nullable=False)
```

### Pattern 2: Directory Auto-Provisioning
**What:** When creating a workspace, create the standard directory structure
**When to use:** In the workspace service `create` method
**Example:**
```python
# Standard subdirs: api/, web/, testcase/, attachments/, scripts/
SUBDIRS = ["api", "web", "testcase", "attachments", "scripts"]

async def create_workspace(self, data: WorkspaceCreate) -> WorkspaceInfo:
    # 1. Create DB record
    # 2. Create directory: workspace/{slug}/
    workspace_dir = settings.workspace_dir / slug
    for subdir in SUBDIRS:
        (workspace_dir / subdir).mkdir(parents=True, exist_ok=True)
    # 3. Optionally copy skills from default workspace
    return WorkspaceInfo.model_validate(workspace)
```

### Pattern 3: Frontend Data-Driven Workspace Selector
**What:** Replace hardcoded WORKSPACES constant with API-fetched data
**When to use:** WorkspaceSelect component
**Example:**
```typescript
// Replace: const WORKSPACES = [{ id: "default", label: "Default" }] as const;
// With: Fetch from API via SWR
const { data } = useWorkspaces();
const workspaces = data?.data ?? [];
```

### Anti-Patterns to Avoid
- **Hardcoding workspace list:** The current `WORKSPACES` constant in types.ts is the anti-pattern this phase fixes. Do not add more hardcoded entries.
- **Using workspace id as filesystem directory name directly:** Sanitize slugs for filesystem safety. Use a validated slug format (lowercase, hyphens, no special chars).
- **Skipping "default" workspace seeding:** The "default" workspace already exists on disk but has no DB record. The service must auto-seed the default workspace on first list/create call.
- **Deleting the "default" workspace:** The default workspace should be protected from deletion (is_default flag check).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| CRUD boilerplate | Custom SQL queries | `BaseRepository[Workspace]` from `src/app/db/repositories/base.py` | Already provides get_by_id, get_all, count, create, update, delete |
| Identifier generation | Custom counter | Adapt `generate_identifier()` from `src/app/db/utils/identifier.py` or use slug-based naming | Workspaces use human-readable slugs, not auto-increment PR-xxx format |
| API response format | Custom response shapes | `SuccessResponse[T]`, `MessageResponse`, `PaginatedResponse[T]` from `src/app/db/schemas/common.py` | Consistent with all existing endpoints |
| Frontend data fetching | Custom fetch calls | `useSWR` + `useSWRMutation` pattern from `useProjects.ts` | Caching, revalidation, error handling built in |
| Workspace dir resolution | Custom path logic | `settings.workspace_dir / slug` using existing config pattern | Already used throughout codebase |

**Key insight:** The project has a mature three-layer architecture from Phases 8-11. Every CRUD entity (Project, Folder, TestCase, TestRun, APITest) follows the exact same pattern. This phase should add Workspace as another entity in that same architecture.

## Common Pitfalls

### Pitfall 1: Type Narrowing Breaks When WORKSPACES Becomes Dynamic
**What goes wrong:** The current `WorkspaceId` type is derived from `as const` tuple: `(typeof WORKSPACES)[number]["id"]`. This produces the literal `"default"`. When WORKSPACES becomes an API response array, the type becomes `string`, breaking every `WorkspaceId` type annotation.
**Why it happens:** TypeScript literal types from `as const` cannot be preserved from runtime API data.
**How to avoid:** Change `WorkspaceId` to `string` type. Update all consumers. The type safety comes from runtime validation, not literal types.
**Warning signs:** TypeScript errors on `onWorkspaceChange(v as WorkspaceId)` after removing `as const`.

### Pitfall 2: Race Condition on Workspace Switch
**What goes wrong:** User switches workspace while a request is in-flight. The response comes back for the old workspace but UI shows new workspace data.
**Why it happens:** apiClient reads workspaceId from localStorage at request time, but the response handler may execute after the user has already switched.
**How to avoid:** Current apiClient already reads `getWorkspaceId()` per-request (line 17 of api-client.ts). The existing pattern is correct. Just ensure the frontend clears thread state on switch (already done in `handleWorkspaceChange`).
**Warning signs:** Data from workspace A appearing when workspace B is selected.

### Pitfall 3: Default Workspace Has No DB Record
**What goes wrong:** Creating a workspace via API creates a DB record, but the existing "default" workspace on disk has no corresponding DB row. Listing workspaces returns empty or only newly created ones.
**Why it happens:** The default workspace directory was created manually before the workspaces table existed.
**How to avoid:** Auto-seed the default workspace in the service layer: if the table is empty, insert a row for "default" with `is_default=True`. This can happen lazily on first `get_all()` call or eagerly on app startup.
**Warning signs:** Frontend workspace selector shows empty after upgrade.

### Pitfall 4: Deleting Workspace with Active Agent Threads
**What goes wrong:** User deletes a workspace while LangGraph agents are actively using it. Agent tools call `get_workspace_dir(space_id)` which returns a now-deleted directory path.
**Why it happens:** LangGraph threads store `space_id` in configurable. Deleting the workspace doesn't stop running agent threads.
**How to avoid:** (1) Check for active threads before deletion (complex), or (2) soft-delete with a warning, or (3) simply document the limitation and allow deletion -- the directory is gone but the agent thread will fail gracefully. For this phase, allow deletion with a confirmation -- the directory can be recreated on demand.
**Warning signs:** Agent errors after workspace deletion.

### Pitfall 5: Skills Not Available in New Workspaces
**What goes wrong:** Creating a new workspace creates empty `api/skills/` and `web/skills/` directories. Agent tools look for skills in these directories and find nothing.
**Why it happens:** Skills are loaded from `workspace/{space_id}/{agent}/skills/` at runtime. A new workspace has no SKILL.md files.
**How to avoid:** Copy skills from the default workspace during provisioning. Use `shutil.copytree()` for the skills subdirectories.
**Warning signs:** Agent chat in a new workspace has no skills loaded.

### Pitfall 6: SQLite identifier_seq Table Doesn't Exist for Workspace
**What goes wrong:** The `generate_identifier()` function tries to INSERT into `identifier_seq` table for a new `workspace_slug_seq` key, but the table only has entries for existing entities.
**Why it happens:** The identifier_seq table uses INSERT OR IGNORE which handles this correctly, but workspaces should use slugs not sequential identifiers.
**How to avoid:** Workspaces use user-provided or derived slugs (not PR-xxx format). Derive slug from name: `name.lower().replace(" ", "-")`. Validate uniqueness via DB unique constraint.
**Warning signs:** N/A -- just use slug-based approach instead.

## Code Examples

### Backend: Workspace Model
```python
# src/app/db/models/workspace.py
# Follows src/app/db/models/project.py pattern

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.app.db.database import Base
from src.app.db.models.base import TimestampMixin, UUIDMixin


class Workspace(Base, UUIDMixin, TimestampMixin):
    """Workspace table - stores workspace metadata for multi-space isolation."""
    __tablename__ = "workspaces"
    __table_args__ = {"comment": "Workspace table"}

    slug: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True,
        comment="URL-safe workspace slug, e.g. 'default', 'project-alpha'",
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Display name",
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Workspace description",
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="Whether this is the system default workspace (cannot be deleted)",
    )

    def __repr__(self) -> str:
        return f"<Workspace(id={self.id}, slug={self.slug}, name={self.name})>"
```

### Backend: Workspace Service with Directory Provisioning
```python
# src/app/db/services/workspace_service.py
# Follows src/app/db/services/project_service.py pattern

import re
import shutil
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.config import settings
from src.app.db.repositories.workspace_repo import WorkspaceRepository
from src.app.db.schemas.workspace import WorkspaceCreate, WorkspaceInfo, WorkspaceUpdate
from src.app.db.utils.exceptions import ConflictException, NotFoundException

SUBDIRS = ["api", "web", "testcase", "attachments", "scripts"]


class WorkspaceService:
    def __init__(self, db: AsyncSession):
        self.repo = WorkspaceRepository(db)

    async def _ensure_default(self) -> None:
        """Auto-seed default workspace if table is empty."""
        count = await self.repo.count()
        if count == 0:
            await self.repo.create(
                slug="default",
                name="Default",
                description="Default workspace",
                is_default=True,
            )

    @staticmethod
    def _slugify(name: str) -> str:
        """Convert name to URL-safe slug."""
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        return slug or "workspace"

    async def list_workspaces(self) -> list[WorkspaceInfo]:
        await self._ensure_default()
        workspaces = await self.repo.get_all(offset=0, limit=100)
        return [WorkspaceInfo.model_validate(w) for w in workspaces]

    async def create_workspace(self, data: WorkspaceCreate) -> WorkspaceInfo:
        slug = data.slug or self._slugify(data.name)
        # Check uniqueness
        existing = await self.repo.get_by_slug(slug)
        if existing:
            raise ConflictException(f"Workspace slug '{slug}' already exists")

        workspace = await self.repo.create(
            slug=slug, name=data.name,
            description=data.description, is_default=False,
        )

        # Provision directory structure
        workspace_dir = settings.workspace_dir / slug
        for subdir in SUBDIRS:
            (workspace_dir / subdir).mkdir(parents=True, exist_ok=True)

        # Copy skills from default workspace
        default_dir = settings.workspace_dir / "default"
        for agent_subdir in ["api/skills", "web/skills"]:
            src = default_dir / agent_subdir
            dst = workspace_dir / agent_subdir
            if src.exists() and not dst.exists():
                shutil.copytree(src, dst)

        return WorkspaceInfo.model_validate(workspace)

    async def delete_workspace(self, slug: str) -> str:
        workspace = await self.repo.get_by_slug(slug)
        if not workspace:
            raise NotFoundException(resource="Workspace", identifier=slug)
        if workspace.is_default:
            raise ConflictException("Cannot delete the default workspace")

        # Remove directory
        workspace_dir = settings.workspace_dir / slug
        if workspace_dir.exists():
            shutil.rmtree(workspace_dir)

        await self.repo.delete(workspace)
        return f"Workspace '{slug}' deleted successfully"
```

### Frontend: Updated WorkspaceSelect Component
```typescript
// webui/src/app/components/WorkspaceSelect.tsx
// Updated to fetch workspaces from API instead of hardcoded constant

"use client";

import { useWorkspaces } from "@/lib/api/useWorkspaces";
import { Building2, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
// ... shadcn Select imports ...

export function WorkspaceSelect({
  workspaceId,
  onWorkspaceChange,
}: {
  workspaceId: string;
  onWorkspaceChange: (id: string) => void;
}) {
  const { data } = useWorkspaces();
  const workspaces = data?.data ?? [];

  return (
    <div className="flex items-center gap-1">
      <Select value={workspaceId} onValueChange={(v) => { if (v !== null) onWorkspaceChange(v); }}>
        <SelectTrigger className="w-[160px] h-9">
          <Building2 className="mr-2 h-4 w-4" />
          <SelectValue placeholder="Workspace" />
        </SelectTrigger>
        <SelectContent>
          {workspaces.map((ws) => (
            <SelectItem key={ws.slug} value={ws.slug}>
              {ws.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {/* Create/Delete buttons */}
    </div>
  );
}
```

### Frontend: SWR Hooks for Workspace API
```typescript
// webui/src/lib/api/useWorkspaces.ts
// Follows useProjects.ts pattern

import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { mutate } from "swr";
import { apiClient } from "@/lib/api-client";
import type { WorkspaceInfo, WorkspaceCreate } from "@/app/types/api";

export function useWorkspaces() {
  return useSWR<{ success: boolean; data: WorkspaceInfo[] }>(
    "/workspaces",
    (url: string) => apiClient.get<WorkspaceInfo[]>(url).then(r => ({
      success: r.success,
      data: r.data ? [r.data] : [], // adjust based on endpoint design
    }))
  );
}

export function useCreateWorkspace() {
  return useSWRMutation(
    "/workspaces",
    async (url: string, { arg }: { arg: WorkspaceCreate }) => {
      const result = await apiClient.post<WorkspaceInfo>(url, arg);
      mutate(key => typeof key === "string" && key === "/workspaces");
      return result;
    }
  );
}

export function useDeleteWorkspace() {
  return useSWRMutation(
    "/workspaces",
    async (_url: string, { arg }: { arg: string }) => {
      const result = await apiClient.delete(`/workspaces/${arg}`);
      mutate(key => typeof key === "string" && key === "/workspaces");
      return result;
    }
  );
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hardcoded WORKSPACES array | Dynamic API-fetched list | Phase 13 | Workspace selector becomes data-driven |
| No DB record for workspaces | Workspace table with CRUD | Phase 13 | Workspaces are persistent, queryable |
| Manual directory creation | Auto-provisioning on create | Phase 13 | New workspaces have full directory structure immediately |

**Deprecated/outdated:**
- `WORKSPACES` constant in `types.ts` -- replaced by API fetch
- `WorkspaceId` literal type -- replaced by `string`

## Open Questions

1. **Should workspace deletion be soft or hard?**
   - What we know: Hard delete removes directory + DB row. Soft delete adds `deleted_at` column.
   - What's unclear: Whether users might accidentally delete and want recovery.
   - Recommendation: Hard delete with confirmation dialog. Simpler, and workspace data is reproducible (agents can regenerate).

2. **Should skills be copied or shared?**
   - What we know: Default workspace has ~10 skill directories under `api/skills/` and `web/skills/`.
   - What's unclear: Whether users want per-workspace skill customization.
   - Recommendation: Copy skills from default on creation. This gives each workspace independent skills that can be customized.

3. **Should workspace list be paginated?**
   - What we know: Most installations will have <20 workspaces. Existing pattern uses pagination.
   - What's unclear: Whether the frontend expects paginated response format.
   - Recommendation: Simple list endpoint (no pagination) -- workspaces are a small set. A `list_workspaces` returning all is simpler than paginated.

4. **Should there be a management page for workspaces?**
   - What we know: The chat page has WorkspaceSelect. ManagementLayout has a sidebar with navigation items.
   - What's unclear: Whether workspace CRUD should be in the chat header or a separate management page.
   - Recommendation: Create/Delete can be in the WorkspaceSelect dropdown (popover with actions). A management page is overkill for this entity.

## Environment Availability

Step 2.6: SKIPPED (no external dependencies identified -- all changes are code/config within the existing project stack. SQLite, Python, Node.js, and all required libraries are already installed and verified.)

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Backend runtime | Yes | 3.13.2 | -- |
| Node.js | Frontend runtime | Yes | 22.14.0 | -- |
| SQLite | Database (via aiosqlite) | Yes | (bundled) | -- |
| FastAPI | REST API | Yes | 0.136.1 | -- |
| SQLAlchemy | ORM | Yes | 2.0.49 | -- |

**Missing dependencies with no fallback:** None

**Missing dependencies with fallback:** N/A

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (Python) |
| Config file | pyproject.toml (no pytest section yet) |
| Quick run command | `python -m pytest tests/test_workspace.py -x -v` |
| Full suite command | `python -m pytest tests/ -x -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| WS-01 | Workspace model creates DB table correctly | unit | `python -m pytest tests/test_workspace.py::test_workspace_model -x` | No -- Wave 0 |
| WS-02 | Workspace service auto-seeds default workspace | unit | `python -m pytest tests/test_workspace.py::test_auto_seed_default -x` | No -- Wave 0 |
| WS-03 | Workspace CRUD creates directory structure | unit | `python -m pytest tests/test_workspace.py::test_create_provisions_dirs -x` | No -- Wave 0 |
| WS-04 | Workspace CRUD copies skills from default | unit | `python -m pytest tests/test_workspace.py::test_create_copies_skills -x` | No -- Wave 0 |
| WS-05 | Cannot delete default workspace | unit | `python -m pytest tests/test_workspace.py::test_cannot_delete_default -x` | No -- Wave 0 |
| WS-06 | Slug generation sanitizes names | unit | `python -m pytest tests/test_workspace.py::test_slugify -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_workspace.py -x -v`
- **Per wave merge:** `python -m pytest tests/ -x -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_workspace.py` -- covers all WS-xx requirements
- [ ] `tests/conftest.py` update -- workspace fixtures (if not present)

## Sources

### Primary (HIGH confidence)
- Code inspection: `src/app/core/workspace.py` -- workspace resolution helpers
- Code inspection: `src/app/db/repositories/base.py` -- BaseRepository generic CRUD
- Code inspection: `src/app/db/services/project_service.py` -- reference service pattern
- Code inspection: `src/app/api/v2/projects.py` -- reference route pattern
- Code inspection: `webui/src/lib/api/useProjects.ts` -- reference SWR hooks pattern
- Code inspection: `webui/src/app/components/WorkspaceSelect.tsx` -- current component
- Code inspection: `webui/src/lib/api-client.ts` -- X-Space-Id header already sent
- Code inspection: `src/app/db/models/project.py` -- reference model pattern
- Code inspection: `src/app/db/utils/file_storage.py` -- directory creation pattern

### Secondary (MEDIUM confidence)
- Phase 7/ROADMAP decisions: workspace isolation already implemented (directory-level)
- Phase 8 architecture: three-layer CRUD pattern established and used consistently

### Tertiary (LOW confidence)
- None -- all findings based on direct code inspection

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in project, verified versions
- Architecture: HIGH -- follows exact pattern from Phases 8-11 (6 existing CRUD entities)
- Pitfalls: HIGH -- based on direct code inspection of type system, directory structure, and existing patterns

**Research date:** 2026-05-20
**Valid until:** 2026-06-20 (stable patterns, no fast-moving dependencies)

## Key Code Paths Referenced

The planner should be aware of these specific files that need modification or serve as reference:

**Backend files to CREATE:**
- `src/app/db/models/workspace.py` (new model)
- `src/app/db/schemas/workspace.py` (new schemas)
- `src/app/db/repositories/workspace_repo.py` (new repository)
- `src/app/db/services/workspace_service.py` (new service with provisioning)
- `src/app/api/v2/workspaces.py` (new routes)

**Backend files to MODIFY:**
- `src/app/db/models/__init__.py` (import Workspace model)
- `src/app/api/__init__.py` (register workspaces router)
- `src/app/api/deps.py` (add WorkspaceServiceDep)

**Frontend files to MODIFY:**
- `webui/src/app/types/types.ts` (remove WORKSPACES constant, change WorkspaceId to string)
- `webui/src/app/types/api.ts` (add WorkspaceInfo, WorkspaceCreate types)
- `webui/src/app/components/WorkspaceSelect.tsx` (fetch from API, add create/delete UI)
- `webui/src/app/chat/page.tsx` (update WorkspaceId type references)
- `webui/src/app/hooks/useChat.ts` (update workspaceId type)

**Frontend files to CREATE:**
- `webui/src/lib/api/useWorkspaces.ts` (SWR hooks)

**Reference files (copy patterns from):**
- `src/app/db/models/project.py` -- model pattern
- `src/app/db/services/project_service.py` -- service pattern
- `src/app/api/v2/projects.py` -- route pattern
- `webui/src/lib/api/useProjects.ts` -- SWR hooks pattern
