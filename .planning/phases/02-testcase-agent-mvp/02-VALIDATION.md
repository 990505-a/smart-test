---
phase: 02
slug: testcase-agent-mvp
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-11
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | none — Wave 0 installs |
| **Quick run command** | `pytest tests/ -x -q` |
| **Full suite command** | `pytest tests/ -v --tb=short` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x -q`
- **After every plan wave:** Run `pytest tests/ -v --tb=short`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 0 | PARS-01 | unit | `pytest tests/test_pdf_processor.py -x` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 0 | PARS-05 | unit | `pytest tests/test_pdf_processor.py::test_md5_cache -x` | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 | 1 | MIDW-01 | unit | `pytest tests/test_pdf_middleware.py -x` | ❌ W0 | ⬜ pending |
| 02-02-02 | 02 | 1 | MIDW-02 | unit | `pytest tests/test_pdf_middleware.py::test_session_isolation -x` | ❌ W0 | ⬜ pending |
| 02-02-03 | 02 | 1 | MIDW-03 | unit | `pytest tests/test_pdf_middleware.py::test_immutable_prompt -x` | ❌ W0 | ⬜ pending |
| 02-03-01 | 03 | 1 | MIDW-06 | unit | `pytest tests/test_skills_middleware.py -x` | ❌ W0 | ⬜ pending |
| 02-04-01 | 04 | 2 | SKILL-01~06 | smoke | `pytest tests/test_skills.py -x` | ❌ W0 | ⬜ pending |
| 02-05-01 | 05 | 2 | EXPT-01 | unit | `pytest tests/test_excel_export.py -x` | ❌ W0 | ⬜ pending |
| 02-05-02 | 05 | 2 | EXPT-02 | unit | `pytest tests/test_excel_export.py::test_tc_numbering -x` | ❌ W0 | ⬜ pending |
| 02-05-03 | 05 | 2 | EXPT-04 | unit | `pytest tests/test_excel_export.py::test_field_extraction -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_pdf_processor.py` — stubs for PARS-01, PARS-05
- [ ] `tests/test_pdf_middleware.py` — stubs for MIDW-01, MIDW-02, MIDW-03
- [ ] `tests/test_skills_middleware.py` — stubs for MIDW-06
- [ ] `tests/test_skills.py` — stubs for SKILL-01, SKILL-02, SKILL-03, SKILL-06
- [ ] `tests/test_excel_export.py` — stubs for EXPT-01, EXPT-02, EXPT-04
- [ ] `tests/conftest.py` — shared fixtures
- [ ] Framework install: `uv pip install pytest`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SKILL-07: System prompt enforces 5-stage workflow order | SKILL-07 | Requires live LLM interaction to verify agent follows sequential stages | Start server, upload PDF, verify agent produces output in 5 stages |
| PDF injection preserves Skills content | MIDW-03 | Integration test across middleware chain | Upload PDF, verify agent response follows Skill workflow patterns |
| Excel download in chat interface | EXPT-01 | Requires full stack (frontend + backend) | Generate test cases, click download, verify Excel opens correctly |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
