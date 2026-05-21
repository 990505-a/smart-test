---
phase: 16-backend-and-frontend-alignment
plan: 01
subsystem: database, api
tags: [sqlalchemy, fastapi, sqlite, web-functions, web-tests, configurations, crud, pydantic]

# Dependency graph
requires:
  - phase: 08-database-layer
    provides: SQLAlchemy Base, UUIDMixin, TimestampMixin, BaseRepository, database session infrastructure
  - phase: 11-api-test-execution-engine
    provides: APITest model pattern, api_test_service/repo/route patterns to follow
provides:
  - WebFunction + WebSubFunction SQLAlchemy models with bidirectional relationships
  - WebTest + WebTestRun + WebTestResult SQLAlchemy models
  - Configuration SQLAlchemy model (integer PK)
  - 3 schema files with Create/Update/Info Pydantic schemas
  - 3 repository files with scoped query methods
  - 3 service files with business logic and identifier generation
  - 3 route files with 25 total endpoints (10+9+6)
  - Service dependency registrations in deps.py
  - Router registrations in api/__init__.py
affects: [16-02, frontend-pages, agent-tool-migration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Integer PK model (Configuration) for non-UUID entities"
    - "Sub-function nested CRUD within parent route prefix"
    - "System configuration filter endpoint (GET /configurations/system)"

key-files:
  created:
    - src/app/db/models/web_function.py
    - src/app/db/models/web_test.py
    - src/app/db/models/configuration.py
    - src/app/db/schemas/web_function.py
    - src/app/db/schemas/web_test.py
    - src/app/db/schemas/configuration.py
    - src/app/db/repositories/web_function_repo.py
    - src/app/db/repositories/web_test_repo.py
    - src/app/db/repositories/configuration_repo.py
    - src/app/db/services/web_function_service.py
    - src/app/db/services/web_test_service.py
    - src/app/db/services/configuration_service.py
    - src/app/api/v2/web_functions.py
    - src/app/api/v2/web_tests.py
    - src/app/api/v2/configurations.py
  modified:
    - src/app/db/models/__init__.py
    - src/app/db/models/project.py
    - src/app/db/models/folder.py
    - src/app/db/models/test_case.py
    - src/app/api/deps.py
    - src/app/api/__init__.py

key-decisions:
  - "WebTest/WebTestRun/WebTestResult use explicit id/timestamp columns (not UUIDMixin/TimestampMixin) to match api_test.py pattern"
  - "Configuration uses integer autoincrement PK instead of UUID per BrowserStack API pattern"
  - "All routes use lazy service import pattern to avoid circular dependencies"
  - "Sub-function count maintained via parent function total_sub_functions counter on create/delete"

patterns-established:
  - "Integer PK model: Configuration demonstrates non-UUID primary key with TimestampMixin only"
  - "Nested sub-resource CRUD: web-functions/{id}/sub-functions pattern for hierarchical entities"
  - "Parent counter maintenance: service updates parent total_sub_functions on sub-function create/delete"

requirements-completed: [BE-ALIGN-01, BE-ALIGN-02, BE-ALIGN-03]

# Metrics
duration: 5min
completed: 2026-05-21
---

# Phase 16 Plan 01: Backend Models, Schemas, Repos, Services, Routes Summary

**6 SQLite-compatible SQLAlchemy models, 3 full CRUD stacks (schemas/repos/services/routes), 25 REST endpoints for web-functions, web-tests, and configurations**

## Performance

- **Duration:** 5 min
- **Started:** 2026-05-21T11:57:06Z
- **Completed:** 2026-05-21T12:03:04Z
- **Tasks:** 2
- **Files modified:** 21

## Accomplishments
- Created 6 new database models (WebFunction, WebSubFunction, WebTest, WebTestRun, WebTestResult, Configuration) with full bidirectional relationships to Project, Folder, and TestCase
- Built complete CRUD stack for 3 domain entities: schemas, repositories, services, and routes with 25 new endpoints
- All routes verified: 10 web-function routes, 9 web-test routes, 6 configuration routes, totaling 83 routes in the API router

## Task Commits

Each task was committed atomically:

1. **Task 1: Database models + project relationship updates + model registration** - `cc4d8a3` (feat)
2. **Task 2: Schemas + Repositories + Services + Routes + Registration** - `6e085ba` (feat)

## Files Created/Modified

- `src/app/db/models/web_function.py` - WebFunction + WebSubFunction models with project/folder relationships
- `src/app/db/models/web_test.py` - WebTest + WebTestRun + WebTestResult models
- `src/app/db/models/configuration.py` - Configuration model with integer PK
- `src/app/db/models/__init__.py` - Added model registrations in dependency order
- `src/app/db/models/project.py` - Added web_functions and web_tests relationships
- `src/app/db/models/folder.py` - Added web_functions and web_tests relationships
- `src/app/db/models/test_case.py` - Added web_tests relationship
- `src/app/db/schemas/web_function.py` - WebFunction and WebSubFunction CRUD schemas
- `src/app/db/schemas/web_test.py` - WebTest, WebTestRun, WebTestResult CRUD schemas
- `src/app/db/schemas/configuration.py` - Configuration CRUD schemas
- `src/app/db/repositories/web_function_repo.py` - WebFunction and WebSubFunction repositories
- `src/app/db/repositories/web_test_repo.py` - WebTest, WebTestRun, WebTestResult repositories
- `src/app/db/repositories/configuration_repo.py` - Configuration repository
- `src/app/db/services/web_function_service.py` - Web function/sub-function business logic with identifier generation
- `src/app/db/services/web_test_service.py` - Web test/run/result business logic
- `src/app/db/services/configuration_service.py` - Configuration business logic
- `src/app/api/v2/web_functions.py` - 10 web function/sub-function endpoints
- `src/app/api/v2/web_tests.py` - 9 web test/run/result endpoints
- `src/app/api/v2/configurations.py` - 6 configuration endpoints
- `src/app/api/deps.py` - Added WebFunctionServiceDep, WebTestServiceDep, ConfigurationServiceDep
- `src/app/api/__init__.py` - Registered web_functions, web_tests, configurations routers

## Decisions Made
- WebTest/WebTestRun/WebTestResult use explicit id/timestamp columns matching api_test.py pattern (not UUIDMixin/TimestampMixin mixins) for consistency with existing test domain models
- Configuration uses integer autoincrement PK following BrowserStack API pattern for OS/browser/device combos
- Sub-function routes nested under web-functions prefix (/projects/{id}/web-functions/{id}/sub-functions) for hierarchical resource organization
- Parent counter (total_sub_functions) maintained in service layer on sub-function create/delete operations

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 6 database models ready for table creation on startup
- 25 new REST endpoints available for frontend consumption in Plan 16-02
- SWR hooks and frontend pages can now be built against the web-functions, web-tests, and configurations endpoints

## Self-Check: PASSED

- All 15 created files verified present
- Both task commits verified in git log (cc4d8a3, 6e085ba)
- All models import successfully
- All 83 routes registered (10 web-function, 9 web-test, 6 configuration)
- No PostgreSQL dialect imports detected

---
*Phase: 16-backend-and-frontend-alignment*
*Completed: 2026-05-21*
