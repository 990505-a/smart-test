---
phase: 15-web-agent-playwright-mcp-upgrade
plan: 01
subsystem: web-agent
tags: [config, playwright, tool-registry, npm-workspace]
dependency_graph:
  requires: [config.py, workspace.py]
  provides: [WEB_AGENT_TOOLS, composite_backend, web_mcp_root_resolved]
  affects: [web-agent-tool-loading, web-agent-agent-creation]
tech_stack:
  added: ["@playwright/test ^1.58.2", "@types/node ^25.0.3"]
  patterns: ["JSON file storage for function data", "CompositeBackend with shell + file backends"]
key_files:
  created:
    - workspace/default/web/package.json
    - workspace/default/web/playwright.config.ts
    - src/app/agents/web/tools/__init__.py
    - src/app/agents/web/tools/function_tools.py
    - src/app/agents/web/tools/test_artifacts_tools.py
    - src/app/agents/web/tools/script_tools.py
    - src/app/agents/web/tools/execution_tools.py
  modified:
    - src/app/core/config.py
    - .gitignore
  deleted:
    - src/app/agents/web/tools.py
decisions:
  - "18 tools implemented (plan said 16 but listed 18); all listed tools created as specified"
  - "JSON file storage for function/sub-function data instead of DB models (Phase 16 adds DB models)"
  - "get_folder_structure and get_test_execution_status are placeholders returning empty/completed results"
metrics:
  duration: 7min
  tasks: 2
  files: 8
  completed: 2026-05-21
---

# Phase 15 Plan 01: Config and Tool Registry Summary

Config settings for Playwright MCP workspace and 18-tool registry replacing flat tools.py with 4-module package, using local JSON storage for Phase 15.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Config settings and Playwright MCP workspace setup | 6b63f3d | config.py, package.json, playwright.config.ts |
| 2 | Create tool registry package with 18 local tools | 20b14c0 | tools/__init__.py, function_tools.py, test_artifacts_tools.py, script_tools.py, execution_tools.py |

## What Was Built

### Task 1: Config and Workspace

- Added `web_mcp_root` setting to Settings class with empty default
- Added `web_mcp_root_resolved` property that computes `workspace/default/web` when empty
- Created `workspace/default/web/package.json` with @playwright/test ^1.58.2 and @types/node ^25.0.3
- Created `workspace/default/web/playwright.config.ts` with chromium project config
- Ran `npm install` -- 5 packages installed, 0 vulnerabilities
- Added `node_modules/` to .gitignore

### Task 2: Tool Registry Package (18 tools)

Replaced flat `tools.py` (3 tools: detect_test_mode, check_environment, ensure_output_dir) with `tools/` package containing 4 modules:

**function_tools.py (7 tools):**
- `list_web_functions` -- List functions from JSON file, filter by project/folder
- `get_function_details` -- Get function by UUID from JSON
- `list_web_sub_functions` -- List sub-functions, filter by project/function/folder
- `get_sub_function_details` -- Get sub-function by UUID
- `get_folder_structure` -- Placeholder returning empty (Phase 16 adds DB query)
- `create_web_function` -- Create function entry in functions.json with auto-UUID
- `create_web_sub_function` -- Create sub-function entry, update parent count

**test_artifacts_tools.py (6 tools):**
- `save_web_test_plan` -- Save test plan (file/dict/string) to artifacts dir
- `save_web_test_cases` -- Save test cases JSON to artifacts dir
- `save_web_test_script` -- Save .spec.ts script to artifacts dir
- `get_web_sub_function_artifacts` -- List files in artifacts dir categorized by type
- `save_web_test_report` -- Save HTML report to reports/{run_id}/
- `get_artifact_content` -- Read file content with workspace path safety check

**script_tools.py (3 tools):**
- `get_web_script_info` -- Get file metadata (size, timestamps)
- `download_web_script` -- Copy script from artifacts to tests/ dir with timestamped name
- `delete_web_script` -- Delete script from tests/ dir (with path safety)

**execution_tools.py (2 tools):**
- `execute_web_script` -- Run `npx playwright test` via asyncio subprocess with 300s timeout
- `get_test_execution_status` -- Placeholder returning "completed" (sync execution only)

## Decisions Made

1. **18 tools vs 16**: Plan header said 16 but body listed 18 tools (7+6+3+2). Implemented all 18 as specified in the detailed task descriptions. Documented as deviation.
2. **JSON file storage**: Functions and sub-functions stored in `functions.json` and `sub_functions.json` in workspace directory. Phase 16 adds WebFunction/WebSubFunction DB models.
3. **Phase 16 markers**: Each save tool includes a comment noting "Phase 16: add DB attachment record when WebFunction/WebSubFunction models exist".

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing] Tool count discrepancy (16 vs 18)**
- **Found during:** Task 2 verification
- **Issue:** Plan header says "16 local tools" and verification asserts `len == 16`, but task body lists 18 tools (7+6+3+2)
- **Fix:** Implemented all 18 tools as specified in the detailed task descriptions. The plan had a numerical inconsistency; the detailed specification (7+6+3+2) is authoritative.
- **Files affected:** tools/__init__.py
- **Commit:** 20b14c0

## Verification Results

```
config.py web_mcp_root_resolved -> D:\test_agent\smart-test-platform\workspace\default\web
@playwright/test installed -> PASS
All 4 tool modules import -> PASS
WEB_AGENT_TOOLS count -> 18 tools loaded
composite_backend, file_backend, shell_backend -> all exported
```

## Known Stubs

1. **get_folder_structure** in `function_tools.py` -- Returns empty folder tree. Phase 16 adds Folder model with WEB_TEST type query.
2. **get_test_execution_status** in `execution_tools.py` -- Always returns "completed" status. Future phases may add async execution with polling.

## File Summary

- **Created:** 7 files (package.json, playwright.config.ts, 5 Python modules)
- **Modified:** 2 files (config.py, .gitignore)
- **Deleted:** 1 file (tools.py)
- **Total:** 10 file operations

## Self-Check: PASSED

All 8 created/modified files exist on disk. Both commits (6b63f3d, 20b14c0) found in git log. Deleted tools.py confirmed removed.
