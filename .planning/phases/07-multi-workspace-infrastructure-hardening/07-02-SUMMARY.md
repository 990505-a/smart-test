---
phase: 07-multi-workspace-infrastructure-hardening
plan: 02
subsystem: frontend
tags: [frontend, workspace, select, space_id, useChat, config, navigation]

requires:
  - phase: 07-multi-workspace-infrastructure-hardening
    plan: 01
    provides: "get_space_id() backend helper, ResilientClient, workspace infrastructure"

provides:
  - "WorkspaceSelect component with dropdown for workspace selection"
  - "config.ts workspaceId field persisted to localStorage"
  - "useChat workspaceId parameter with space_id propagation in configurable"
  - "chat/page.tsx workspace state management with threadId clearing on switch"

affects: [07-multi-workspace-infrastructure-hardening]

tech-stack:
  added: []
  patterns: [workspace-state-persisted-to-localStorage, space_id-in-configurable, thread-clear-on-workspace-switch]

key-files:
  created:
    - webui/src/app/components/WorkspaceSelect.tsx
  modified:
    - webui/src/lib/config.ts
    - webui/src/app/types/types.ts
    - webui/src/app/hooks/useChat.ts
    - webui/src/app/chat/page.tsx

decisions:
  - "Static WORKSPACES list in types.ts — workspace management API deferred to future versions"
  - "WorkspaceSelect placed next to AgentTabs in header via Header children slot"
  - "Switching workspace clears threadId to prevent cross-workspace data leakage (per D-06)"

metrics:
  duration: "completed"
  tasks_completed: 2
  files_modified: 5
---

# Phase 07 Plan 02: Frontend Workspace UI Summary

Added frontend workspace selection UI with space_id propagation from frontend to backend via LangGraph configurable mechanism.

## What Was Done

### Task 1: WorkspaceSelect Component and Wiring

**WorkspaceSelect.tsx** — Dropdown component using shadcn/ui Select, displays workspace options from WORKSPACES constant, renders Building2 icon.

**config.ts** — Added `workspaceId?: string` to StandaloneConfig interface, persisted via existing getConfig/saveConfig localStorage mechanism.

**types.ts** — Added `WORKSPACES` constant with default workspace, and `WorkspaceId` type.

**useChat.ts** — Added `workspaceId` parameter (default "default"), passes `configurable: { space_id: workspaceId }` in every stream.submit call.

**chat/page.tsx** — Full workspace state management:
- `currentWorkspace` state initialized from config
- `handleWorkspaceChange` clears threadId and persists to localStorage
- `WorkspaceSelect` rendered in header next to AgentTabs
- `workspaceId` passed to ChatProvider

## Deviations from Plan

None — implemented exactly as specified in 07-02-PLAN.md.
