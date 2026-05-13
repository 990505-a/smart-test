---
phase: 04-advanced-testcase
plan: 01
subsystem: middleware/processors
tags: [dynamic-model, file-context, image-processor, excel-processor, gpt-4o]
dependency_graph:
  requires: [02-01-SUMMARY.md, 02-02-SUMMARY.md]
  provides: [DynamicModelSelection, FileContextMiddleware, ImageProcessor, ExcelProcessor]
  affects: [middleware/pdf_context.py, processors/, core/config.py]
tech_stack:
  added: [openai:gpt-4o, openpyxl]
  patterns: [lazy-init-model, multi-file-dispatch, backward-compat-alias]
key_files:
  created:
    - src/app/middleware/dynamic_model.py
    - src/app/processors/image.py
    - src/app/processors/excel.py
    - tests/test_dynamic_model.py
    - tests/test_file_context.py
  modified:
    - src/app/core/config.py
    - src/app/middleware/pdf_context.py
    - tests/conftest.py
    - tests/test_pdf_middleware.py
    - .env.example
decisions:
  - Lazy-init ImageProcessor model to avoid OpenAI API key error at construction time
  - FileContextMiddleware stores backward-compat alias PDFContextMiddleware for existing imports
  - Multi-file extraction scans both attachments and inline image_url content blocks
metrics:
  duration: 11min
  completed: "2026-05-13"
  tasks: 2
  files: 10
  tests_added: 14
  tests_total: 85
---

# Phase 4 Plan 1: Advanced TestCase Middleware Summary

DynamicModelSelection middleware with GPT-4o vision switching, unified FileContextMiddleware dispatching PDF/Image/Excel via MIME type, and lazy-init ImageProcessor to avoid API key errors at construction.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add GPT-4o config, DynamicModelSelection, ImageProcessor, ExcelProcessor, test fixtures | e7f68a4 | config.py, dynamic_model.py, image.py, excel.py, conftest.py, .env.example |
| 2 | Refactor PDFContextMiddleware to FileContextMiddleware with multi-file dispatch, unit tests | 690c3bd | pdf_context.py, image.py, test_dynamic_model.py, test_file_context.py, test_pdf_middleware.py |

## Key Decisions

1. **Lazy-init ImageProcessor model** - ImageProcessor defers `init_chat_model("openai:gpt-4o")` to first `extract_text()` call, avoiding `OpenAIError: Missing credentials` when constructing FileContextMiddleware without an API key in tests or at server startup. This allows the middleware chain to initialize cleanly even without OPENAI_API_KEY configured.

2. **Backward-compat alias** - `PDFContextMiddleware = FileContextMiddleware` at module level ensures existing imports (e.g., `agent.py` which imports `PDFContextMiddleware`) continue to work without modification. Will be cleaned up in Plan 03 when agent.py is updated.

3. **Dual-source file extraction** - `_extract_files_from_last_message` scans both `additional_kwargs.attachments` (file uploads) and `content` list blocks (inline `image_url`), ensuring coverage for both upload patterns.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] ImageProcessor eager init caused OpenAI API key error**
- **Found during:** Task 2 test run
- **Issue:** `ImageProcessor.__init__` called `init_chat_model("openai:gpt-4o")` immediately, which threw `OpenAIError: Missing credentials` when `api_key=""` and no `OPENAI_API_KEY` env var was set. This broke all middleware tests that create `FileContextMiddleware` without mocking `ImageProcessor`.
- **Fix:** Changed `ImageProcessor` to lazy-initialize the model on first use via `_get_model()` method, storing `api_key` and deferring `init_chat_model` until `extract_text()` is called.
- **Files modified:** `src/app/processors/image.py`
- **Commit:** 690c3bd

**2. [Rule 1 - Bug] Updated test_pdf_middleware.py attribute references**
- **Found during:** Task 2 refactoring
- **Issue:** Existing tests referenced `middleware._processor` and `middleware._session_pdf_hash` which no longer exist after renaming to FileContextMiddleware.
- **Fix:** Updated all references to `middleware._pdf_processor` and `middleware._session_file_hash`. Changed `test_non_pdf_attachment_ignored` to `test_image_attachment_processed` since images are now supported.
- **Files modified:** `tests/test_pdf_middleware.py`
- **Commit:** 690c3bd

## Test Results

- **Before:** 71 tests passing
- **After:** 85 tests passing (71 existing + 14 new)
- **New tests:**
  - `tests/test_dynamic_model.py`: 5 tests (no-image passthrough, image_url trigger, image attachment trigger, PDF no-trigger, image in non-last message)
  - `tests/test_file_context.py`: 9 tests (Excel markdown extraction, empty input, multi-sheet, PDF dispatch, image dispatch, Excel dispatch, multi-file concat, session isolation, MD5 dedup)

## Architecture Notes

The middleware onion order is now:
```
|-- SkillsMiddleware      -> append skills to system_message
|   |-- DynamicModelSelection -> detect image content, switch to GPT-4o
|   |   |-- FileContextMiddleware -> dispatch PDF/Image/Excel, inject into system_message
|   |   |-- LLM
```

FileContextMiddleware dispatches by MIME type:
- `application/pdf` -> PDFProcessor (PyMuPDF4LLM)
- `image/*` -> ImageProcessor (GPT-4o vision, lazy-init)
- `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` / `application/vnd.ms-excel` -> ExcelProcessor (openpyxl)

## Self-Check: PASSED

All 10 files verified present. Both commits (e7f68a4, 690c3bd) verified in git log.
