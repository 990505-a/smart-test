---
phase: 10-agent-database-integration
plan: 02
subsystem: frontend-chat
tags: [tool-result-cards, inline-cards, chat-ui, save-result-detection]
dependency_graph:
  requires: [10-01]
  provides: [ToolResultCard, parseSaveResults, stripSaveResultMarkers]
  affects: [ChatMessage]
tech-stack:
  added: [lucide-react (CheckCircle2, XCircle, ExternalLink)]
  patterns: [regex-based marker detection, useMemo content transformation]
key-files:
  created:
    - webui/src/app/components/ToolResultCard.tsx
  modified:
    - webui/src/app/components/ChatMessage.tsx
decisions:
  - Regex-based [SAVE_RESULT] marker detection in AI message content (per D-06)
  - Cards render inline between pipeline stage indicator and markdown content
  - Cards only appear after streaming completes (not during)
  - displayContent useMemo strips markers so raw text never renders
  - detectedStage moved after displayContent for correct dependency chain
metrics:
  duration: 3min
  completed: "2026-05-15"
  tasks: 2
  files: 2
  commits: 2
---

# Phase 10 Plan 02: Tool Result Card Components Summary

Inline card components for tool call results in chat messages, with regex-based detection of [SAVE_RESULT] markers and deep links to management pages.

## What Was Done

### Task 1: Created ToolResultCard component
- **File:** `webui/src/app/components/ToolResultCard.tsx`
- **Commit:** c1830c9
- Green success card with CheckCircle2 icon showing case count, identifiers, and deep link to `/cases?project={id}`
- Red error card with XCircle icon showing error message
- `parseSaveResults()` extracts structured data from `[SAVE_RESULT]...[/SAVE_RESULT]` blocks
- `stripSaveResultMarkers()` removes raw markers from display content

### Task 2: Integrated card detection into ChatMessage
- **File:** `webui/src/app/components/ChatMessage.tsx`
- **Commit:** aa08899
- Added `saveResults` useMemo to detect [SAVE_RESULT] blocks in AI messages
- Added `displayContent` useMemo to strip markers from rendered markdown
- Moved `detectedStage` after `displayContent` for correct dependency ordering
- ToolResultCard components render inline between pipeline stage indicator and markdown
- Cards only render when streaming is complete

## Deviations from Plan

None - plan executed exactly as written.

## Verification Results

- TypeScript compilation: passes (only pre-existing module resolution errors from worktree without node_modules)
- ToolResultCard exports: ToolResultCard, SaveResultData, parseSaveResults, stripSaveResultMarkers
- ChatMessage imports: ToolResultCard, parseSaveResults, stripSaveResultMarkers
- displayContent used in detectedStage, streaming paragraph, and ReactMarkdown rendering
- Cards rendered in non-streaming block with saveResults.length > 0 guard

## Key Decisions

1. **Hook ordering:** saveResults -> displayContent -> detectedStage ensures all dependencies resolve correctly in the component render cycle
2. **Streaming guard:** Cards only render when `!isStreaming` to avoid flickering during content delivery
3. **Dark mode support:** All card variants include dark: prefixed Tailwind classes

## Self-Check: PASSED

- FOUND: webui/src/app/components/ToolResultCard.tsx
- FOUND: webui/src/app/components/ChatMessage.tsx
- FOUND: .planning/phases/10-agent-database-integration/10-02-SUMMARY.md
- FOUND: commit c1830c9
- FOUND: commit aa08899
