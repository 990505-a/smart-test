---
phase: 6
slug: api-automation-agent
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-14
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 |
| **Config file** | pyproject.toml (no pytest.ini) |
| **Quick run command** | `.venv/Scripts/python -m pytest tests/test_api_agent.py -x` |
| **Full suite command** | `.venv/Scripts/python -m pytest tests/ -x` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `.venv/Scripts/python -m pytest tests/test_api_agent.py tests/test_api_tools.py tests/test_api_skills.py -x`
- **After every plan wave:** Run `.venv/Scripts/python -m pytest tests/ -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | API-01, API-05, API-06 | unit | `pytest tests/test_api_tools.py -x` | Wave 0 | pending |
| 06-01-02 | 01 | 1 | API-03, API-04, API-09 | unit | `pytest tests/test_api_skills.py -x` | Wave 0 | pending |
| 06-02-01 | 02 | 1 | API-02, API-07 | unit | `pytest tests/test_api_agent.py -x` | Wave 0 | pending |
| 06-02-02 | 02 | 1 | API-01..API-09 | integration | `pytest tests/ -x` | Wave 0 | pending |
| 06-03-01 | 03 | 2 | API-01..API-09 | integration | `pytest tests/ -x` | existing | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_api_agent.py` — stubs for API-02, API-07 (agent import, system prompt, MCP config)
- [ ] `tests/test_api_tools.py` — stubs for API-01, API-05, API-06 (api_parser, check_syntax, compute_coverage)
- [ ] `tests/test_api_skills.py` — stubs for API-03, API-04, API-09 (3 Skill file existence and content)
- [ ] `Levenshtein` package install — required before compute_coverage tests pass

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Agent generates test scripts from OpenAPI spec | API-01, API-02 | Requires running LLM + DeepAgents server | Upload OpenAPI JSON, verify generated .spec.ts files |
| GitNexus MCP connects and returns code graph data | API-07 | Requires GitNexus server running locally | Start GitNexus, send query, verify tool_map/api_impact responses |

---

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
