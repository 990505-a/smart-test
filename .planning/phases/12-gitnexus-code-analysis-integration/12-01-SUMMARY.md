---
phase: 12-gitnexus-code-analysis-integration
plan: 01
subsystem: frontend
tags: [frontend, iframe, code-analysis, gitnexus, navigation]

provides:
  - "/code-analysis page with iframe embedding of gitnexus-web frontend"
  - "Server probe with online/offline status indicator"
  - "ManagementLayout navigation item for code analysis"

affects: [12-gitnexus-code-analysis-integration]

tech-stack:
  added: []
  patterns: [iframe-embedding, server-health-probe, auto-reconnect]

key-files:
  created:
    - webui/src/app/code-analysis/page.tsx
  modified:
    - webui/src/app/components/ManagementLayout.tsx

decisions:
  - "iframe approach chosen for zero-coupling integration — gitnexus-web runs independently"
  - "Server probe via GET /api/repos with 3s timeout, polls every 15s"
  - "Offline state shows connection instructions with exact gitnexus serve command"

metrics:
  duration: "completed"
  tasks_completed: 1
  files_modified: 2
---

# Phase 12 Plan 01: GitNexus Frontend Embedding Summary

Embedded gitnexus-web frontend into the smart-test-platform via iframe at /code-analysis route.

## What Was Done

### Task 1: Code Analysis Page with iframe

**code-analysis/page.tsx** — Full page component with:
- Server health probe: `GET http://localhost:4747/api/repos` with 3s timeout, auto-polling every 15s
- Online/offline status indicator with colored badge (green/red/gray)
- Offline state: shows Server icon, connection instructions, and exact `gitnexus serve` command
- Refresh button (reloads iframe via key trick) and "open in new window" link
- iframe with clipboard permissions for seamless interaction

**ManagementLayout.tsx** — Added `Code2` icon and "代码分析" nav item pointing to /code-analysis

## Deviations from Plan

None — implemented exactly as specified.
