---
phase: 01-core-infrastructure-frontend-shell
plan: 02
subsystem: ui
tags: [nextjs, react, tailwindcss4, shadcn-ui, nuqs, next-themes, langgraph-sdk, react-resizable-panels]

# Dependency graph
requires: []
provides:
  - Next.js 15.4.4 frontend shell with App Router
  - Root layout with NuqsAdapter + ThemeProvider + Toaster
  - Main page with agent tab bar and resizable panel layout
  - ClientProvider for LangGraph SDK context
  - StandaloneConfig with localStorage persistence
  - TypeScript interfaces for agents and content blocks
affects: [01-03-PLAN, 01-04-PLAN]

# Tech tracking
tech-stack:
  added: [next@15.4.4, react@19.1.0, tailwindcss@4, shadcn-ui, nuqs, next-themes, react-resizable-panels@4, @langchain/langgraph-sdk, swr, sonner, lucide-react, use-stick-to-bottom, date-fns, react-markdown, remark-gfm, uuid, clsx, tailwind-merge]
  patterns: [client-component-suspense-pattern, url-state-via-nuqs, resizable-panel-layout, agent-tab-routing]

key-files:
  created:
    - webui/src/app/layout.tsx
    - webui/src/app/page.tsx
    - webui/src/providers/ClientProvider.tsx
    - webui/src/providers/ThemeProvider.tsx
    - webui/src/lib/config.ts
    - webui/src/app/types/types.ts
    - webui/src/lib/utils.ts
    - webui/components.json
    - webui/src/components/ui/*.tsx
  modified:
    - webui/src/app/globals.css

key-decisions:
  - "Used react-resizable-panels v4 API (orientation instead of direction, no autoSaveId/order props)"
  - "Tailwind CSS 4 with @theme inline directive and @custom-variant dark for Shadcn/ui"
  - "Agent tab switching clears threadId to prevent state leakage across agents"

patterns-established:
  - "Suspense wrapper required by nuqs around page content"
  - "ClientProvider wraps app at config-loaded level, not layout level"
  - "Agent routing via useQueryState('agent') with AGENT_CONFIG lookup"
  - "ConfigDialog pattern for deployment URL and assistant ID setup"

requirements-completed: [UI-01, UI-09, UI-11, UI-12]

# Metrics
duration: 13min
completed: 2026-05-11
---

# Phase 01 Plan 02: Frontend Shell Setup Summary

**Next.js 15.4.4 frontend shell with Shadcn/ui, Tailwind CSS 4, agent tab bar, resizable panels, theme toggle, URL state via nuqs, and LangGraph SDK client provider**

## Performance

- **Duration:** 13 min
- **Started:** 2026-05-11T07:33:44Z
- **Completed:** 2026-05-11T07:46:20Z
- **Tasks:** 2
- **Files modified:** 39

## Accomplishments
- Scaffolded Next.js 15.4.4 project with TypeScript, Tailwind CSS 4, and App Router
- Created root layout with NuqsAdapter, ThemeProvider (next-themes), and Toaster (sonner)
- Built main page with three-domain agent tabs, resizable left-right panel layout, and theme toggle
- Implemented URL state management for threadId, sidebar, and agent params via nuqs
- Created ClientProvider for LangGraph SDK Client context and StandaloneConfig for localStorage persistence

## Task Commits

Each task was committed atomically:

1. **Task 1: Scaffold Next.js project and install all frontend dependencies** - `54eab2d` (feat)
2. **Task 2: Create core layout, providers, config, types, and main page** - `53a3fcc` (feat)

## Files Created/Modified
- `webui/package.json` - Project dependencies with Next.js 15.4.4 and all frontend libraries
- `webui/src/app/globals.css` - Tailwind CSS 4 theme with Shadcn/ui CSS variables (light/dark)
- `webui/src/app/layout.tsx` - Root layout with Inter font, ThemeProvider, NuqsAdapter, Toaster
- `webui/src/app/page.tsx` - Main page with agent tabs, resizable panels, ConfigDialog, ThemeToggle
- `webui/src/providers/ThemeProvider.tsx` - next-themes wrapper component
- `webui/src/providers/ClientProvider.tsx` - LangGraph SDK Client context provider with useClient hook
- `webui/src/lib/config.ts` - StandaloneConfig interface with localStorage persistence
- `webui/src/lib/utils.ts` - cn() utility from Shadcn/ui (clsx + tailwind-merge)
- `webui/src/app/types/types.ts` - TypeScript interfaces: AgentKey, AgentConfig, AGENT_CONFIG, ContentBlock, StateType
- `webui/components.json` - Shadcn/ui configuration (base-nova style, Tailwind v4)
- `webui/postcss.config.mjs` - PostCSS config with @tailwindcss/postcss plugin
- `webui/tsconfig.json` - TypeScript config with path alias @/*
- `webui/src/components/ui/*.tsx` - 15 Shadcn/ui components (button, tabs, dialog, resizable, etc.)

## Decisions Made
- Used `orientation` prop instead of `direction` for ResizablePanelGroup (react-resizable-panels v4 API change)
- Removed `autoSaveId` and `order` props from resizable panels (not available in v4, layout persistence uses different API)
- Used `@custom-variant dark (&:is(.dark *))` in globals.css for dark mode (Shadcn/ui + Tailwind CSS 4 pattern)
- Agent tab switching clears threadId to prevent thread state leakage between agents (per research Pitfall 4)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed react-resizable-panels v4 API incompatibility**
- **Found during:** Task 2 (Main page implementation)
- **Issue:** Plan used v3 API props (`direction`, `autoSaveId`, `order`) which don't exist in v4 (installed as 4.11.0)
- **Fix:** Changed `direction` to `orientation`, removed `autoSaveId` (used `id`), removed `order` props from ResizablePanel
- **Files modified:** webui/src/app/page.tsx
- **Verification:** npm run build succeeds
- **Committed in:** 53a3fcc (Task 2 commit)

**2. [Rule 3 - Blocking] Added missing input Shadcn/ui component**
- **Found during:** Task 2 (ConfigDialog implementation)
- **Issue:** ConfigDialog uses Input component which was not in the plan's component install list
- **Fix:** Ran `npx shadcn@latest add input -y`
- **Files modified:** webui/src/components/ui/input.tsx
- **Verification:** npm run build succeeds
- **Committed in:** 53a3fcc (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 blocking issues)
**Impact on plan:** Both auto-fixes were API compatibility adjustments. No scope creep.

## Issues Encountered
- create-next-app prompted for Turbopack preference (interactive) - resolved by piping input

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Frontend shell complete and builds successfully
- Ready for Plan 03 (chat interface and thread list implementation)
- Ready for Plan 04 (streaming chat with LangGraph SDK)
- Thread list and chat interface are placeholder divs awaiting implementation

## Self-Check: PASSED

All 9 key files verified present. Both task commits (54eab2d, 53a3fcc) found in git log.

---
*Phase: 01-core-infrastructure-frontend-shell*
*Completed: 2026-05-11*
