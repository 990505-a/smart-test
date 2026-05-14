# Phase 8: FastAPI Backend & Database - Research

**Researched:** 2026-05-14
**Domain:** FastAPI CRUD backend, PostgreSQL/SQLAlchemy async ORM, Agent-DB integration
**Confidence:** HIGH

## Summary

This phase adds a FastAPI CRUD backend (port 8000) alongside the existing LangGraph Agent service (port 2026), backed by a PostgreSQL database with 9 core tables following the classroom schema. The classroom reference code provides a complete, working implementation of the exact architecture needed: layered (API routes -> Services -> Repositories -> Models), async SQLAlchemy 2.0, Pydantic schemas, dependency injection via FastAPI Depends, and Agent tools that write directly to the database via shared session factories.

The primary technical decision is to adapt the classroom's 20+ table model down to the 9 tables specified in D-03, removing Users/auth dependencies and MongoDB, while keeping the same layered architecture. The classroom code uses PostgreSQL UUID primary keys, JSONB columns for flexible data, and async sessions throughout -- all patterns that map directly to our requirements. FastAPI, SQLAlchemy 2.0, asyncpg, and alembic are already installed in the project's virtual environment, reducing setup to configuration only.

**Primary recommendation:** Follow the classroom's layered architecture exactly (Models -> Repositories -> Services -> API routes -> Schemas) and adapt the 9 specified tables by removing User FK references and MongoDB dependencies. Use `async_session_factory` pattern from classroom for both FastAPI endpoints and Agent tools.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** PostgreSQL only + JSONB for flexible data. No MongoDB.
- **D-02:** SQLAlchemy async (2.0 style) as ORM.
- **D-03:** Implement all 9 classroom tables: Projects, Folders, TestCases, TestSteps, TestRuns, TestResults, APIEndpoints, TestScenarios. No Users table (see D-04).
- **D-04:** No user authentication. Single default user, no login flow.
- **D-05:** Agent tools write directly to database via SQLAlchemy session.
- **D-06:** FastAPI serves as the CRUD API layer for frontend management pages (Phase 9). Agent tools bypass FastAPI and write directly to the same database.
- **D-07:** Local filesystem storage under workspace/ directory. No MinIO.
- **D-08:** FastAPI on port 8000 with /api/v2 prefix (matching classroom).

### Claude's Discretion
- Exact directory structure for FastAPI code within src/app/
- Database migration strategy (Alembic vs manual)
- Connection pooling configuration
- Error handling patterns for CRUD endpoints
- Repository/Service layer separation depth
- Pydantic schema design details

### Deferred Ideas (OUT OF SCOPE)
- MinIO object storage -- can add abstract storage interface in future phase
- User authentication (JWT) -- deferred to future phase, not needed for dev
- Redis caching layer -- not needed for current scale
- Alembic migrations -- can add when schema stabilizes
- API rate limiting -- FastAPI middleware, add later if needed
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PLAT-01 | FastAPI app (port 8000), /api/v2 prefix, CORS, dependency injection | Classroom main.py provides exact pattern: create_app() with lifespan, CORS middleware, APIRouter with /api/v2 prefix, deps.py for DI |
| PLAT-02 | PostgreSQL models (SQLAlchemy async): 9 tables | Classroom models/ directory has all 9+ tables with UUIDMixin, TimestampMixin, Mapped types, JSONB columns. Adapt by removing User FKs |
| PLAT-03 | Project management CRUD | Classroom projects.py API route + ProjectService + ProjectRepository provide complete CRUD pattern |
| PLAT-04 | Folder tree management (hierarchical, move/copy, type support) | Classroom Folder model has parent_id self-reference, FolderType enum, recursive tree queries |
| PLAT-05 | Test case CRUD (regular + BDD, version control, custom fields) | Classroom TestCase model has template enum (test_case/test_case_bdd), version field, custom_fields JSONB, TestStep relationship |
| PLAT-06 | Test execution management (TestRun/TestResult, status tracking, stats) | Classroom TestRun has denormalized stats fields, TestRunTestCase join table, TestResult with step-level results |
| PLAT-07 | Local file storage (attachments, scripts, reports) | Replace classroom's MinIO with local filesystem under workspace/. Attachment model stays, object_name becomes relative file path |
| PLAT-08 | Agent tools (save_test_case_to_db, save_test_plan_to_db, etc.) | Classroom test_artifacts_tools.py shows exact pattern: @tool decorator + async_session_factory() context manager for direct DB writes |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.128.0 (installed) / 0.136.1 (latest) | REST API framework | Async-native, auto OpenAPI docs, dependency injection. Matches classroom. |
| SQLAlchemy | 2.0.44 (installed) / 2.0.49 (latest) | Async ORM | 2.0 style with Mapped[], mapped_column, async session. Classroom uses this exact pattern. |
| asyncpg | 0.31.0 (installed/latest) | PostgreSQL async driver | Used via `postgresql+asyncpg://` URL. Only production-ready async PG driver for Python. |
| pydantic | 2.12.4 (installed) | Schema validation | Request/response models, settings. Already in project. |
| pydantic-settings | 2.12.0 (installed) / 2.14.1 (latest) | Configuration management | BaseSettings for .env loading. Already in project. |
| uvicorn | 0.46.0 (installed/latest) | ASGI server | Runs FastAPI on port 8000. Already in project. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| alembic | 1.18.0 (installed) / 1.18.4 (latest) | Database migrations | Deferred per CONTEXT.md, but already installed. Use `create_all` for dev, add Alembic when schema stabilizes. |
| python-dotenv | 1.2.2 (installed) | .env file loading | Settings already use pydantic-settings. Used in start_server.py. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| asyncpg | psycopg (async) | asyncpg is faster and simpler for pure async. psycopg added sync compatibility layer overhead. Classroom uses asyncpg. |
| Alembic (deferred) | Manual create_all | create_all is fine for dev. Alembic when we need schema evolution without data loss. |
| Repository pattern | Direct ORM in services | Repository adds abstraction for testability and reuse. Classroom uses it. Worth the small overhead. |

**Installation:**
No new packages required. All dependencies are already installed in the project's virtual environment. Only need to add `DATABASE_URL` to the existing .env file and update pyproject.toml if version pinning is desired.

**Version verification:**
```
fastapi: 0.128.0 installed, 0.136.1 latest (in sync with classroom pattern)
sqlalchemy: 2.0.44 installed, 2.0.49 latest
asyncpg: 0.31.0 installed (latest)
alembic: 1.18.0 installed, 1.18.4 latest
pydantic-settings: 2.12.0 installed, 2.14.1 latest
uvicorn: 0.46.0 installed (latest)
```

## Architecture Patterns

### Recommended Project Structure
```
src/app/
  api/                      # FastAPI layer (NEW)
    __init__.py             # API router aggregation (api_router)
    deps.py                 # Dependency injection (get_db, service factories)
    v2/                     # /api/v2 route handlers
      __init__.py
      projects.py
      folders.py
      test_cases.py
      test_runs.py
      test_results.py
      api_endpoints.py
      scenarios.py
  db/                       # Database layer (NEW)
    __init__.py
    database.py             # Engine, session factory, get_db, init_db
    models/                 # SQLAlchemy ORM models
      __init__.py           # Import all models for metadata registration
      base.py               # Base, UUIDMixin, TimestampMixin
      project.py
      folder.py
      test_case.py          # TestCase, TestStep, Tag, TestCaseTag
      test_run.py           # TestRun, TestRunTestCase
      test_result.py        # TestResult, TestStepResult
      api_endpoint.py
      test_scenario.py      # TestScenario, ScenarioStep, ScenarioVariable, etc.
      attachment.py         # Attachment model (local file, not MinIO)
    schemas/                # Pydantic request/response models
      __init__.py
      common.py             # SuccessResponse, MessageResponse, ErrorResponse, PaginatedResponse
      pagination.py         # PaginationParams, PaginationInfo
      enums.py              # Priority, TestCaseState, TestResultStatus, etc.
      project.py
      folder.py
      test_case.py
      test_run.py
      test_result.py
      api_endpoint.py
      scenario.py
    repositories/           # Data access layer
      __init__.py
      base.py               # Generic BaseRepository[ModelType]
      project_repo.py
      folder_repo.py
      test_case_repo.py
      test_run_repo.py
      test_result_repo.py
      api_endpoint_repo.py
      scenario_repo.py
    services/               # Business logic layer
      __init__.py
      project_service.py
      folder_service.py
      test_case_service.py
      test_run_service.py
      test_result_service.py
      api_endpoint_service.py
      scenario_service.py
    utils/                  # DB utilities
      __init__.py
      exceptions.py         # AppException hierarchy
      identifier.py         # PR-xxx, TC-xxx, TR-xxx generators
  core/
    config.py               # Extended with database_url, fastapi_port, pg settings
    workspace.py            # Existing - reuse for file storage paths
  agents/
    testcase/
      tools/                # NEW: db_tools.py for save_test_case_to_db, etc.
  fastapi_app.py            # FastAPI create_app() entry point (separate from LangGraph)
start_fastapi.py            # FastAPI server startup script (parallel to start_server.py)
```

### Pattern 1: Layered Architecture (API -> Service -> Repository -> Model)
**What:** Every CRUD operation follows 4-layer separation. API route receives request -> calls Service method -> Service uses Repository for data access -> Repository operates on SQLAlchemy Model.
**When to use:** All CRUD endpoints. This is the classroom pattern and provides clean separation.
**Example:**
```python
# src/app/api/v2/projects.py (API layer)
from src.app.api.deps import ProjectServiceDep, CurrentUserIdDep, DbSessionDep

router = APIRouter(prefix="/projects")

@router.post("", response_model=SuccessResponse[ProjectInfo], status_code=201)
async def create_project(
    data: ProjectCreate,
    service: ProjectServiceDep,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
) -> SuccessResponse[ProjectInfo]:
    project = await service.create_project(data, current_user_id)
    await db.commit()
    return SuccessResponse(success=True, data=project)

# src/app/api/deps.py (Dependency injection)
async def get_project_service(db: AsyncSession = Depends(get_db)) -> ProjectService:
    return ProjectService(db)
ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
```

### Pattern 2: Agent Tools with Direct DB Access
**What:** Agent tools use `async_session_factory()` context manager to create their own sessions, bypassing FastAPI entirely. Both FastAPI and Agent tools share the same engine/session factory.
**When to use:** Agent tools that need to persist data (save_test_case_to_db, save_test_plan_to_db).
**Example:**
```python
# src/app/agents/testcase/tools/db_tools.py
from langchain_core.tools import tool
from src.app.db.database import async_session_factory
from src.app.db.models.test_case import TestCase, TestStep

@tool
async def save_test_case_to_db(
    project_id: str,
    name: str,
    steps: list[dict],
    priority: str = "medium",
    folder_id: str | None = None,
) -> dict:
    """Save a generated test case to the database."""
    async with async_session_factory() as session:
        try:
            # Generate identifier
            identifier = generate_test_case_identifier()
            # Create test case
            test_case = TestCase(
                project_id=UUID(project_id),
                folder_id=UUID(folder_id) if folder_id else None,
                identifier=identifier,
                name=name,
                priority=Priority(priority),
                created_by=DEFAULT_USER_ID,
            )
            session.add(test_case)
            await session.flush()
            # Create steps
            for i, step in enumerate(steps, 1):
                test_step = TestStep(
                    test_case_id=test_case.id,
                    step_number=i,
                    action=step["action"],
                    expected_result=step.get("expected_result"),
                )
                session.add(test_step)
            await session.commit()
            return {"success": True, "test_case_id": str(test_case.id), "identifier": identifier}
        except Exception as e:
            await session.rollback()
            return {"error": str(e)}
```

### Pattern 3: Database Session Management
**What:** Single engine + session factory shared by FastAPI (via Depends) and Agent tools (via context manager). Session auto-commits in FastAPI layer, manual commit in Agent tools.
**When to use:** All database access.
**Example:**
```python
# src/app/db/database.py
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: auto-commit on success, rollback on error."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

async def init_db() -> None:
    """Create all tables (dev mode)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

### Pattern 4: Shared Settings Extension
**What:** Extend existing `src/app/core/config.py` Settings class with PostgreSQL configuration fields, keeping backward compatibility with all existing agent settings.
**When to use:** Configuration only.
**Example:**
```python
# Extend existing src/app/core/config.py
class Settings(BaseSettings):
    # ... existing fields unchanged ...

    # PostgreSQL (Phase 8)
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "smart_test_platform"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
```

### Anti-Patterns to Avoid
- **Putting FastAPI inside LangGraph process:** FastAPI must be a separate process on port 8000. LangGraph runs on port 2026. They share Python code (models, session factory) but not the process.
- **Creating DB sessions at module level:** Sessions must be created per-request. Module-level sessions cause connection leaks and cross-request state pollution.
- **Commit in repository layer:** Commits belong in the API route handler (FastAPI) or tool function (Agent). Repositories should only flush.
- **Synchronous DB calls:** All database operations must use `await`. Never use sync SQLAlchemy sessions.
- **Embedding MinIO/S3 logic in models:** Attachment model stores file metadata only. Actual file I/O goes through a storage utility. This phase uses local filesystem.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Generic CRUD operations | Custom query builders per model | `BaseRepository[ModelType]` generic class | Classroom provides tested pattern with get_by_id, get_all, count, create, update, delete. ~180 lines handles all models. |
| Pagination | Custom offset/limit math | `PaginatedResponse[T]` generic + `PaginationParams` | BrowserStack-compatible HATEOAS pagination with prev/next links. Handles edge cases. |
| Identifier generation | UUID strings or manual counters | `generate_project_identifier()`, `generate_test_case_identifier()` | Classroom pattern: PR-xxx, TC-xxx, TR-xxx with sequence/random. Advisory locks prevent collisions. |
| Error responses | Inconsistent error formats | `ErrorResponse` + `setup_exception_handlers()` | Unified error schema across all endpoints. Handles AppException, HTTPException, RequestValidationError, and generic Exception. |
| Dependency injection | Manual service instantiation in routes | FastAPI `Depends()` with Annotated type aliases | `ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]` pattern is clean, testable, and auto-documented. |
| Database table creation | Raw SQL DDL | `Base.metadata.create_all(engine)` | SQLAlchemy models ARE the schema. create_all reads model metadata. Dev mode only; Alembic for production. |

**Key insight:** The classroom code provides a complete, battle-tested implementation of every pattern needed. The task is adaptation (remove Users, MongoDB, MinIO), not invention.

## Runtime State Inventory

> This phase is greenfield for the backend/database. No existing runtime state needs migration.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None -- PostgreSQL database does not exist yet | Create database, run init_db() to create tables |
| Live service config | None -- FastAPI server does not exist yet | Create start_fastapi.py, run alongside start_server.py |
| OS-registered state | None | -- |
| Secrets/env vars | `.env` file needs `POSTGRES_*` variables added | Code edit to config.py + .env.example update |
| Build artifacts | None | -- |

## Common Pitfalls

### Pitfall 1: UUID vs String Confusion in Foreign Keys
**What goes wrong:** Mixing `str` and `UUID` types when passing IDs between API routes, Pydantic schemas, and SQLAlchemy models causes type errors or silent failures.
**Why it happens:** Pydantic schemas use `str` for UUID fields (JSON serialization), but SQLAlchemy models use `UUID` type. FastAPI auto-converts, but Agent tools receive raw strings.
**How to avoid:** Always convert with `UUID(string_id)` in Agent tools. Use `UUID(as_uuid=True)` consistently in models. Pydantic v2 handles str<->UUID conversion automatically in API routes.
**Warning signs:** `TypeError: expected UUID, got str` in Agent tool calls.

### Pitfall 2: Circular Model Imports
**What goes wrong:** SQLAlchemy models reference each other via relationships (Project has folders, Folder has project). Circular imports cause startup failures.
**Why it happens:** Python evaluates module-level code at import time. `from app.models.project import Project` inside `folder.py` while `project.py` imports `Folder` creates a cycle.
**Why the classroom avoids it:** Classroom uses forward references as strings (`"Folder"` not `Folder`) in relationship() calls, and the `__init__.py` imports all models in dependency order.
**How to avoid:** Use string forward references in `relationship()`. Import models in `models/__init__.py` in dependency order (Base first, then Project, then Folder, etc.). The classroom's main.py shows the exact import order needed.

### Pitfall 3: Session Commit Timing
**What goes wrong:** FastAPI dependency `get_db()` auto-commits on yield return, but if the route handler also calls `await db.commit()`, you get double-commit or "session already committed" errors.
**Why it happens:** The classroom pattern has get_db() yield + commit, AND some routes call `await db.commit()` explicitly.
**How to avoid:** Choose ONE pattern. Either: (a) get_db commits automatically, routes never commit, OR (b) get_db does NOT commit, routes commit explicitly. The classroom uses pattern (b) in some routes. Recommendation: use get_db with auto-commit, remove explicit commits from routes. OR use the classroom pattern where get_db commits but routes that need explicit control use their own session.
**Warning signs:** `PendingRollbackError` or stale data after writes.

### Pitfall 4: Shared Engine Across Processes
**What goes wrong:** FastAPI (port 8000) and LangGraph (port 2026) are separate processes but both import the same `database.py`. SQLAlchemy engines use connection pools that cannot be shared across processes.
**Why it happens:** Both processes load the same module at import time, creating the same engine object. Fork-based process sharing corrupts connection pools.
**How to avoid:** Each process creates its own engine at startup. The `engine` object is created at module import time, which is correct since each process has its own Python interpreter. Just ensure `engine.dispose()` is called in lifespan shutdown.
**Warning signs:** "connection already closed" errors, or data appearing in wrong sessions.

### Pitfall 5: JSONB Column Defaults
**What goes wrong:** `default=dict` on JSONB columns creates a SINGLE mutable dict shared across all instances, causing data cross-contamination.
**Why it happens:** Python mutable default argument anti-pattern applies to SQLAlchemy column defaults.
**How to avoid:** The classroom uses `default=dict` and `default=list` which in SQLAlchemy 2.0 actually creates new instances per row (unlike plain Python). This is safe. But verify this in testing.
**Warning signs:** One test case's `custom_fields` appearing in another test case.

### Pitfall 6: PostgreSQL Not Running
**What goes wrong:** `asyncpg.exceptions.CannotConnectNowError` or `Connection refused` on startup.
**Why it happens:** PostgreSQL is an external service that must be running before FastAPI starts. No automatic startup.
**How to avoid:** Add health check in FastAPI lifespan. Provide clear error message if DB unreachable. Document PostgreSQL startup in README or start script.
**Warning signs:** FastAPI starts but all endpoints return 500.

## Code Examples

Verified patterns from classroom reference code:

### Database Engine and Session Factory
```python
# Source: classroom backend/app/config/database.py
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

engine = create_async_engine(
    settings.postgres_url,     # postgresql+asyncpg://user:pass@host:port/db
    echo=settings.debug,
    pool_pre_ping=True,        # Verify connections before use
    pool_size=10,
    max_overflow=20,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,    # Access attributes after commit
    autocommit=False,
    autoflush=False,
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

### SQLAlchemy Model with JSONB
```python
# Source: classroom backend/app/models/test_case.py
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

class TestCase(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "test_cases"

    project_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    identifier: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    priority: Mapped[Priority] = mapped_column(SQLEnum(Priority), default=Priority.MEDIUM, nullable=False)
    custom_fields: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Relationships use string forward references
    steps: Mapped[list["TestStep"]] = relationship(
        "TestStep", back_populates="test_case", cascade="all, delete-orphan",
        order_by="TestStep.step_number",
    )
```

### FastAPI Lifespan with DB Init
```python
# Source: classroom backend/app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables in dev mode
    if settings.debug:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown: close connection pool
    await engine.dispose()

def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                       allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    app.include_router(api_router)
    return app
```

### Agent Tool Direct DB Write
```python
# Source: classroom backend/app/agents/api/tools/test_artifacts_tools.py
from langchain_core.tools import tool
from app.config.database import async_session_factory

@tool
async def save_test_cases(endpoint_id: str, test_cases: list[dict], project_identifier: str) -> dict:
    async with async_session_factory() as session:
        # Query existing data
        endpoint = await session.execute(select(APIEndpoint).where(APIEndpoint.id == UUID(endpoint_id)))
        # Create/update records
        session.add(attachment)
        await session.commit()
        return {"success": True, "test_cases_count": len(test_cases)}
```

### Generic Base Repository
```python
# Source: classroom backend/app/repositories/base.py
from typing import Generic, TypeVar
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

ModelType = TypeVar("ModelType", bound=Base)

class BaseRepository(Generic[ModelType]):
    def __init__(self, model: Type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session

    async def get_by_id(self, id: UUID) -> Optional[ModelType]:
        result = await self.session.execute(select(self.model).where(self.model.id == id))
        return result.scalar_one_or_none()

    async def count(self) -> int:
        result = await self.session.execute(select(func.count()).select_from(self.model))
        return result.scalar_one()

    async def create(self, **kwargs) -> ModelType:
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SQLAlchemy 1.x query API | SQLAlchemy 2.0 `select()` + `Mapped[]` | SQLAlchemy 2.0 (2023) | Type-safe column access, no more `query.filter()` |
| Sync SQLAlchemy | Async SQLAlchemy with asyncpg | SQLAlchemy 1.4+ (2021) | All DB operations are async, must use `await` |
| Pydantic v1 `class Config` | Pydantic v2 `model_config` dict | Pydantic v2 (2023) | `model_config = {"from_attributes": True}` replaces `class Config` |
| FastAPI `@app.on_event("startup")` | FastAPI lifespan context manager | FastAPI 0.100+ (2023) | `@asynccontextmanager async def lifespan(app)` is the new pattern |
| MongoDB for flexible data | PostgreSQL JSONB | Always available | JSONB provides indexed JSON queries without a second database |

**Deprecated/outdated:**
- `sqlalchemy.orm.query.Query.filter()`: Use `select().where()` in 2.0 style
- `from pydantic import BaseSettings`: Use `from pydantic_settings import BaseSettings`
- `session.query(Model)`: Use `await session.execute(select(Model))`

## Open Questions

1. **PostgreSQL Installation and Database Creation**
   - What we know: The project requires PostgreSQL running locally. asyncpg is installed. The connection URL defaults to `localhost:5432`.
   - What's unclear: Whether PostgreSQL is installed on the development machine. The `psql` and `pg_isready` commands were not found, suggesting PostgreSQL may not be installed or not on PATH.
   - Recommendation: Add PostgreSQL installation and database creation as a Wave 0 prerequisite task. The plan should include instructions for creating the `smart_test_platform` database.

2. **Model Simplification Scope**
   - What we know: The classroom has 20+ models including Users, Teams, Tags, Attachments, Configurations, TestPlans, APITests, WebTests, WebFunctions, etc. D-03 says "all 9 classroom tables" but lists 8 model names.
   - What's unclear: Whether Tag/TestCaseTag, Attachment, TestPlan (referenced by TestRun.test_plan_id) should be included. TestRun references TestPlan via FK, so TestPlan may be needed.
   - Recommendation: Include the minimum set needed for FK integrity: Projects, Folders, TestCases, TestSteps, TestRuns, TestRunTestCase, TestResults, TestStepResults, APIEndpoints, TestScenarios (with sub-tables). Add Attachment model for file metadata. Add Tag/TestCaseTag if test case tagging is needed in Phase 9. TestPlan is optional -- can make test_plan_id nullable.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.13 | Runtime | Available | 3.13.2 | -- |
| FastAPI | REST API | Available | 0.128.0 | -- |
| SQLAlchemy | ORM | Available | 2.0.44 | -- |
| asyncpg | PostgreSQL driver | Available | 0.31.0 | -- |
| alembic | Migrations (deferred) | Available | 1.18.0 | Use create_all for dev |
| uvicorn | ASGI server | Available | 0.46.0 | -- |
| pydantic-settings | Config | Available | 2.12.0 | -- |
| PostgreSQL | Database | Not verified | -- | Must install/configure |

**Missing dependencies with no fallback:**
- PostgreSQL server: Must be installed and `smart_test_platform` database created before backend can start. This is a blocking prerequisite.

**Missing dependencies with fallback:**
- None -- all Python packages are installed.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (already in use) |
| Config file | None -- uses conftest.py and auto-discovery |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PLAT-01 | FastAPI app creates with /api/v2 prefix, CORS, health check | unit | `pytest tests/test_fastapi_app.py -x` | Wave 0 |
| PLAT-02 | All 9 models create tables with correct columns/relationships | unit | `pytest tests/test_db_models.py -x` | Wave 0 |
| PLAT-03 | Project CRUD (create, read, update, delete) | unit | `pytest tests/test_project_api.py -x` | Wave 0 |
| PLAT-04 | Folder tree: create, move, hierarchical query | unit | `pytest tests/test_folder_api.py -x` | Wave 0 |
| PLAT-05 | Test case CRUD with steps, BDD template, version | unit | `pytest tests/test_testcase_api.py -x` | Wave 0 |
| PLAT-06 | Test run creation with result tracking | unit | `pytest tests/test_testrun_api.py -x` | Wave 0 |
| PLAT-07 | File upload/save to local filesystem | unit | `pytest tests/test_file_storage.py -x` | Wave 0 |
| PLAT-08 | Agent tool save_test_case_to_db writes to DB | unit | `pytest tests/test_db_tools.py -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_db*.py tests/test_fastapi*.py -x -q`
- **Per wave merge:** `pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_fastapi_app.py` -- covers PLAT-01 (app creation, CORS, health check)
- [ ] `tests/test_db_models.py` -- covers PLAT-02 (model table creation)
- [ ] `tests/test_project_api.py` -- covers PLAT-03 (project CRUD)
- [ ] `tests/test_folder_api.py` -- covers PLAT-04 (folder tree management)
- [ ] `tests/test_testcase_api.py` -- covers PLAT-05 (test case CRUD)
- [ ] `tests/test_testrun_api.py` -- covers PLAT-06 (test run management)
- [ ] `tests/test_file_storage.py` -- covers PLAT-07 (file storage)
- [ ] `tests/test_db_tools.py` -- covers PLAT-08 (agent DB tools)
- [ ] `tests/conftest.py` -- add async DB fixtures (async engine, test session, test client)

## Sources

### Primary (HIGH confidence)
- Classroom reference code at `d:/test_agent/2026-05-13-ai-test-agent-system-platform/ai-test-agent-system-platform/backend/app/` -- Complete working implementation of the exact architecture needed
- Installed package versions verified via `pip show` and `pip index versions`
- SQLAlchemy 2.0 documentation patterns confirmed in classroom code (Mapped[], mapped_column, async session)

### Secondary (MEDIUM confidence)
- FastAPI lifespan pattern verified against both classroom code and current FastAPI documentation
- PostgreSQL JSONB capabilities confirmed as adequate replacement for MongoDB (indexed queries, nested documents)

### Tertiary (LOW confidence)
- PostgreSQL installation status on development machine -- `psql` and `pg_isready` not found on PATH, but this may be a PATH configuration issue rather than missing installation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- All packages already installed, versions verified against PyPI
- Architecture: HIGH -- Classroom provides complete reference implementation of identical architecture
- Pitfalls: HIGH -- Based on classroom code analysis and SQLAlchemy/FastAPI well-known issues
- Agent-DB integration: HIGH -- Classroom test_artifacts_tools.py provides working pattern

**Research date:** 2026-05-14
**Valid until:** 2026-06-14 (stable libraries, low risk of breaking changes)
