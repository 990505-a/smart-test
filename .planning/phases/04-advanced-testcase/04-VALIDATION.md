---
phase: 4
slug: advanced-testcase
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-13
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | pyproject.toml [tool.pytest.ini_options] |
| **Quick run command** | `python -m pytest tests/ -x -q --tb=short` |
| **Full suite command** | `python -m pytest tests/ -v --tb=short` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -x -q --tb=short`
- **After every plan wave:** Run `python -m pytest tests/ -v --tb=short`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | MIDW-04 | unit | `python -m pytest tests/test_dynamic_model.py -v` | ❌ W0 | ⬜ pending |
| 04-01-02 | 01 | 1 | PARS-02, PARS-03 | unit | `python -m pytest tests/test_file_context.py -v` | ❌ W0 | ⬜ pending |
| 04-01-03 | 01 | 1 | PARS-06, UI-07 | integration | `python -m pytest tests/test_dynamic_model.py -v` | ❌ W0 | ⬜ pending |
| 04-02-01 | 02 | 1 | SKILL-04 | unit | `python -m pytest tests/test_skills.py -v` | ✅ exists | ⬜ pending |
| 04-02-02 | 02 | 1 | EXPT-03 | unit | `python -m pytest tests/test_multi_export.py -v` | ❌ W0 | ⬜ pending |
| 04-02-03 | 02 | 1 | UI-07 | unit | `npm test --prefix webui` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_dynamic_model.py` — stubs for MIDW-04, PARS-06
- [ ] `tests/test_file_context.py` — stubs for PARS-02, PARS-03
- [ ] `tests/test_multi_export.py` — stubs for EXPT-03

*Existing infrastructure (tests/test_skills.py) covers SKILL-04.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| UI Switch toggle in ConfigDialog | UI-07 | Requires browser rendering | Open ConfigDialog, toggle multimodal switch, verify state changes |
| GPT-4o image parsing end-to-end | PARS-02 | Requires real API call with image | Upload image in chat, verify agent response includes image description |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
