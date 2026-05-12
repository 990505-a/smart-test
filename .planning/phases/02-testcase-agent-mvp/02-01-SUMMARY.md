---
phase: 02-testcase-agent-mvp
plan: 01
subsystem: document-processing
tags: [pdf, pymupdf4llm, middleware, caching, md5, session-isolation, deepagents]

# Dependency graph
requires:
  - phase: 01-core-infrastructure-frontend-shell
    provides: "Agent stubs, config.py Settings, llms.py, graph.json"
provides:
  - "PDFProcessor class with MD5 hash caching for PDF text extraction"
  - "extract_pdf_text function using PyMuPDF4LLMLoader (mode=page)"
  - "PDFContextMiddleware with session isolation and immutable system prompt"
  - "Test suite: 19 unit tests (10 processor + 9 middleware)"
affects: [02-02, 02-03, 04-advanced-testcase]

# Tech tracking
tech-stack:
  added: [langchain-pymupdf4llm, reportlab, pytest, pytest-asyncio, openpyxl]
  patterns: [md5-cache-dedup, onion-middleware, immutable-system-prompt, session-isolation-dict]

key-files:
  created:
    - "src/app/processors/pdf.py"
    - "src/app/middleware/pdf_context.py"
    - "tests/conftest.py"
    - "tests/test_pdf_processor.py"
    - "tests/test_pdf_middleware.py"
  modified: []

key-decisions:
  - "extract_images=False for basic PDF processor; multimodal image extraction deferred to Phase 4 with images_parser"
  - "PDFContextMiddleware uses current request.system_message as base (v4 immutable pattern) to preserve SkillsMiddleware content"
  - "Session isolation via thread_id-keyed dicts (_session_docs, _session_pdf_hash) with __default__ fallback"

patterns-established:
  - "MD5 hash cache pattern: filename_md5hex key, module-level dict, enable_cache flag"
  - "Immutable system prompt pattern: constructor injects original, runtime uses request.override()"
  - "Windows temp file handling: os.fsync + _safe_delete_temp_file with retry logic"
  - "Middleware test pattern: MockModelRequest + AsyncMock handler + patch _get_thread_id"

requirements-completed: [PARS-01, PARS-05, MIDW-01, MIDW-02, MIDW-03]

# Metrics
duration: 14min
completed: 2026-05-12
---

# Phase 2 Plan 01: PDF Processing Pipeline Summary

**PDFProcessor with MD5 caching and PDFContextMiddleware with session-isolated document injection via immutable system prompt pattern**

## Performance

- **Duration:** 14 min
- **Started:** 2026-05-12T01:40:54Z
- **Completed:** 2026-05-12T01:54:56Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- PDF processing pipeline converts PDF bytes to Markdown via PyMuPDF4LLMLoader with MD5 hash caching
- PDFContextMiddleware extracts base64 PDF from last HumanMessage, parses content, injects into system prompt
- Session isolation via thread_id-keyed dictionaries, independent document state per conversation
- Immutable system prompt pattern preserves SkillsMiddleware content when injecting PDF blocks
- 19 comprehensive unit tests covering all requirements (PARS-01, PARS-05, MIDW-01, MIDW-02, MIDW-03)

## Task Commits

Each task was committed atomically:

1. **Task 1: PDF Processor with MD5 caching** - `0064346` (feat)
2. **Task 2: PDFContextMiddleware with session isolation** - `e7bcec5` (feat)

## Files Created/Modified
- `src/app/processors/__init__.py` - Empty package init
- `src/app/processors/pdf.py` - PDFProcessor class, extract_pdf_text function, MD5 caching, safe temp file deletion
- `src/app/middleware/__init__.py` - Empty package init
- `src/app/middleware/pdf_context.py` - PDFContextMiddleware with session isolation, immutable system prompt
- `tests/__init__.py` - Empty test package init
- `tests/conftest.py` - Shared fixtures (sample_pdf_bytes, MockModelRequest, create_pdf_attachment)
- `tests/test_pdf_processor.py` - 10 unit tests for PDF processing and caching
- `tests/test_pdf_middleware.py` - 9 unit tests for middleware session isolation and immutability

## Decisions Made
- Used `extract_images=False` for basic PDF processor since PyMuPDF4LLMLoader requires an `images_parser` parameter when `extract_images=True`. Multimodal image extraction deferred to Phase 4 when DynamicModelSelection and LLMImageBlobParser are implemented.
- Used `file_path` positional argument for PyMuPDF4LLMLoader (not `path` keyword) matching the installed version's API signature.
- PDFContextMiddleware v4 immutable pattern: `_build_system_message()` uses `current_system_message.content` as base instead of `_original_system_content`, ensuring SkillsMiddleware-appended content is preserved during PDF injection.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed extract_images parameter causing extraction failure**
- **Found during:** Task 1 (PDF Processor)
- **Issue:** Plan specified `extract_images=True` but PyMuPDF4LLMLoader requires an `images_parser` when images are enabled, causing "images_parser must be provided" error
- **Fix:** Added `extract_images` and `images_parser` parameters to `extract_pdf_text()`. Default is `extract_images=False`; multimodal mode will be enabled in Phase 4 with proper image parser
- **Files modified:** src/app/processors/pdf.py
- **Verification:** All 10 processor tests pass
- **Committed in:** 0064346 (Task 1 commit)

**2. [Rule 1 - Bug] Fixed PyMuPDF4LLMLoader constructor argument name**
- **Found during:** Task 1 (PDF Processor)
- **Issue:** Used `path` keyword but the installed version requires `file_path` as positional argument
- **Fix:** Changed `PyMuPDF4LLMLoader(**loader_kwargs)` to `PyMuPDF4LLMLoader(file_path=temp_path, **loader_kwargs)`
- **Files modified:** src/app/processors/pdf.py
- **Verification:** All 10 processor tests pass
- **Committed in:** 0064346 (Task 1 commit)

**3. [Rule 3 - Blocking] Installed pytest-asyncio for async middleware tests**
- **Found during:** Task 2 (PDFContextMiddleware)
- **Issue:** pytest-asyncio was not installed, async test functions could not run
- **Fix:** `uv pip install pytest-asyncio`
- **Files modified:** None (dependency only)
- **Verification:** All 9 middleware tests pass with async support

---

**Total deviations:** 3 auto-fixed (2 bugs, 1 blocking dependency)
**Impact on plan:** All auto-fixes necessary for correctness. No scope creep. The extract_images parameter addition is forward-compatible with Phase 4 multimodal support.

## Issues Encountered
- Module-level `_pdf_cache` shared across tests caused test assertion failure (expected 1 cached file, got 2). Fixed by adjusting test to use `enable_cache=False` for stats test and clearing cache before assertion in clear_cache test.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- PDF processing pipeline ready for integration with SkillsMiddleware (Plan 02-02)
- PDFContextMiddleware ready for onion middleware chain wiring (Plan 02-03)
- The extract_images parameter is forward-compatible with Phase 4 multimodal image extraction

## Self-Check: PASSED

All 8 files verified FOUND. Both task commits (0064346, e7bcec5) verified in git log. All 19 tests passing.

---
*Phase: 02-testcase-agent-mvp*
*Completed: 2026-05-12*
