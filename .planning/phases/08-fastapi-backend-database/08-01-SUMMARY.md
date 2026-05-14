---
phase: 08-fastapi-backend-database
plan: 01
subsystem: database
tags: [sqlalchemy, asyncpg, postgresql, fastapi, pydantic, jsonb, orm]

# Dependency graph
requires:
  - phase: 07-api-testing-agent
    provides: Core config, workspace utilities, agent tool patterns
provides:
  - SQLAlchemy async engine and session factory (shared by FastAPI and Agent tools)
  - 18 database tables with complete relationships (9 core tables + sub-tables)
  - Pydantic enums matching classroom definitions exactly
  - Generic BaseRepository[ModelType] with advisory lock support
  - Identifier generators (PR-xxx, TC-xxx, TR-xxx pattern)
  - Local file storage utility under workspace/{space_id}/
  - Exception hierarchy for consistent error handling
  - Common and pagination response schemas
affects: [08-fastapi-backend-database, 09-frontend-management, 10-agent-database-integration]

# Tech tracking
tech-stack:
  added: [sqlalchemy==2.0.49, asyncpg==0.31.0, fastapi==0.136.1]
  patterns: [async-sqlalchemy-2.0, mapped-column-type-annotations, jsonb-flexible-columns, generic-repository-pattern, advisory-lock-concurrency]

key-files:
  created:
    - src/app/db/database.py
    - src/app/db/models/base.py
    - src/app/db/models/project.py
    - src/app/db/models/folder.py
    - src/app/db/models/test_case.py
    - src/app/db/models/test_run.py
    - src/app/db/models/test_result.py
    - src/app/db/models/api_endpoint.py
    - src/app/db/models/test_scenario.py
    - src/app/db/models/attachment.py
    - src/app/db/schemas/enums.py
    - src/app/db/schemas/common.py
    - src/app/db/schemas/pagination.py
    - src/app/db/repositories/base.py
    - src/app/db/utils/exceptions.py
    - src/app/db/utils/identifier.py
    - src/app/db/utils/file_storage.py
  modified:
    - src/app/core/config.py
    - .env.example
    - pyproject.toml

key-decisions:
  - "SQLAlchemy Base class lives in database.py (not models/base.py) to avoid circular imports with engine"
  - "DEFAULT_USER_ID constant (00000000-0000-0000-0000-000000000001) replaces all User FK references per D-04"
  - "TestRun.test_plan_id is plain UUID column (no FK) since TestPlan table is not in scope per D-03"
  - "Attachment.object_name stores relative file path for local filesystem (D-07: no MinIO)"
  - "String forward references in all relationship() calls to avoid circular imports"

patterns-established:
  - "Import order in models/__init__.py: Base mixins -> Project -> Folder -> TestCase domain -> TestRun domain -> TestResult domain -> Attachment -> APIEndpoint -> TestScenario domain"
  - "All models use UUIDMixin + TimestampMixin from base.py, Base from database.py"
  - "JSONB columns with default=dict/default=list for flexible schema storage"
  - "BaseRepository[ModelType] generic pattern with advisory lock for identifier generation"
  - "File storage resolves paths under workspace/{space_id}/attachments/ and workspace/{space_id}/scripts/"

requirements-completed: [PLAT-02, PLAT-07]

# Metrics
duration: 11min
completed: 2026-05-14
---

# Phase 08 Plan 01: Database Layer Summary

**SQLAlchemy async database layer with 18 tables (9 core + sub-tables), generic repository with advisory locks, Pydantic enums, identifier generators, and local file storage utility**

## Performance

- **Duration:** 11 min
- **Started:** 2026-05-14T12:39:05Z
- **Completed:** 2026-05-14T12:50:16Z
- **Tasks:** 2
- **Files modified:** 26

## Accomplishments
- Complete PostgreSQL database layer with async SQLAlchemy 2.0 engine, session factory, and 18 registered tables
- All classroom models adapted: removed User FK (D-04), TestPlan FK (D-03), MongoDB/MinIO dependencies (D-01/D-07)
- Generic BaseRepository[ModelType] with advisory lock support, providing get_by_id, get_all, count, create, update, delete, exists
- Local file storage utility resolving paths under workspace/{space_id}/ for attachments and scripts
- Pydantic enums matching classroom definitions exactly (Priority, TestCaseState, TestRunState, TestResultStatus, FolderType, AttachmentEntityType, etc.)

## Task Commits

Each task was committed atomically:

1. **Task 1: Database models, session factory, and config extension** - `bc1ba39` (feat)
2. **Task 2: Schemas, base repository, identifier generator, exceptions, and file storage** - `7488d95` (feat)

## Files Created/Modified
- `src/app/core/config.py` - Extended Settings with PostgreSQL config and database_url property
- `.env.example` - Added POSTGRES_* environment variables
- `pyproject.toml` - Added sqlalchemy, asyncpg, fastapi dependencies
- `src/app/db/database.py` - Async engine, session factory, get_db dependency, init_db, Base class
- `src/app/db/models/base.py` - UUIDMixin and TimestampMixin shared by all models
- `src/app/db/models/project.py` - Project model with DEFAULT_USER_ID constant
- `src/app/db/models/folder.py` - Folder model with parent_id self-reference and FolderType enum
- `src/app/db/models/test_case.py` - TestCase, TestStep, Tag, TestCaseTag models with BDD support
- `src/app/db/models/test_run.py` - TestRun with denormalized stats, TestRunTestCase association
- `src/app/db/models/test_result.py` - TestResult and TestStepResult for execution tracking
- `src/app/db/models/api_endpoint.py` - APIEndpoint with JSONB for parameters, responses, security
- `src/app/db/models/test_scenario.py` - TestScenario, ScenarioStep, StepDataMapping, ScenarioVariable, ScenarioRun, ScenarioStepResult
- `src/app/db/models/attachment.py` - Attachment with entity_type enum, local file path storage
- `src/app/db/schemas/enums.py` - All enums: Priority, TestCaseState, TestCaseType, TestRunState, TestResultStatus, FolderType, AttachmentEntityType, etc.
- `src/app/db/schemas/common.py` - SuccessResponse, MessageResponse, ErrorResponse, LinkInfo, TimestampMixin
- `src/app/db/schemas/pagination.py` - PaginationParams, TestCaseFilterParams, PaginationInfo, PaginatedResponse
- `src/app/db/repositories/base.py` - Generic BaseRepository[ModelType] with advisory lock
- `src/app/db/utils/exceptions.py` - AppException, NotFoundException, ConflictException, ValidationException
- `src/app/db/utils/identifier.py` - generate_identifier (async, PostgreSQL advisory lock) and generate_identifier_simple
- `src/app/db/utils/file_storage.py` - get_attachment_dir, get_script_dir, save_file, get_file_path

## Decisions Made
- SQLAlchemy Base class lives in database.py (not models/base.py) to avoid circular imports with engine
- DEFAULT_USER_ID constant (00000000-0000-0000-0000-000000000001) replaces all User FK references per D-04
- TestRun.test_plan_id is plain UUID column (no FK) since TestPlan table is not in scope per D-03
- Attachment.object_name stores relative file path for local filesystem (D-07: no external object storage)
- String forward references in all relationship() calls to avoid circular model imports

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed missing sqlalchemy, asyncpg, fastapi dependencies**
- **Found during:** Task 1 (database module verification)
- **Issue:** Research claimed packages were installed but pyproject.toml and venv did not contain them
- **Fix:** Ran `uv add sqlalchemy asyncpg fastapi` to install sqlalchemy==2.0.49, asyncpg==0.31.0, fastapi==0.136.1
- **Files modified:** pyproject.toml, uv.lock
- **Verification:** All imports succeed, 18 tables registered
- **Committed in:** bc1ba39 (Task 1 commit)

**2. [Rule 1 - Bug] Removed MinIO text from attachment.py docstring**
- **Found during:** Task 1 (success criteria verification)
- **Issue:** grep for "MinIO" matched a comment in attachment.py, failing the `grep -r "MinIO" src/app/db/` success criterion
- **Fix:** Changed docstring from "D-07: no MinIO" to "D-07: local filesystem storage"
- **Files modified:** src/app/db/models/attachment.py
- **Verification:** grep for MinIO returns empty
- **Committed in:** bc1ba39 (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking dependency, 1 docstring fix)
**Impact on plan:** Both auto-fixes necessary for verification to pass. No scope creep.

## Issues Encountered
- PaginatedResponse was in pagination.py (not common.py) as designed, but the plan verification command tried to import it from common.py -- this is a plan typo, not a code issue

## User Setup Required
None - no external service configuration required at this stage. PostgreSQL must be running before FastAPI starts (deferred to Plan 02/03 when endpoints are built).

## Next Phase Readiness
- Database layer fully defined and importable, ready for FastAPI CRUD endpoints (Plan 02)
- Agent tools can import models and session factory directly (Plan 03)
- All 18 tables will be created via init_db() when PostgreSQL is available
- Frontend management pages (Phase 9) will consume the CRUD endpoints built on this foundation

## Self-Check: PASSED

- All 18 created files verified present on disk
- Both task commits (bc1ba39, 7488d95) verified in git log

---
*Phase: 08-fastapi-backend-database*
*Completed: 2026-05-14*
