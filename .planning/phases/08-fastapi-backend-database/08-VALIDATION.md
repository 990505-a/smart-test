---
phase: 08
slug: fastapi-backend-database
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-14
---

# Phase 08 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (already in use) |
| **Config file** | None -- uses conftest.py and auto-discovery |
| **Quick run command** | `pytest tests/ -x -q` |
| **Full suite command** | `pytest tests/ -v` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x -q`
- **After every plan wave:** Run `pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 08-01-01 | 01 | 1 | PLAT-02 | unit | `pytest tests/test_db_models.py -x` | Wave 0 | pending |
| 08-01-02 | 01 | 1 | PLAT-07 | unit | `pytest tests/test_file_storage.py -x` | Wave 0 | pending |
| 08-02-01 | 02 | 1 | PLAT-01 | unit | `pytest tests/test_fastapi_app.py -x` | Wave 0 | pending |
| 08-02-02 | 02 | 1 | PLAT-03 | unit | `pytest tests/test_project_api.py -x` | Wave 0 | pending |
| 08-02-03 | 02 | 1 | PLAT-04 | unit | `pytest tests/test_folder_api.py -x` | Wave 0 | pending |
| 08-02-04 | 02 | 1 | PLAT-05 | unit | `pytest tests/test_testcase_api.py -x` | Wave 0 | pending |
| 08-02-05 | 02 | 1 | PLAT-06 | unit | `pytest tests/test_testrun_api.py -x` | Wave 0 | pending |
| 08-03-01 | 03 | 1 | PLAT-08 | unit | `pytest tests/test_db_tools.py -x` | Wave 0 | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_fastapi_app.py` -- covers PLAT-01 (app creation, CORS, health check)
- [ ] `tests/test_db_models.py` -- covers PLAT-02 (model table creation)
- [ ] `tests/test_project_api.py` -- covers PLAT-03 (project CRUD)
- [ ] `tests/test_folder_api.py` -- covers PLAT-04 (folder tree management)
- [ ] `tests/test_testcase_api.py` -- covers PLAT-05 (test case CRUD)
- [ ] `tests/test_testrun_api.py` -- covers PLAT-06 (test run management)
- [ ] `tests/test_file_storage.py` -- covers PLAT-07 (file storage)
- [ ] `tests/test_db_tools.py` -- covers PLAT-08 (agent DB tools)
- [ ] `tests/conftest.py` -- add async DB fixtures (async engine, test session, test client)

*If none: "Existing infrastructure covers all phase requirements."*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| PostgreSQL server is running and accessible | PLAT-01 through PLAT-08 | External service dependency; cannot be verified without running PostgreSQL instance | Start PostgreSQL, run `psql -U postgres -c "SELECT 1"`, verify `smart_test_platform` database exists |
| FastAPI serves on port 8000 alongside LangGraph on port 2026 | PLAT-01 | Requires two live processes; integration-level check | Start both servers, curl `http://localhost:8000/health` and `http://localhost:2026/ok` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
