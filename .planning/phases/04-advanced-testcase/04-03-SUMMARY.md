---
phase: 04-advanced-testcase
plan: 03
subsystem: testcase-agent
tags: [middleware, integration, frontend, multimodal, gpt-4o, export, config]
dependency_graph:
  requires: [04-01, 04-02]
  provides: [3-layer-onion-middleware, unified-export-in-agent, multimodal-toggle-frontend]
  affects: [src/app/agents/testcase/agent.py, webui/src/lib/config.ts, webui/src/app/components/ConfigDialog.tsx, webui/src/app/hooks/useChat.ts]
tech_stack:
  added: []
  patterns: [3-layer-onion-middleware, config-toggle-frontend]
key_files:
  created: []
  modified:
    - src/app/agents/testcase/agent.py
    - webui/src/lib/config.ts
    - webui/src/app/components/ConfigDialog.tsx
    - webui/src/app/hooks/useChat.ts
decisions:
  - Agent middleware chain: Skills(outer) -> DynamicModel(middle) -> FileContext(inner)
  - Unified export_test_cases replaces export_test_cases_to_excel in agent tools
  - Frontend multimodal toggle persists in localStorage via StandaloneConfig
  - enable_multimodal passed to backend via additional_kwargs
metrics:
  duration: 5min
  tasks_completed: 2
  files_created: 0
  files_modified: 4
  tests_added: 0
  tests_passing: 101
completed: "2026-05-13T08:15:00Z"
---

# Plan 04-03 Summary: Integration Wiring + Frontend Multimodal Toggle

## What was done

1. **Agent 3-layer middleware chain** (Task 1): Updated `agent.py` to wire Skills -> DynamicModel -> FileContext onion. Replaced `PDFContextMiddleware` import with `FileContextMiddleware`, added `DynamicModelSelection` middleware, replaced `export_test_cases_to_excel` with unified `export_test_cases`. Updated SYSTEM_PROMPT for test-data-generator skill and multi-format export instructions.

2. **Frontend multimodal toggle** (Task 2): Added `enablePdfMultimodal` to `StandaloneConfig` interface, added Switch toggle to `ConfigDialog.tsx` with Chinese label "多模态模式", wired `enable_multimodal` passthrough in `useChat.ts` via `additional_kwargs`.

## Verification

- 101 tests pass (0 failures)
- TypeScript compiles without errors
- AST parse confirms all imports are valid
- 7 SKILL.md files present
- Agent loads correctly (fails only on missing DEEPSEEK_API_KEY at module level, expected)
