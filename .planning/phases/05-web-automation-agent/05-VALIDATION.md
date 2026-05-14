---
phase: 05
slug: web-automation-agent
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-14
---

# Phase 05 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing) |
| **Config file** | pyproject.toml (defaults) |
| **Quick run command** | `python -m pytest tests/ -x -q` |
| **Full suite command** | `python -m pytest tests/ -v` |

## Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | Created In |
|--------|----------|-----------|-------------------|------------|
| WEB-01 | detect_test_mode returns correct mode for URL, repo path, ambiguous input | unit | `python -m pytest tests/test_web_tools.py::test_detect_test_mode -x` | Wave 2 (Plan 05-02) |
| WEB-02 | LocalShellBackend executes commands via CompositeBackend | integration | `python -m pytest tests/test_web_tools.py::test_shell_execute -x` | Wave 2 (Plan 05-02) |
| WEB-03/04/05 | Skills load and contain expected content sections | unit | `python -m pytest tests/test_web_skills.py::test_skill_load -x` | Wave 2 (Plan 05-02) |
| WEB-06/07 | 7 reference guides exist and are readable | unit | `python -m pytest tests/test_web_skills.py::test_reference_guides -x` | Wave 2 (Plan 05-02) |
| WEB-08 | ensure_output_dir creates correct directory structure | unit | `python -m pytest tests/test_web_tools.py::test_ensure_output_dir -x` | Wave 2 (Plan 05-02) |
| WEB-01 | Agent imports and creates successfully | smoke | `python -m pytest tests/test_web_agent.py::test_agent_import -x` | Wave 2 (Plan 05-02) |
| UI-14 | Pipeline stages display in ChatMessage | component | `npx tsc --noEmit` | Wave 3 (Plan 05-03) |

## Sampling Rate

- **Per task commit:** `python -m pytest tests/test_web_tools.py tests/test_web_skills.py -x -q`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before phase complete

## Wave 0 Gaps

Test files are created as part of Plan 05-02 (Wave 2), not in a separate Wave 0:
- [ ] `tests/test_web_tools.py` — covers WEB-01 (detect_test_mode), WEB-02 (shell execute), WEB-08 (ensure_output_dir), check_environment
- [ ] `tests/test_web_skills.py` — covers WEB-03/04/05/06/07 (Skill loading, reference guide readability)
- [ ] `tests/test_web_agent.py` — covers WEB-01 (agent import and creation)
