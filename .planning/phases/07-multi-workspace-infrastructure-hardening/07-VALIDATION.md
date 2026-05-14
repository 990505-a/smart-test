---
phase: 7
slug: multi-workspace-infrastructure-hardening
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-14
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | pyproject.toml |
| **Quick run command** | `.venv/Scripts/python -m pytest tests/test_workspace.py tests/test_resilient.py -x` |
| **Full suite command** | `.venv/Scripts/python -m pytest tests/ -x` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `.venv/Scripts/python -m pytest tests/test_workspace.py tests/test_resilient.py -x`
- **After every plan wave:** Run `.venv/Scripts/python -m pytest tests/ -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 1 | INFRA-07, RAGS-02 | unit | `pytest tests/test_workspace.py -x` | Wave 0 | pending |
| 07-01-02 | 01 | 1 | INFRA-08 | unit | `pytest tests/test_resilient.py -x` | Wave 0 | pending |
| 07-02-01 | 02 | 2 | INFRA-07 | unit | `pytest tests/test_workspace.py -x` | Wave 0 | pending |
| 07-02-02 | 02 | 2 | INFRA-07 | integration | `pytest tests/ -x` | existing | pending |

---

## Wave 0 Requirements

- [ ] `tests/test_workspace.py` — covers INFRA-07, RAGS-02 (workspace resolution, isolation)
- [ ] `tests/test_resilient.py` — covers INFRA-08 (ResilientClient, CircuitBreaker, retry)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Frontend workspace dropdown works | INFRA-07 | Requires running frontend + backend | Open UI, select different workspace, verify data isolation |
| Workspace data migration preserves existing data | INFRA-07 | Requires inspecting file system | Check workspace/default/ contains original testcase/web/api data |

---

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
