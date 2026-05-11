# Phase 2: TestCase Agent MVP - Research

**Researched:** 2026-05-11
**Domain:** AI Agent middleware, Skills system, PDF parsing, Excel export
**Confidence:** HIGH

## Summary

Phase 2 transforms the TestCase agent stub into a fully functional test case generation agent. The implementation involves six major subsystems: (1) SkillsMiddleware integration to load 5 SKILL.md files from the filesystem, (2) PDFContextMiddleware to parse uploaded PDFs and inject content into the agent's system prompt, (3) PDF processing with PyMuPDF4LLM and MD5 caching, (4) Excel export tool with openpyxl professional formatting, (5) a comprehensive system prompt enforcing the 5-stage workflow, and (6) session isolation via thread_id.

The reference implementations in `../2026-05-07-ai-test-agent-system/` and `../2026-03-25-testing-agent-system/` provide battle-tested patterns for every subsystem. The key is adapting these patterns to the existing project structure (src/app/ layout, FilesystemBackend with workspace_dir).

**Primary recommendation:** Use the 2026-03-25 reference as the primary pattern for PDFContextMiddleware (v4 version with SkillsMiddleware compatibility), and the 2026-05-07 reference for the agent creation pattern and SKILL.md file structure. Copy and adapt the SKILL.md files from the reference code, then enhance with MFQ&PPDCS methodology content.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** 5-stage workflow (requirement analysis -> test strategy -> case design -> quality review -> output formatting)
- **D-02:** 5 Skills matching 5 stages: requirement-analysis, test-strategy, test-case-design, quality-review, output-formatter
- **D-03:** Strict sequential execution of 5 Skills via system prompt constraint
- **D-04:** MFQ&PPDCS methodology (PPDCS 5-dimension analysis, KUFI classification, coverage evaluation) incorporated into Skill prompts, not changing the 5-stage workflow structure
- **D-05:** 2-layer onion middleware: SkillsMiddleware (outer, loads SKILL.md) -> PDFContextMiddleware (inner, parses PDF and injects into system prompt)
- **D-06:** Session isolation built into PDFContextMiddleware internally, managed via thread_id dictionary
- **D-07:** PDF parsing uses PyMuPDF4LLM(mode="page", extract_images=True), converts PDF to Markdown text injected into agent system prompt
- **D-08:** MD5 hash caching mechanism to avoid re-parsing the same document
- **D-09:** LLM generates Markdown test cases -> backend parses Markdown to extract fields -> openpyxl writes Excel -> user downloads file via chat interface
- **D-10:** Full numbering convention TC-[PROJECT]-[MODULE]-[NNN], user provides project and module names in conversation, Agent auto-generates numbering
- **D-11:** Excel professional formatting: header style, borders, alignment, auto-wrap
- **D-12:** SKILL.md files unified in src/app/skills/ directory, shared by all agents
- **D-13:** SkillsMiddleware loads SKILL.md from filesystem and injects into agent system prompt
- **D-14:** 5-stage mandatory workflow (SKILL-07) implemented through system prompt constraint

### Claude's Discretion
- Specific content template and Prompt design for SKILL.md files
- Immutable system prompt pattern implementation details for PDFContextMiddleware
- Specific column names and style parameters for Excel export
- Specific regex and field extraction logic for Markdown parser

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PARS-01 | PDF parser (PyMuPDF4LLM, mode="page", extract_images=True) | PDF processing module pattern from reference code, langchain-pymupdf4llm package |
| PARS-05 | MD5 hash caching to avoid re-parsing | MD5 cache pattern documented in reference processors/pdf.py |
| MIDW-01 | PDFContextMiddleware (extract base64 PDF from HumanMessage attachments -> parse -> inject SystemMessage) | Full v4 PDFContextMiddleware reference with SkillsMiddleware compatibility |
| MIDW-02 | Session isolation (thread_id level independent document state) | _session_docs dict keyed by thread_id from langgraph.config.get_config() |
| MIDW-03 | Immutable system prompt pattern (constructor injection, request override) | Constructor-based original_system_prompt with request.override() pattern |
| MIDW-06 | SkillsMiddleware (filesystem SKILL.md loading) | DeepAgents SkillsMiddleware API fully documented from source |
| SKILL-01 | requirement-analysis skill | Reference SKILL.md + MFQ PPDCS 5-dimension model |
| SKILL-02 | test-strategy skill | Reference SKILL.md + KUFI classification |
| SKILL-03 | test-case-design skill | Reference SKILL.md + 6 design techniques |
| SKILL-06 | output-formatter skill | Reference SKILL.md + TC numbering convention |
| SKILL-07 | 5-stage mandatory workflow | System prompt enforcement pattern |
| EXPT-01 | Excel export tool (openpyxl, professional styles) | Full export_test_cases_to_excel tool from reference code |
| EXPT-02 | TC numbering convention TC-[PROJECT]-[MODULE]-[NNN] | output-formatter SKILL.md defines exact format |
| EXPT-04 | Field mapping and data extraction (supports nested formats) | _extract_field with multiple candidate keys, _flatten_* helper functions |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| DeepAgents | >=0.5.5 (installed 0.2.8, needs upgrade) | Agent framework | Provides SkillsMiddleware, FilesystemBackend, create_deep_agent. Required by project CLAUDE.md. |
| langchain-pymupdf4llm | 0.5.0 (not yet installed) | PDF to Markdown conversion | Cleanest Markdown output from PDFs, supports table extraction and image extraction. Used in all reference implementations. |
| openpyxl | 3.1.5 (needs venv install) | Excel file generation | Standard Python Excel library. Reference code uses PatternFill, Border, Side, Alignment for professional formatting. |
| PyMuPDF4LLM (pymupdf4llm) | 0.1.9 (dependency of langchain-pymupdf4llm) | PDF parsing engine | Underlying engine for langchain-pymupdf4llm, provides PyMuPDF4LLMLoader |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| hashlib | stdlib | MD5 caching | Generate cache keys from PDF binary data |
| langchain-core | 1.1.1 (installed) | Message types | HumanMessage, SystemMessage for middleware message manipulation |
| langgraph | 1.0.3 (installed) | Thread config | get_config() for thread_id extraction in middleware |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| langchain-pymupdf4llm | PyMuPDF directly | langchain wrapper provides Loader abstraction, table_strategy, integration with LLMImageBlobParser for Phase 4 |
| openpyxl | xlsxwriter | openpyxl has better read+write support and is used in all reference code |

**Installation:**
```bash
# In project venv
cd D:/test_agent/smart-test-platform
uv pip install langchain-pymupdf4llm openpyxl
# Also need to upgrade DeepAgents to >= 0.5.5
uv pip install "deepagents>=0.5.5"
```

**Version verification:**
- deepagents: 0.2.8 installed (needs upgrade to >=0.5.5 per pyproject.toml)
- langchain-pymupdf4llm: 0.5.0 (available, not yet installed)
- openpyxl: 3.1.5 (available globally, needs venv install)
- pymupdf4llm: 0.1.9 (dependency, auto-installed with langchain-pymupdf4llm)

## Architecture Patterns

### Recommended Project Structure
```
src/app/
  agents/
    testcase/
      agent.py          # Modified: add middleware, tools, system_prompt
      tools.py           # New: Excel export tool + PDF extraction tool
  middleware/
    __init__.py          # New
    pdf_context.py       # New: PDFContextMiddleware
  processors/
    __init__.py          # New
    pdf.py               # New: PDF processing with MD5 cache
  skills/                # New: Shared skills directory
    requirement-analysis/
      SKILL.md
    test-strategy/
      SKILL.md
    test-case-design/
      SKILL.md
    quality-review/
      SKILL.md
    output-formatter/
      SKILL.md
```

### Pattern 1: Agent Creation with Middleware Chain
**What:** Create TestCase agent with SkillsMiddleware and PDFContextMiddleware in onion layers
**When to use:** This is the core agent creation pattern for Phase 2
**Example:**
```python
# Source: Reference code 2026-05-07/agents/testcase/agent.py
from deepagents import create_deep_agent as create_agent
from deepagents.backends import FilesystemBackend
from deepagents.middleware import SkillsMiddleware

# SkillsMiddleware uses backend to load SKILL.md from filesystem
# sources is a list of paths within the backend's root_dir
skills_middleware = SkillsMiddleware(
    backend=file_backend,
    sources=["/testcase/skills/"]  # path within backend root
)

agent = create_agent(
    model=llm,
    tools=[export_test_cases_to_excel, extract_pdf_text_from_file],
    backend=file_backend,
    middleware=[
        skills_middleware,       # outer layer: loads skills
        PDFContextMiddleware(),  # inner layer: injects PDF context
    ],
    system_prompt=SYSTEM_PROMPT,
)
```

### Pattern 2: PDFContextMiddleware v4 (SkillsMiddleware Compatible)
**What:** PDF middleware that preserves Skills content when injecting PDF text
**When to use:** When SkillsMiddleware and PDFContextMiddleware coexist
**Key design points:**
- Constructor accepts `original_system_prompt` to avoid runtime snapshot pollution
- Uses `request.system_message` (already containing Skills content) as base, not the constructor's original
- Thread_id from `langgraph.config.get_config()["configurable"]["thread_id"]`
- `_session_docs: dict[str, str]` keyed by thread_id for session isolation
- `_session_pdf_hash: dict[str, str]` keyed by thread_id for MD5 dedup
- Only scans the LAST user message for PDF attachments

**Example:**
```python
# Source: Reference code 2026-03-25/middleware/pdf_context.py
class PDFContextMiddleware(AgentMiddleware):
    def __init__(self, original_system_prompt=None, enable_cache=True, max_content_length=80_000):
        self._processor = PDFProcessor(enable_cache=enable_cache)
        self._original_system_content = original_system_prompt
        self._session_docs: dict[str, str] = {}
        self._session_pdf_hash: dict[str, str] = {}

    async def awrap_model_call(self, request, handler):
        thread_id = self._get_thread_id()  # from langgraph.config.get_config()

        # Extract PDF from last user message
        pdf_info = self._extract_pdf_from_last_message(request)
        if pdf_info:
            pdf_data, pdf_name = pdf_info
            pdf_hash = hashlib.md5(pdf_data).hexdigest()
            if self._session_pdf_hash.get(thread_id) != pdf_hash:
                text = self._processor.extract_text(pdf_data, pdf_name)
                if text:
                    self._session_docs[thread_id] = text
                    self._session_pdf_hash[thread_id] = pdf_hash

        # Inject PDF using current system_message as base (preserves Skills)
        current_doc = self._session_docs.get(thread_id)
        if current_doc:
            request = request.override(
                system_message=self._build_system_message(current_doc, request.system_message)
            )
        return await handler(request)
```

### Pattern 3: SkillsMiddleware with FilesystemBackend
**What:** Load SKILL.md files from filesystem into agent system prompt
**When to use:** For all agents that need skill definitions
**Key API details from DeepAgents source (0.2.8 installed):**
- Constructor: `SkillsMiddleware(backend=..., sources=[...])`
- `sources`: list of paths within backend's root_dir where skill directories exist
- Each skill is a directory containing `SKILL.md` with YAML frontmatter
- YAML frontmatter requires: `name` (must match directory name), `description`
- Skills are loaded once per session (before_agent), cached in state
- Progressive disclosure: name/description in system prompt, full content via `read_file`
- The backend must be a FilesystemBackend (or StateBackend) with the skills directories accessible

**Example:**
```python
# Source: deepagents/middleware/skills.py (installed source)
from deepagents.backends import FilesystemBackend

# FilesystemBackend must have skills accessible at the source paths
backend = FilesystemBackend(root_dir=workspace_dir, virtual_mode=True)
middleware = SkillsMiddleware(
    backend=backend,
    sources=["/testcase/skills/"]
)
```

### Pattern 4: Excel Export with openpyxl
**What:** Professional Excel formatting with test case fields
**When to use:** When exporting test cases to .xlsx files
**Example:**
```python
# Source: Reference code 2026-05-07/agents/testcase/tools.py
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side

_HEADER_FILL = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
_HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
_BORDER = Border(
    left=Side(style="thin"), right=Side(style="thin"),
    top=Side(style="thin"), bottom=Side(style="thin"),
)
_ALIGNMENT_WRAP = Alignment(vertical="top", wrap_text=True)

# 10 columns: 用例编号, 用例标题, 所属模块, 用例类型, 优先级,
#             前置条件, 测试步骤, 测试数据, 预期结果, 备注
```

### Pattern 5: MD5 Caching for PDF Documents
**What:** Avoid re-parsing identical PDFs across sessions
**When to use:** In PDFProcessor to cache parsed results
**Example:**
```python
# Source: Reference code processors/pdf.py
import hashlib

def _get_cache_key(data: bytes, filename: str) -> str:
    pdf_hash = hashlib.md5(data).hexdigest()
    return f"{filename}_{pdf_hash}"

# Module-level cache dict
_pdf_cache: dict[str, str] = {}

def extract_pdf_text(pdf_data: bytes, filename: str, cache=None) -> str:
    cache_key = _get_cache_key(pdf_data, filename)
    if cache is not None and cache_key in cache:
        return cache[cache_key]
    # ... parse and cache result
```

### Anti-Patterns to Avoid
- **Overwriting system_message in PDFContextMiddleware with original prompt**: Must use current `request.system_message` as base to preserve SkillsMiddleware content. The 2026-03-25 v4 reference explicitly fixes this.
- **Scanning all message history for PDFs**: Only scan the LAST user message. Old reference code scanned all history causing repeated parsing every turn.
- **Hardcoding workspace_dir with absolute path**: Use relative path resolution from `__file__` like Phase 1 already does (`Path(__file__).parent.parent.parent.parent.parent / "workspace"`).
- **Putting skills in workspace directory**: CONTEXT.md D-12 specifies `src/app/skills/` as the shared skills directory. The FilesystemBackend root must include this path.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PDF parsing | Custom PDF text extraction | PyMuPDF4LLMLoader from langchain-pymupdf4llm | Handles tables, images, multi-page, encoding edge cases |
| Skills loading | Custom SKILL.md parser | DeepAgents SkillsMiddleware | Already handles YAML frontmatter, validation, progressive disclosure, caching |
| Agent middleware | Custom middleware chain | DeepAgents onion middleware + AgentMiddleware base class | Official middleware API handles state schema, before_agent, wrap_model_call |
| Excel formatting | Manual XML/XLSX generation | openpyxl with PatternFill, Border, Alignment | Professional formatting requires correct XML styles, openpyxl handles all edge cases |
| Thread isolation | Custom session management | langgraph.config.get_config() for thread_id | Official API, works with LangGraph's built-in session management |

**Key insight:** DeepAgents provides SkillsMiddleware as a built-in middleware. It handles loading, parsing, validation, and injection of SKILL.md files automatically. The only custom code needed is the PDFContextMiddleware and the tools.

## Runtime State Inventory

This is a greenfield implementation phase (not a rename/refactor), so no runtime state migration is required. However, note:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None -- fresh workspace directory | Create workspace/uploads/ dir for PDF temp files |
| Live service config | None -- agent stub has empty middleware/tools | Populate middleware list and tools |
| OS-registered state | None | None |
| Secrets/env vars | DEEPSEEK_API_KEY already configured in .env | None |
| Build artifacts | None -- no compiled artifacts | None |

## Common Pitfalls

### Pitfall 1: SkillsMiddleware Source Path Mismatch
**What goes wrong:** SkillsMiddleware cannot find SKILL.md files because the source path doesn't match the FilesystemBackend root_dir structure.
**Why it happens:** The `sources` parameter is a path RELATIVE TO the backend's root_dir, not an absolute filesystem path. If backend root is `workspace/` and source is `/testcase/skills/`, then files must be at `workspace/testcase/skills/`.
**How to avoid:** Ensure the FilesystemBackend root_dir contains the skill directories at the expected source paths. Since D-12 specifies `src/app/skills/`, the backend root must be `src/app/` with sources `["/skills/"]`, OR a separate backend with root at `src/app/skills/` and sources `["/"]`.
**Warning signs:** Agent starts but SkillsMiddleware logs "no valid YAML frontmatter found" or "(No skills available yet)".

### Pitfall 2: PDFContextMiddleware Overwrites Skills Content
**What goes wrong:** PDF injection replaces the system prompt, removing Skills content injected by SkillsMiddleware.
**Why it happens:** Onion model executes SkillsMiddleware first (outer), then PDFContextMiddleware (inner). If PDF middleware uses `_original_system_content` instead of `request.system_message`, it overwrites Skills content.
**How to avoid:** Use the v4 pattern from 2026-03-25 reference: `_build_system_message(current_doc, request.system_message)` -- always use current system_message as base.
**Warning signs:** Agent works with PDF but doesn't follow Skill workflows.

### Pitfall 3: DeepAgents Version Mismatch
**What goes wrong:** Installed DeepAgents is 0.2.8 but pyproject.toml requires >=0.5.5. SkillsMiddleware API may differ.
**Why it happens:** The venv may have been created with an older version that wasn't upgraded.
**How to avoid:** Run `uv pip install "deepagents>=0.5.5"` before implementation. Verify with `uv pip show deepagents`.
**Warning signs:** Import errors, missing methods, different API signatures than reference code.

### Pitfall 4: Windows Temp File Locking
**What goes wrong:** PDF temp files cannot be deleted because PyMuPDF4LLM still holds a file handle.
**Why it happens:** Windows enforces file locks more strictly than Unix. NamedTemporaryFile with delete=False + explicit close is needed.
**How to avoid:** Use the `_safe_delete_temp_file` pattern from reference code with retry logic.
**Warning signs:** Warning logs about temp file cleanup, disk space filling up.

### Pitfall 5: thread_id Not Available in Middleware Context
**What goes wrong:** `get_config()` raises exception or returns no thread_id.
**Why it happens:** Running agent outside LangGraph server context (e.g., direct invoke without config).
**How to avoid:** Always provide fallback thread_id `"__default__"` when config is unavailable. Reference code handles this gracefully.
**Warning signs:** All sessions share the same PDF context, or AttributeError on get_config().

### Pitfall 6: SKILL.md name Must Match Directory Name
**What goes wrong:** SkillsMiddleware skips a SKILL.md because the `name` field doesn't match the parent directory.
**Why it happens:** DeepAgents SkillsMiddleware validates that `name` in YAML frontmatter equals the directory name (per Agent Skills specification).
**How to avoid:** Always name the directory and the `name` field identically (e.g., directory `requirement-analysis/` has `name: requirement-analysis` in SKILL.md).
**Warning signs:** Skill missing from system prompt, "name must match directory name" warning in logs.

## Code Examples

### PDF Processing with MD5 Cache
```python
# Source: Reference code processors/pdf.py pattern
import hashlib
import tempfile
import os
from langchain_pymupdf4llm import PyMuPDF4LLMLoader

_pdf_cache: dict[str, str] = {}

def extract_pdf_text(pdf_data: bytes, filename: str = "unknown.pdf", cache: dict | None = None) -> str:
    cache_key = f"{filename}_{hashlib.md5(pdf_data).hexdigest()}"
    if cache is not None and cache_key in cache:
        return cache[cache_key]

    temp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    try:
        temp_file.write(pdf_data)
        temp_file.flush()
        os.fsync(temp_file.fileno())
        temp_path = temp_file.name
    finally:
        temp_file.close()

    try:
        loader = PyMuPDF4LLMLoader(
            temp_path,
            mode="page",          # D-07: mode="page"
            extract_images=True,   # D-07: extract_images=True
            table_strategy="lines"
        )
        documents = loader.load()
        text = documents[0].page_content if documents else ""

        if cache is not None:
            cache[cache_key] = text
        return text
    finally:
        _safe_delete_temp_file(temp_path)
```

### Excel Export Tool (LangChain @tool)
```python
# Source: Reference code 2026-05-07/agents/testcase/tools.py
from langchain.tools import tool
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side

@tool
def export_test_cases_to_excel(
    test_cases: list[dict],
    output_path: str,
    sheet_name: str = "测试用例",
) -> str:
    """Export test cases to a professionally formatted Excel file."""
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name

    headers = ["用例编号", "用例标题", "所属模块", "用例类型", "优先级",
               "前置条件", "测试步骤", "测试数据", "预期结果", "备注"]
    ws.append(headers)
    # Apply header style, borders, alignment, column widths...
    # Write data rows with _extract_field for flexible key mapping...
    wb.save(output_path)
    return str(Path(output_path).resolve())
```

### SKILL.md File Format
```markdown
---
name: requirement-analysis
description: When a user provides requirement documents, PRD, user stories, or test requirement input, immediately activate this Skill. Responsible for systematic deep analysis of requirements, extracting test points, building a feature matrix, and identifying risk areas.
---

# Requirement Deep Analysis Skill

## Activation Scenarios
- User uploads or pastes requirement documents
...

## Execution Flow
### Step 1: Document Structure Parsing
...
```

### Session-Isolated PDF Middleware
```python
# Source: Reference 2026-03-25 middleware/pdf_context.py (v4)
def _get_thread_id(self) -> str:
    try:
        from langgraph.config import get_config
        config = get_config()
        tid = config.get("configurable", {}).get("thread_id")
        if tid:
            return str(tid)
    except Exception:
        pass
    return "__default__"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| PyPDF2 for PDF parsing | PyMuPDF4LLM | 2024+ | Cleaner Markdown output, better table extraction |
| Raw system_message replacement | request.override() immutable pattern | DeepAgents 0.5+ | No pickle/serialization issues |
| Scanning all history for PDFs | Only last user message | 2026-03-25 v4 | Prevents repeated parsing every turn |
| Simple dict cache | Module-level dict with MD5 hash keys | Standard pattern | Safe dedup across sessions |
| Skills in workspace dir | Shared src/app/skills/ directory | CONTEXT.md D-12 | All agents share same skills |

**Deprecated/outdated:**
- PyPDF2: Replaced by PyMuPDF4LLM for better quality
- Modifying system_message content directly: Use request.override() for immutability
- Global PDF cache without per-session isolation: Use thread_id keyed dicts

## Open Questions

1. **DeepAgents Version Gap**
   - What we know: Installed 0.2.8, pyproject.toml requires >=0.5.5. SkillsMiddleware API exists in 0.2.8 (confirmed via import test and source read).
   - What's unclear: Whether 0.2.8 SkillsMiddleware is fully compatible with the reference code patterns that were built against 0.5.x. The SkillsMiddleware source code we read IS from the 0.2.8 installation and looks complete.
   - Recommendation: Upgrade to >=0.5.5 as specified in pyproject.toml. The upgrade should be a pre-implementation step in Wave 0.

2. **FilesystemBackend Skills Path Resolution**
   - What we know: D-12 says skills go in `src/app/skills/`. FilesystemBackend uses `root_dir` + source paths. Current agent uses `workspace/` as backend root.
   - What's unclear: Whether to use the same FilesystemBackend for both workspace files and skills, or create a separate backend for skills.
   - Recommendation: Use a separate FilesystemBackend with root_dir pointing to `src/app/` and source `["/skills/"]`. The reference code uses separate backends for skills vs workspace.

3. **Frontend Download Mechanism**
   - What we know: Current ChatMessage component renders markdown but has no file download support. The LangGraph API serves the agent.
   - What's unclear: How to deliver the Excel file to the user. Options: (a) save to workspace and return a URL, (b) embed download link in AI message, (c) add a custom API endpoint.
   - Recommendation: Save Excel to workspace directory, return file path in tool response, agent includes a download instruction in its message. A custom FastAPI endpoint or LangGraph static file serving may be needed. This is Claude's discretion area.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | Backend runtime | Yes | 3.12.12 (venv) | -- |
| DeepAgents >= 0.5.5 | Agent framework | Wrong version | 0.2.8 (needs upgrade) | -- |
| langchain-pymupdf4llm | PDF parsing | No | -- | Must install |
| openpyxl | Excel export | No (not in venv) | 3.1.5 (global only) | Must install in venv |
| langchain-core | Message types | Yes | 1.1.1 | -- |
| langgraph | Thread config | Yes | 1.0.3 | -- |

**Missing dependencies with no fallback:**
- DeepAgents >= 0.5.5: Must upgrade before implementation. `uv pip install "deepagents>=0.5.5"`
- langchain-pymupdf4llm: Must install. `uv pip install langchain-pymupdf4llm`
- openpyxl: Must install in venv. `uv pip install openpyxl`

**Missing dependencies with fallback:**
- None

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (standard for Python, needs install) |
| Config file | None -- see Wave 0 |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ -v --tb=short` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PARS-01 | PDF parsing produces Markdown text | unit | `pytest tests/test_pdf_processor.py -x` | No -- Wave 0 |
| PARS-05 | MD5 cache returns cached result for same PDF | unit | `pytest tests/test_pdf_processor.py::test_md5_cache -x` | No -- Wave 0 |
| MIDW-01 | PDFContextMiddleware extracts PDF from attachments | unit | `pytest tests/test_pdf_middleware.py -x` | No -- Wave 0 |
| MIDW-02 | Different thread_ids maintain separate doc state | unit | `pytest tests/test_pdf_middleware.py::test_session_isolation -x` | No -- Wave 0 |
| MIDW-03 | Immutable system prompt preserves original content | unit | `pytest tests/test_pdf_middleware.py::test_immutable_prompt -x` | No -- Wave 0 |
| MIDW-06 | SkillsMiddleware loads SKILL.md and injects into prompt | unit | `pytest tests/test_skills_middleware.py -x` | No -- Wave 0 |
| SKILL-01~03,06 | SKILL.md files exist and have valid frontmatter | smoke | `pytest tests/test_skills.py -x` | No -- Wave 0 |
| SKILL-07 | System prompt enforces 5-stage workflow order | manual | Manual inspection | N/A |
| EXPT-01 | Excel file has professional formatting | unit | `pytest tests/test_excel_export.py -x` | No -- Wave 0 |
| EXPT-02 | TC numbering follows TC-[PROJECT]-[MODULE]-[NNN] | unit | `pytest tests/test_excel_export.py::test_tc_numbering -x` | No -- Wave 0 |
| EXPT-04 | Field extraction handles nested formats | unit | `pytest tests/test_excel_export.py::test_field_extraction -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/ -x -q`
- **Per wave merge:** `pytest tests/ -v --tb=short`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_pdf_processor.py` -- covers PARS-01, PARS-05
- [ ] `tests/test_pdf_middleware.py` -- covers MIDW-01, MIDW-02, MIDW-03
- [ ] `tests/test_skills_middleware.py` -- covers MIDW-06
- [ ] `tests/test_skills.py` -- covers SKILL-01, SKILL-02, SKILL-03, SKILL-06
- [ ] `tests/test_excel_export.py` -- covers EXPT-01, EXPT-02, EXPT-04
- [ ] `tests/conftest.py` -- shared fixtures
- [ ] Framework install: `uv pip install pytest` -- if none detected

## Sources

### Primary (HIGH confidence)
- DeepAgents SkillsMiddleware source code (installed at `.venv/Lib/site-packages/deepagents/middleware/skills.py`) -- Full API: constructor, SkillMetadata, frontmatter parsing, progressive disclosure, source path resolution
- Reference implementation `2026-05-07-ai-test-agent-system/agents/testcase/agent.py` -- Agent creation pattern with SkillsMiddleware + PDFContextMiddleware
- Reference implementation `2026-05-07-ai-test-agent-system/agents/testcase/tools.py` -- Complete Excel export tool with openpyxl
- Reference implementation `2026-03-25-testing-agent-system/middleware/pdf_context.py` -- PDFContextMiddleware v4 with SkillsMiddleware compatibility
- Reference implementation `2026-03-25-testing-agent-system/processors/pdf.py` -- PDF processing with MD5 cache
- Reference SKILL.md files from `2026-05-07-ai-test-agent-system/workspace/testcase/skills/` -- All 5 skill definitions
- MFQ&PPDCS methodology document at `c:\Users\yuanyb\Downloads\测试用例生成模块_MFQ_PPDCS_重构与产物输出方案_v1.0.md`

### Secondary (MEDIUM confidence)
- DeepAgents API verified via import tests in project venv
- openpyxl API verified via reference code (PatternFill, Border, etc.)
- langchain-pymupdf4llm availability verified via `uv pip install --dry-run`

### Tertiary (LOW confidence)
- None -- all findings verified against installed code or reference implementations

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all libraries verified installed or available, reference code uses exact same stack
- Architecture: HIGH - all patterns directly from reference implementations and DeepAgents source code
- Pitfalls: HIGH - identified from actual reference code evolution (v3->v4 PDF middleware fix)

**Research date:** 2026-05-11
**Valid until:** 2026-06-11 (stable, no fast-moving dependencies)
