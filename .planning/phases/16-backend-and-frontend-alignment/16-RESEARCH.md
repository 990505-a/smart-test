# Phase 16: Backend and Frontend Alignment - Research

**Researched:** 2026-05-21
**Domain:** Backend model/route/service layering, Next.js frontend pages, alignment with classroom codebase
**Confidence:** HIGH

## Summary

Phase 16 closes the gap between our platform and the classroom reference implementation by adding three missing backend endpoint groups (web_tests, web_functions, configurations), their corresponding database models (WebFunction, WebSubFunction, WebTest, WebTestRun, WebTestResult, Configuration), services, Pydantic schemas, and frontend pages. The work follows the exact same layered architecture pattern established in Phases 8-11: SQLAlchemy model -> Pydantic schema -> repository -> service -> FastAPI route -> SWR hook -> Next.js page.

The most substantial new domain is the WebFunction/WebSubFunction model pair. Phase 15 implemented these as JSON file storage in the web agent tools (`function_tools.py`). Phase 16 migrates this to proper database models while keeping the agent tools backward-compatible until a future migration. The Configuration model is simple (integer PK, OS/browser/device combos) and follows the BrowserStack API pattern already used for our schema design.

Frontend alignment involves adding project-dimension routing (`/projects/[id]/web-tests`), a web-tests management page with folder tree and function/sub-function panels, and configuration management. The classroom's fullstack-analysis page is just an iframe wrapper for gitnexus-web, which we already have at `/code-analysis`. The test-plans page uses mock data in the classroom and is a lower priority.

**Primary recommendation:** Follow the existing layered pattern exactly (model -> schema -> repo -> service -> route -> deps). Use `sqlalchemy.JSON` not PostgreSQL `JSONB` since we run on SQLite. Keep Phase 15's JSON file tools working alongside new DB routes during transition.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | 2.x (existing) | ORM | Already in project since Phase 8, async engine with aiosqlite |
| FastAPI | 0.115+ (existing) | REST API | Already in project since Phase 8 |
| Pydantic | 2.x (existing) | Schema validation | Already in project, used for all request/response schemas |
| Next.js | 15.4.4 (existing) | Frontend | Already in project since Phase 1 |
| SWR | 2.x (existing) | Data fetching | Already in project since Phase 9 |
| Shadcn/ui | latest (existing) | Component library | Already in project since Phase 1 |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| @monaco-editor/react | 4.x (new) | Code editor | Script viewing/editing in web-tests and api-tests pages |
| lucide-react | existing | Icons | New page icons for navigation |
| sonner | existing | Toast notifications | CRUD operation feedback |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| @monaco-editor/react | CodeMirror | Monaco is the VS Code editor, classroom uses it, better language support |
| SWR (existing) | React Query | SWR is already established in the project, no reason to switch |

**Installation:**
```bash
# Frontend only - Monaco editor
cd webui && npm install @monaco-editor/react
```

**Version verification:** Run `npm view @monaco-editor/react version` before implementing to confirm current version.

## Architecture Patterns

### Recommended Project Structure (new files only)
```
src/app/db/models/
  web_function.py          # WebFunction + WebSubFunction models
  web_test.py              # WebTest + WebTestRun + WebTestResult models
  configuration.py         # Configuration model

src/app/db/schemas/
  web_function.py          # Pydantic schemas for web function CRUD
  web_test.py              # Pydantic schemas for web test CRUD
  configuration.py         # Pydantic schemas for configuration CRUD

src/app/db/repositories/
  web_function_repo.py     # WebFunction + WebSubFunction repository
  web_test_repo.py         # WebTest repository
  configuration_repo.py    # Configuration repository

src/app/db/services/
  web_function_service.py  # WebFunction + WebSubFunction business logic
  web_test_service.py      # WebTest business logic
  configuration_service.py # Configuration business logic

src/app/api/v2/
  web_functions.py         # Web function/sub-function routes
  web_tests.py             # Web test CRUD routes
  configurations.py        # Configuration routes

webui/src/app/
  web-tests/               # Web tests management page
    page.tsx
    components/
  web-tests/[id]/          # (optional detail pages)
  projects/[id]/           # Project-scoped routing (NEW pattern)

webui/src/lib/api/
  useWebFunctions.ts       # SWR hooks for web functions
  useWebTests.ts           # SWR hooks for web tests
  useConfigurations.ts     # SWR hooks for configurations
```

### Pattern 1: Layered Architecture (existing pattern)
**What:** Model -> Schema -> Repository -> Service -> Route -> Deps registration
**When to use:** Every new database entity follows this exact pattern
**Example:**
```python
# Model: src/app/db/models/web_function.py
from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.app.db.database import Base
from src.app.db.models.base import TimestampMixin, UUIDMixin

class WebFunction(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "web_functions"
    project_id: Mapped[str] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    identifier: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(500), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    # ... (adapted from classroom, using JSON not JSONB for SQLite)
    navigation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    sub_functions: Mapped[list["WebSubFunction"]] = relationship("WebSubFunction", back_populates="function", cascade="all, delete-orphan")
```

### Pattern 2: SQLite adaptation from PostgreSQL models
**What:** Classroom uses PostgreSQL-specific features (UUID with as_uuid=True, JSONB). We use generic SQLAlchemy equivalents.
**When to use:** Every model adapted from classroom
**Example:**
```python
# Classroom (PostgreSQL):
from sqlalchemy.dialects.postgresql import UUID, JSONB
project_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ...)

# Our project (SQLite-compatible):
from sqlalchemy import Uuid, JSON
project_id: Mapped[str] = mapped_column(Uuid, ForeignKey("projects.id"), ...)

# Classroom JSONB -> Our JSON
navigation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
```

### Pattern 3: FastAPI route with lazy service import
**What:** Route files use lazy imports for services to avoid circular dependencies
**When to use:** All new route files
**Example:**
```python
# src/app/api/v2/web_functions.py
from src.app.api.deps import DbSessionDep, PaginationDep

async def _get_web_function_service(db: DbSessionDep):
    from src.app.db.services.web_function_service import WebFunctionService
    return WebFunctionService(db)

@router.post("")
async def create_web_function(project_id, data, db: DbSessionDep):
    svc = await _get_web_function_service(db)
    result = await svc.create_web_function(project_id, data)
    await db.commit()
    return SuccessResponse(success=True, data=result)
```

### Pattern 4: SWR hook for new entities
**What:** Follow useProjects.ts pattern for new API hooks
**When to use:** Every new backend endpoint group
**Example:**
```typescript
// webui/src/lib/api/useWebFunctions.ts
export function useWebFunctions(projectId: string, page: number = 1, pageSize: number = 20) {
  return useSWR<PaginatedResponse<WebFunctionInfo>>(
    projectId ? [`/projects/${projectId}/web-functions`, page, pageSize] : null,
    ([url, p, ps]) => apiClient.getPaginated<WebFunctionInfo>(url, { p, page_size: ps })
  );
}
```

### Anti-Patterns to Avoid
- **Using PostgreSQL JSONB:** Our DB is SQLite. Use `sqlalchemy.JSON` instead. JSONB is PostgreSQL-specific and will fail on SQLite.
- **Direct UUID import from postgresql dialect:** Use `sqlalchemy.Uuid` not `sqlalchemy.dialects.postgresql.UUID`.
- **Using PostgreSQL advisory locks for new repos:** `_acquire_xact_lock` calls `pg_advisory_xact_lock` which only works on PostgreSQL. New repos should use SQLite-compatible identifier generation (e.g., application-level UUID or counter).
- **Duplicating agent JSON tools:** Phase 15's `function_tools.py` reads/writes JSON files. Phase 16 adds DB models. Do NOT remove the JSON tools yet; they need a migration plan.
- **Monaco editor as global dependency:** Load Monaco only in pages that need it, not in the root layout.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| CRUD boilerplate | Custom per-entity SQL | BaseRepository generic class | Already exists in `src/app/db/repositories/base.py` |
| Pagination logic | Custom offset/limit math | PaginationParams + PaginationInfo | Already exists in `src/app/db/schemas/pagination.py` |
| Response wrapping | Custom response objects | SuccessResponse, MessageResponse | Already exists in `src/app/db/schemas/common.py` |
| Identifier generation | Custom ID logic | generate_identifier() utility | Already exists in `src/app/db/utils/identifier.py` |
| DB session management | Manual session creation | get_db() + async_session_factory() | Already exists in `src/app/db/database.py` |
| Code editor | Custom textarea with syntax highlighting | @monaco-editor/react | Monaco handles 100+ languages, linting, diff view |

**Key insight:** Every piece of infrastructure needed for this phase already exists from Phases 8-11. The work is purely additive: new models, schemas, repos, services, routes, and pages that follow existing patterns.

## Common Pitfalls

### Pitfall 1: JSONB vs JSON Column Type
**What goes wrong:** Copying classroom models directly uses `JSONB` from `sqlalchemy.dialects.postgresql`, which fails on SQLite with "unknown type JSONB" errors.
**Why it happens:** Classroom uses PostgreSQL; we use SQLite.
**How to avoid:** Always replace `JSONB` with `JSON` from core sqlalchemy. Replace `UUID(as_uuid=True)` with `Uuid` from core sqlalchemy.
**Warning signs:** Import errors mentioning `sqlalchemy.dialects.postgresql` at model import time.

### Pitfall 2: Missing __init__.py Model Registration
**What goes wrong:** New models are created but not imported in `src/app/db/models/__init__.py`, so `Base.metadata.create_all()` never creates the tables.
**Why it happens:** SQLAlchemy requires all model classes to be imported before `create_all` is called.
**How to avoid:** Add imports for WebFunction, WebSubFunction, WebTest, WebTestRun, WebTestResult, and Configuration to `__init__.py` in dependency order.
**Warning signs:** API returns 404 for new endpoints, but no table creation errors in logs.

### Pitfall 3: Router Registration Omission
**What goes wrong:** New route files are created but never included in `src/app/api/__init__.py`'s `api_router`.
**Why it happens:** Easy to forget the final wiring step.
**How to avoid:** Add `api_router.include_router(web_functions.router, tags=["Web Functions"])` etc. to the api router registration file.
**Warning signs:** Endpoints return 404 at `/api/v2/...` but FastAPI docs at `/docs` don't show them.

### Pitfall 4: Project Model Missing Relationships
**What goes wrong:** New models define relationships back to Project (e.g., `project: Mapped["Project"] = relationship("Project", back_populates="web_functions")`), but the Project model doesn't have the corresponding `web_functions` relationship defined.
**Why it happens:** Bidirectional SQLAlchemy relationships require both sides.
**How to avoid:** Add `web_functions`, `web_tests`, and `web_sub_functions` relationship lists to `src/app/db/models/project.py`.
**Warning signs:** `InvalidRequestError` or `AutowireInProgressError` at runtime.

### Pitfall 5: SWR Cache Key Collisions
**What goes wrong:** New SWR hooks use the same cache key format as existing hooks, causing data to be mixed.
**Why it happens:** SWR uses the key as cache identifier.
**How to avoid:** Use the full URL path including project ID: `["/projects/${projectId}/web-functions", page, pageSize]`.
**Warning signs:** Page shows data from wrong endpoint after navigation.

### Pitfall 6: Dependency Injection Not Updated
**What goes wrong:** New service dependencies not added to `src/app/api/deps.py`, so routes cannot inject services.
**Why it happens:** Deps file needs explicit registration for each new service.
**How to avoid:** Add `WebFunctionServiceDep`, `WebTestServiceDep`, `ConfigurationServiceDep` to deps.py.
**Warning signs:** Import errors when route files try to use the dependency.

## Code Examples

### WebFunction Model (adapted for SQLite)
```python
# Source: adapted from classroom backend/app/models/web_function.py
# Key changes: UUID -> Uuid, JSONB -> JSON, removed PostgreSQL-specific imports
from sqlalchemy import JSON, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.app.db.database import Base
from src.app.db.models.base import TimestampMixin, UUIDMixin

class WebFunction(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "web_functions"
    __table_args__ = {"comment": "Web function definitions"}

    project_id: Mapped[str] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    folder_id: Mapped[str | None] = mapped_column(Uuid, ForeignKey("folders.id", ondelete="SET NULL"), nullable=True, index=True)
    identifier: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(500), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    business_module: Mapped[str | None] = mapped_column(String(200), nullable=True)
    navigation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    pages: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    custom_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    total_sub_functions: Mapped[int] = mapped_column(Integer, default=0)
    total_test_cases: Mapped[int] = mapped_column(Integer, default=0)
    total_test_runs: Mapped[int] = mapped_column(Integer, default=0)
    last_run_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    sub_functions: Mapped[list["WebSubFunction"]] = relationship(
        "WebSubFunction", back_populates="function", cascade="all, delete-orphan",
        order_by="WebSubFunction.sort_order"
    )
```

### Configuration Route (simplest new endpoint)
```python
# Source: adapted from classroom backend/app/api/v2/configurations.py
from fastapi import APIRouter, status
from src.app.api.deps import DbSessionDep, PaginationDep
from src.app.db.schemas.common import SuccessResponse

router = APIRouter(prefix="/configurations")

async def _get_configuration_service(db: DbSessionDep):
    from src.app.db.services.configuration_service import ConfigurationService
    return ConfigurationService(db)

@router.get("", response_model=SuccessResponse)
async def list_configurations(db: DbSessionDep, pagination: PaginationDep):
    svc = await _get_configuration_service(db)
    items, total = await svc.get_list(offset=pagination.offset, limit=pagination.limit)
    return SuccessResponse(success=True, data=items)

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_configuration(data: dict, db: DbSessionDep):
    svc = await _get_configuration_service(db)
    result = await svc.create(data)
    await db.commit()
    return SuccessResponse(success=True, data=result)
```

### SWR Hook for Web Functions
```typescript
// Source: following existing useProjects.ts pattern
import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { apiClient } from "@/lib/api-client";

export function useWebFunctions(projectId: string, page = 1, pageSize = 20) {
  return useSWR(
    projectId ? [`/projects/${projectId}/web-functions`, page, pageSize] : null,
    ([url, p, ps]) => apiClient.getPaginated(url, { p, page_size: ps })
  );
}

export function useCreateWebFunction(projectId: string) {
  return useSWRMutation(
    `/projects/${projectId}/web-functions`,
    async (url: string, { arg }) => {
      const result = await apiClient.post(url, arg);
      return result;
    }
  );
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| JSON file storage for web functions | Database models (WebFunction, WebSubFunction) | Phase 16 | Persistent, queryable, transactional |
| Flat frontend routing (/cases, /runs) | Project-scoped routing (/projects/[id]/web-tests) | Phase 16 | Better organization, matches classroom |
| No configuration management | Configuration CRUD API | Phase 16 | Browser/device/OS config for test runs |
| No code editor in UI | Monaco editor integration | Phase 16 | Script viewing/editing capability |

**Deprecated/outdated:**
- Phase 15's JSON file tools (`function_tools.py`): Still needed for agent operation, but Phase 16 adds parallel DB-backed API endpoints. Full migration of agent tools to DB is a future task.

## Open Questions

1. **Project-scoped routing vs flat routing**
   - What we know: Classroom uses `/projects/[projectId]/web-tests` structure. Our current frontend uses flat routes like `/api-tests`, `/cases`.
   - What's unclear: Whether to refactor ALL existing pages to project-scoped routing, or only add new pages with project-scoped routing.
   - Recommendation: Only add project-scoped routing for NEW pages (web-tests, configurations). Existing pages can be refactored in a future phase. This keeps scope manageable.

2. **Monaco editor scope**
   - What we know: Classroom uses Monaco for script viewing/editing in web-tests and api-tests pages.
   - What's unclear: Whether to integrate Monaco into existing api-tests pages in this phase or only add it to new web-tests pages.
   - Recommendation: Add Monaco to new web-tests pages. Integration into existing pages can be a separate task.

3. **Agent tool migration (JSON -> DB)**
   - What we know: Phase 15's `function_tools.py` uses JSON files. Phase 16 adds DB models. STATE.md notes "Phase 16 adds WebFunction/WebSubFunction DB models."
   - What's unclear: Whether agent tools should be rewritten to use DB in this phase or remain JSON-based.
   - Recommendation: Keep agent tools as-is (JSON-based). Add DB-backed REST API endpoints for frontend. A future "tool migration" task can connect agent tools to the DB.

4. **Test-plans page**
   - What we know: Classroom's test-plans page uses mock data (not connected to backend). Our requirements don't have a test_plans table.
   - What's unclear: Whether to include this page at all.
   - Recommendation: Skip test-plans page in this phase. It's mock-only in the classroom and has no backend model.

5. **Fullstack-analysis page**
   - What we know: Classroom's fullstack-analysis page is just an iframe to gitnexus-web. We already have `/code-analysis` doing exactly this.
   - What's unclear: Whether to add a duplicate route or just link to existing.
   - Recommendation: Skip. Our `/code-analysis` page already provides this functionality.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| SQLite | Data layer | Yes | aiosqlite (existing) | -- |
| FastAPI | REST API | Yes | 0.115+ (existing) | -- |
| Next.js | Frontend | Yes | 15.4.4 (existing) | -- |
| npm (for Monaco) | Frontend package | Yes | existing | -- |
| SWR | Data fetching | Yes | 2.x (existing) | -- |

**Missing dependencies with no fallback:**
- None. All infrastructure is in place from prior phases.

**Missing dependencies with fallback:**
- `@monaco-editor/react` needs `npm install` in webui/ -- not yet installed but trivial to add.

## Sources

### Primary (HIGH confidence)
- Classroom source code at `D:\test_agent\2026-05-20-ai-test-agent-system-platform\ai-test-agent-system-platform\` -- all model, route, service, schema, and frontend files examined directly
- Existing project codebase -- all patterns verified by reading actual source files (models, routes, services, schemas, frontend hooks, types, components)
- CLASSROOM-DIFF-2026-05-20.md -- comprehensive gap analysis report

### Secondary (MEDIUM confidence)
- Phase 15 STATE.md entries -- confirming JSON file storage pattern and planned DB migration
- Phase 8-11 accumulated context in STATE.md -- confirming layered architecture pattern is established

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all libraries already in project, only Monaco is new
- Architecture: HIGH - follows exact same layered pattern from Phases 8-11
- Pitfalls: HIGH - identified from direct comparison of classroom (PostgreSQL) vs our codebase (SQLite)
- Frontend: HIGH - follows existing SWR + Shadcn patterns, classroom provides reference implementations
- Models: HIGH - classroom models read directly, SQLite adaptations well-understood

**Research date:** 2026-05-21
**Valid until:** 2026-06-21 (stable patterns, no fast-moving dependencies)
