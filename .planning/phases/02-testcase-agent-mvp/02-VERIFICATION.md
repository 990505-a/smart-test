---
phase: 02-testcase-agent-mvp
verified: 2026-05-12T10:30:00Z
status: passed
score: 5/5 must-haves verified
---

# Phase 2: TestCase Agent MVP Verification Report

**Phase Goal:** Users can upload a document and receive structured, numbered test cases exported as a professionally formatted Excel file
**Verified:** 2026-05-12T10:30:00Z
**Status:** PASSED
**Re-verification:** No -- initial verification

## Goal Achievement

The phase goal breaks down into 5 observable truths from ROADMAP.md Success Criteria:

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User can upload a PDF document and receive parsed content via PDFContextMiddleware injected into the agent's system prompt, with session isolation per thread | VERIFIED | `src/app/middleware/pdf_context.py` (270 lines): `_extract_pdf_from_last_message()` extracts base64 PDF from HumanMessage attachments, `_session_docs` keyed by thread_id, `_session_pdf_hash` for MD5 dedup. `awrap_model_call()` injects into system_message via `request.override()`. 9 middleware tests pass. |
| 2 | User receives test cases generated through a mandatory 5-stage workflow powered by 3 core skills (requirement-analysis, test-strategy, test-case-design) | VERIFIED | `src/app/agents/testcase/agent.py`: SYSTEM_PROMPT contains 5-stage workflow table (Phase 1-5) with Skills requirement-analysis, test-strategy, test-case-design, quality-review, output-formatter. Red line enforced: "未完成 Phase 1 和 Phase 2 前，禁止生成具体测试用例". |
| 3 | User can download an Excel file with professional formatting (headers, borders, alignment, auto-wrap) and standardized case numbering (TC-[PROJECT]-[MODULE]-[NNN]) | VERIFIED | `src/app/agents/testcase/tools.py`: `export_test_cases_to_excel()` uses openpyxl Workbook with `_HEADER_FILL` (#366092), `_HEADER_FONT` (white bold), `_BORDER` (thin all sides), `_ALIGNMENT_WRAP` (vertical top, wrap text), `_ALIGNMENT_CENTER`. 10 HEADERS columns. Column widths configured. Row heights 24/60. 15 Excel export tests pass. |
| 4 | Previously parsed documents are cached via MD5 hash and not re-processed on repeated uploads | VERIFIED | `src/app/processors/pdf.py`: `_get_cache_key()` generates `filename_md5hex` key. `extract_pdf_text()` checks cache before parsing. `PDFProcessor` class wraps with enable_cache flag. Module-level `_pdf_cache` dict. Tests `test_md5_cache_returns_cached_result` and `test_md5_cache_different_files` pass. |
| 5 | Skills are loaded from SKILL.md files on the filesystem and injected into the agent via the SkillsMiddleware onion layer | VERIFIED | 5 SKILL.md files exist at `src/app/skills/{name}/SKILL.md` with valid YAML frontmatter where `name` matches directory. `agent.py` configures `SkillsMiddleware(backend=skills_backend, sources=["/skills/"])` with separate FilesystemBackend rooted at `src/app/`. 25 skill tests pass including frontmatter validation. |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/app/processors/pdf.py` | PDFProcessor class with MD5 caching | VERIFIED | 138 lines. Exports `PDFProcessor`, `extract_pdf_text`. PyMuPDF4LLMLoader with mode="page". MD5 cache via `_get_cache_key()`. Safe temp file deletion with retry. |
| `src/app/middleware/pdf_context.py` | PDFContextMiddleware with session isolation | VERIFIED | 270 lines. Exports `PDFContextMiddleware`. Session isolation via `_session_docs[thread_id]`. Immutable pattern via `_original_system_content`. v4 fix: uses `request.system_message` as base. |
| `src/app/skills/requirement-analysis/SKILL.md` | Skill with PPDCS analysis | VERIFIED | 17419 bytes. YAML frontmatter: `name: requirement-analysis`. Contains PPDCS 5-dimension sections. |
| `src/app/skills/test-strategy/SKILL.md` | Skill with KUFI classification | VERIFIED | 13398 bytes. YAML frontmatter: `name: test-strategy`. Contains KUFI 4-quadrant classification. |
| `src/app/skills/test-case-design/SKILL.md` | Skill with 6 design techniques | VERIFIED | 13894 bytes. YAML frontmatter: `name: test-case-design`. Contains equivalence class, boundary value, decision table, state transition, scenario, error guessing. |
| `src/app/skills/quality-review/SKILL.md` | Skill with coverage evaluation | VERIFIED | 12909 bytes. YAML frontmatter: `name: quality-review`. Contains coverage evaluation (16 matches). |
| `src/app/skills/output-formatter/SKILL.md` | Skill with TC numbering | VERIFIED | 8059 bytes. YAML frontmatter: `name: output-formatter`. Contains TC-[PROJECT]-[MODULE]-[NNN] convention. |
| `src/app/agents/testcase/tools.py` | Excel export tool with field extraction | VERIFIED | 187 lines. Exports `export_test_cases_to_excel` as `@tool`. 5 field extraction helpers. Professional styles. EN/CN key mapping. |
| `src/app/agents/testcase/agent.py` | Fully wired agent | VERIFIED | 169 lines. Imports PDFContextMiddleware, SkillsMiddleware, export_test_cases_to_excel. Onion middleware: [skills_middleware, pdf_middleware]. System prompt with 5-stage workflow. |
| `tests/test_pdf_processor.py` | Processor unit tests | VERIFIED | 10 tests pass. Covers extraction, caching, empty input, class interface. |
| `tests/test_pdf_middleware.py` | Middleware unit tests | VERIFIED | 9 tests pass. Covers extraction, session isolation, immutable prompt, MD5 dedup, non-PDF, last message, fallback thread, clear/stats. |
| `tests/test_skills.py` | Skill smoke tests | VERIFIED | 25 tests pass. Covers directory existence, SKILL.md existence, frontmatter validation, content sections, PPDCS/KUFI/coverage/TC convention. |
| `tests/test_excel_export.py` | Excel export tests | VERIFIED | 15 tests pass. Covers field extraction (EN/CN keys), file creation, header styles, empty case error, TC numbering, nested formats. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `agent.py` | `pdf_context.py` | `from app.middleware.pdf_context import PDFContextMiddleware` | WIRED | Line 29: import. Line 151: instantiation with SYSTEM_PROMPT. Line 164: middleware=[..., pdf_middleware]. |
| `agent.py` | `skills/` | `SkillsMiddleware(backend=skills_backend, sources=["/skills/"])` | WIRED | Line 25: import SkillsMiddleware. Line 51-54: backend rooted at src/app/, sources=["/skills/"]. Line 163: middleware=[skills_middleware, ...]. |
| `agent.py` | `tools.py` | `from app.agents.testcase.tools import export_test_cases_to_excel` | WIRED | Line 30: import. Line 161: tools=[export_test_cases_to_excel]. System prompt references it at line 138. |
| `tools.py` | `openpyxl` | `from openpyxl import Workbook` | WIRED | Line 11: import. Line 138: Workbook(). Full styling applied lines 148-183. |
| `pdf_context.py` | `pdf.py` | `from src.app.processors.pdf import PDFProcessor` | WIRED | Line 39: import. Line 84: PDFProcessor(enable_cache=enable_cache). Line 133: extract_text() called. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `pdf_context.py` | `current_doc` (injected into system_message) | `PDFProcessor.extract_text()` -> `_session_docs[thread_id]` | Yes: PyMuPDF4LLMLoader.load() reads PDF bytes via temp file, returns documents with page_content | FLOWING |
| `tools.py` | `test_cases` parameter (dict list -> Excel rows) | Caller provides test case dicts | Yes: `_extract_field()` extracts from EN/CN keys, `_flatten_*()` helpers format complex fields, rows written to openpyxl cells | FLOWING |
| `agent.py` | `SYSTEM_PROMPT` (static string) | Hardcoded in module | N/A: Static system prompt, not dynamic data | N/A |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full test suite passes | `.venv/Scripts/python -m pytest tests/ -v --tb=short` | 59 passed, 1 warning in 3.07s | PASS |
| Agent imports as CompiledStateGraph | `.venv/Scripts/python -c "import sys; sys.path.insert(0,'src'); from app.agents.testcase.agent import agent; print(type(agent).__name__)"` | CompiledStateGraph | PASS |
| SKILL.md YAML frontmatter valid | Validated by test_skills.py (25 tests) | All pass | PASS |
| Excel export creates valid file | Validated by test_excel_export.py (15 tests) | All pass | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| PARS-01 | 02-01, 02-03 | PDF parser (PyMuPDF4LLM, mode="page") | SATISFIED | `pdf.py`: PyMuPDF4LLMLoader with mode="page", 9 matches |
| PARS-05 | 02-01, 02-03 | MD5 hash caching | SATISFIED | `pdf.py`: _get_cache_key(), md5 cache dict, 29 matches |
| MIDW-01 | 02-01, 02-03 | PDFContextMiddleware extracts PDF from HumanMessage | SATISFIED | `pdf_context.py`: _extract_pdf_from_last_message(), additional_kwargs["attachments"] |
| MIDW-02 | 02-01, 02-03 | Session isolation (thread_id) | SATISFIED | `pdf_context.py`: _session_docs[thread_id], _get_thread_id(), 30 matches |
| MIDW-03 | 02-01, 02-03 | Immutable system prompt pattern | SATISFIED | `pdf_context.py`: _original_system_content, request.override(), 10 matches |
| MIDW-06 | 02-02, 02-03 | SkillsMiddleware filesystem loading | SATISFIED | `agent.py`: SkillsMiddleware(backend=skills_backend, sources=["/skills/"]) |
| SKILL-01 | 02-02, 02-03 | requirement-analysis skill | SATISFIED | `src/app/skills/requirement-analysis/SKILL.md`: 17419 bytes, PPDCS content |
| SKILL-02 | 02-02, 02-03 | test-strategy skill | SATISFIED | `src/app/skills/test-strategy/SKILL.md`: 13398 bytes, KUFI content |
| SKILL-03 | 02-02, 02-03 | test-case-design skill | SATISFIED | `src/app/skills/test-case-design/SKILL.md`: 13894 bytes, 6 design techniques |
| SKILL-06 | 02-02, 02-03 | output-formatter skill | SATISFIED | `src/app/skills/output-formatter/SKILL.md`: 8059 bytes, TC numbering |
| SKILL-07 | 02-02, 02-03 | 5-stage mandatory workflow | SATISFIED | `agent.py`: SYSTEM_PROMPT with 5-stage workflow table, 10 phase references |
| EXPT-01 | 02-02, 02-03 | Excel export with professional styles | SATISFIED | `tools.py`: PatternFill, Border, Alignment, Font, 6 matches |
| EXPT-02 | 02-02, 02-03 | TC numbering convention | SATISFIED | `output-formatter/SKILL.md` and `agent.py`: TC-[PROJECT]-[MODULE]-[NNN] |
| EXPT-04 | 02-02, 02-03 | Field extraction with multiple candidate keys | SATISFIED | `tools.py`: _extract_field(*keys) with EN/CN dual mapping, 15 matches |

No orphaned requirements. All 14 requirement IDs from REQUIREMENTS.md Phase 2 mapping are covered by at least one plan and have implementation evidence.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `agent.py` | 111 | "XXX" in `REQ-XXX` | Info | False positive: part of requirement reference format in system prompt text, not a code placeholder |
| `agent.py` | 128 | "XXX" in `[基于假设: XXX]` | Info | False positive: part of assumption annotation format in system prompt text, not a code placeholder |

No blockers or warnings found. All anti-pattern matches are false positives from Chinese instructional text in the system prompt.

### Human Verification Required

### 1. End-to-end PDF Upload and Test Case Generation

**Test:** Upload a real PDF document through the frontend chat interface and request test case generation ("全流程生成")
**Expected:** Agent processes PDF via middleware, executes 5-stage workflow, generates structured test cases, and offers Excel export
**Why human:** Requires running DeepSeek API, full LangGraph server, and frontend -- cannot verify programmatically without external services

### 2. Excel File Visual Quality

**Test:** Download the generated Excel file and open in Excel/WPS
**Expected:** Professional formatting with #366092 blue headers, white bold font, thin borders, auto-wrap, correct column widths
**Why human:** Visual formatting quality can only be confirmed by opening in spreadsheet software

### 3. Multi-turn Session Isolation

**Test:** Upload different PDFs in different chat threads simultaneously
**Expected:** Each thread maintains independent document context; switching threads does not leak PDF content
**Why human:** Requires concurrent interaction with running server and verification of cross-thread isolation behavior

### Gaps Summary

No gaps found. All 5 observable truths from the ROADMAP.md success criteria are verified at all 4 levels (exists, substantive, wired, data flowing). All 14 requirement IDs are satisfied with implementation evidence. The full test suite of 59 tests passes. The agent imports successfully as CompiledStateGraph.

One minor note: `extract_images=False` is the default in the PDF processor (PyMuPDF4LLMLoader requires an `images_parser` when images are enabled). This was a deliberate deviation documented in the Summary, and multimodal image extraction is explicitly deferred to Phase 4.

---

_Verified: 2026-05-12T10:30:00Z_
_Verifier: Claude (gsd-verifier)_
