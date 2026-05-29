---
phase: quick
plan: 260529-shr
subsystem: testcase-agent
tags: [bug-fix, system-prompt, save-workflow]
dependency_graph:
  requires: [ensure_project, save_test_cases_batch]
  provides: [atomic-save-prompt, anti-lazy-merge-prompt]
  affects: [agent.py]
tech_stack:
  added: []
  patterns: [atomic-paired-tool-calls, read-parse-save-workflow]
key_files:
  created: []
  modified:
    - src/app/agents/testcase/agent.py
decisions:
  - "Atomic paired ensure_project + save_test_cases_batch calls enforced via SYSTEM_PROMPT instructions instead of code-level validation"
  - "read_file required for total project merge to prevent LLM shortcut of placeholder steps"
  - "Post-save self-verification checkpoint added for project count, case count, and step content quality"
metrics:
  duration: 3min
  completed: "2026-05-29"
  tasks: 1
  files: 1
---

# Quick Task 260529-shr: Fix Agent Empty Projects and Lazy Merge Summary

Atomic SYSTEM_PROMPT rewrite enforcing paired tool calls and banning placeholder step content in TestCase Agent auto-save workflow.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Fix Phase 5 prompt -- atomic save pairs and anti-lazy-merge | 7245035 | src/app/agents/testcase/agent.py |

## Changes Made

### Task 1: Fix Phase 5 prompt

**File:** `src/app/agents/testcase/agent.py`

**Bug 1 fix -- Atomic save pairs:**
- Replaced the loose 3-step save flow (`## 保存时机`) with a structured 3-step atomic workflow (`## 保存流程（强制原子操作）`)
- Each module now requires: `ensure_project` -> immediately `save_test_cases_batch` -> confirm success -> next module
- Added explicit "禁止行为" list: no batch ensure_project calls, no skipping save, no module skipping

**Bug 2 fix -- Anti-lazy-merge:**
- Step 2 (total project merge) now explicitly requires `read_file` to read each sub-module's `test_cases_{模块名}.md` file
- Steps must use real content from files, not generated summaries
- Explicit ban list of placeholder patterns: "参见子项目中的详细步骤", "详见子模块用例", "同子项目用例", and any "go look at another file" text

**Post-save self-verification:**
- Added `## 保存完成自检（强制）` section after `## 数据库保存格式`
- Three checks: project count verification, case count verification, step content spot-check
- Failed checks require re-execution of the merge step

## Verification

- Python AST parse: syntax OK
- Content assertions: all 4 fix elements present (atomic pair enforcement, read_file in total project, anti-placeholder text, self-check checkpoint)
- Runtime import check skipped due to pre-existing environment issue (PDFContextMiddleware constructor mismatch, unrelated to this change)

## Deviations from Plan

None -- plan executed exactly as written.

## Known Stubs

None.

## Self-Check: PASSED

- [x] src/app/agents/testcase/agent.py exists and modified
- [x] Commit 7245035 exists in git log
