---
phase: 9
slug: platform-management-ui
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-14
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Next.js build (TypeScript compilation + route validation) |
| **Config file** | `webui/tsconfig.json` (existing) |
| **Quick run command** | `cd webui && npx next build 2>&1 \| tail -20` |
| **Full suite command** | `cd webui && npx next build` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd webui && npx next build 2>&1 | tail -20`
- **After every plan wave:** Run `cd webui && npx next build`
- **Before `/gsd:verify-work`:** Full build must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | Status |
|---------|------|------|-------------|-----------|-------------------|--------|
| 09-01-01 | 01 | 1 | PLAT-13 | build | `cd webui && npx next build 2>&1 \| tail -20` | pending |
| 09-01-02 | 01 | 1 | PLAT-13 | build | `cd webui && npx next build 2>&1 \| tail -20` | pending |
| 09-02-01 | 02 | 2 | PLAT-09 | build | `cd webui && npx next build 2>&1 \| tail -20` | pending |
| 09-02-02 | 02 | 2 | PLAT-09, PLAT-13 | build | `cd webui && npx next build 2>&1 \| tail -20` | pending |
| 09-03-01 | 03 | 2 | PLAT-10 | build | `cd webui && npx next build 2>&1 \| tail -20` | pending |
| 09-03-02 | 03 | 2 | PLAT-11 | build | `cd webui && npx next build 2>&1 \| tail -20` | pending |
| 09-04-01 | 04 | 3 | PLAT-12 | build | `cd webui && npx next build 2>&1 \| tail -20` | pending |
| 09-04-02 | 04 | 3 | PLAT-12 | build | `cd webui && npx next build 2>&1 \| tail -20` | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

No additional infrastructure needed. Next.js build validates TypeScript compilation, route structure, and component imports.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Visual layout of management pages matches design spec | PLAT-09 to PLAT-13 | CSS rendering differences between jsdom and browser | Open each page, verify layout matches CONTEXT.md D-03 |
| Drag-drop folder reordering UX feel | PLAT-10 | @dnd-kit drag animation not testable in jsdom | Manually drag folder items, verify reorder and visual feedback |
| BDD editor mode toggle UX | PLAT-11 | Rich text editing behavior in jsdom | Open case editor, toggle BDD mode, verify Given/When/Then format |
| Chart rendering in dashboard | PLAT-12 | recharts SVG rendering in jsdom | Open dashboard, verify BarChart/PieChart render with test data |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
