# Phase 4: Advanced TestCase - Research

**Researched:** 2026-05-13
**Domain:** Dual-model middleware, unified file processing, multi-format export, test-data-generator Skill
**Confidence:** HIGH

## Summary

Phase 4 extends the TestCase Agent with five major capabilities: (1) DynamicModelSelection middleware that switches between DeepSeek (text) and GPT-4o (multimodal) based on detected content type, (2) refactoring PDFContextMiddleware into a unified FileContextMiddleware supporting PDF, images, and Excel, (3) a test-data-generator Skill for generating four categories of concrete test data, (4) multi-format export (CSV, JSON, Markdown) in addition to existing Excel, and (5) a frontend multimodal toggle in ConfigDialog.

The codebase is well-structured for these extensions. The onion middleware pattern (SkillsMiddleware outer, PDFContextMiddleware inner) already has a comment block predicting DynamicModelSelection insertion between them. ModelRequest.override() supports `model=` parameter for swapping the LLM at runtime. langchain-openai 1.2.1 is already installed in .venv and ChatOpenAI(model="gpt-4o") works. Shadcn Switch component already exists in webui. The quality-review Skill (SKILL-05) is fully implemented from Phase 2 -- no work needed there.

**Primary recommendation:** Extend the existing middleware chain and processor pattern rather than building new abstractions. The DynamicModelSelection middleware is a thin wrapper that detects image content and calls request.override(model=gpt4o_model). FileContextMiddleware reuses PDFContextMiddleware's session isolation and caching, adding two new processor dispatches.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** DynamicModelSelection middleware replaces request.model to switch models -- detects image -> creates GPT-4o model instance, pure text -> pass through DeepSeek
- **D-02:** Detection mechanism -- scan HumanMessage for image_url type content blocks and additional_kwargs.attachments with image/* MIME type
- **D-03:** Multimodal toggle in ConfigDialog -- Switch component controlling ENABLE_PDF_MULTIMODAL parameter
- **D-04:** Middleware order -- SkillsMiddleware(outer) -> DynamicModelSelection(middle) -> FileContextMiddleware(inner) -> LLM
- **D-05:** Refactor PDFContextMiddleware to unified FileContextMiddleware -- dispatch by MIME type (PDF -> PyMuPDF4LLM, Image -> GPT-4o, Excel -> openpyxl)
- **D-06:** Image uses GPT-4o multimodal model to parse content, return text description injected into system_message
- **D-07:** Excel uses openpyxl, convert each sheet to Markdown table injected into system_message
- **D-08:** Three file types unified injection into system_message, preserve thread_id isolation and MD5 dedup cache
- **D-09:** Create independent test-data-generator Skill directory and SKILL.md -- 7th Skill
- **D-10:** Generate concrete data values (e.g., "admin' OR 1=1 --"), not just categories or rules
- **D-11:** Four data categories: valid, boundary, invalid, security-attack
- **D-12:** Unified export_test_cases function (format param: excel/csv/json/markdown) replacing export_test_cases_to_excel
- **D-13:** CSV format -- UTF-8 with BOM, comma separated, double-quote escaping, 10 standard columns, compatible with ZenTao/TestRail
- **D-14:** JSON format -- Jira Xray compatible ({"testCases": [{"testCaseKey": ..., "summary": ..., "steps": [...]}]})
- **D-15:** quality-review (SKILL-05) fully implemented in Phase 2, no Phase 4 work needed

### Claude's Discretion
- DynamicModelSelection middleware implementation details (how to create GPT-4o model instance, how to detect image_url content blocks)
- FileContextMiddleware internal processor dispatch logic
- test-data-generator SKILL.md prompt content and four data category generation guidance
- CSV/JSON/Markdown export field mapping and format details
- ConfigDialog Switch UI details

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PARS-02 | Image parsing via GPT-4o multimodal model | D-06: ChatOpenAI(model="gpt-4o") with langchain-openai 1.2.1 (already installed). Image content sent as image_url blocks to GPT-4o, text description returned and injected into system_message. |
| PARS-03 | Excel file parsing via openpyxl | D-07: openpyxl 3.1.5 already installed. Read workbook, convert each sheet to Markdown table, inject into system_message via FileContextMiddleware. |
| PARS-06 | Dual-model dynamic switching middleware | D-01/D-04: DynamicModelSelection as middle layer in onion. Uses request.override(model=gpt4o_model) when images detected. ModelRequest.override() confirmed to support model parameter. |
| MIDW-04 | DynamicModelSelection middleware (onion layer 2) | D-01/D-04: New AgentMiddleware subclass. Scans messages for image_url and image/* attachments. Middleware chain: Skills -> DynamicModel -> FileContext -> LLM. |
| SKILL-04 | Test data generation skill (valid/boundary/invalid/security) | D-09/D-10/D-11: New src/app/skills/test-data-generator/SKILL.md. Follows existing SKILL.md format (YAML frontmatter + Markdown). Generates concrete values, not categories. |
| SKILL-05 | Quality review skill (four-dimensional scoring) | D-15: Already fully implemented in Phase 2. No work needed -- just mark complete. quality-review/SKILL.md has Completeness 30%, Accuracy 25%, Validity 25%, Executability 20%. |
| EXPT-03 | Multi-format export (CSV/JSON/Markdown) | D-12/D-13/D-14: Unified export_test_cases tool with format parameter. Reuses existing field extraction helpers. CSV: UTF-8 BOM for ZenTao/TestRail. JSON: Jira Xray format. Markdown: table format. |
| UI-07 | Multimodal toggle (ENABLE_PDF_MULTIMODAL) | D-03: Switch component in ConfigDialog.tsx. Shadcn Switch already available at webui/src/components/ui/switch.tsx. State saved in StandaloneConfig, passed to backend via additional_kwargs or config. |
</phase_requirements>

## Standard Stack

### Core (Already Installed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| langchain-openai | 1.2.1 | GPT-4o multimodal model | Already in .venv. ChatOpenAI(model="gpt-4o") verified working. init_chat_model("openai:gpt-4o") also works. |
| langchain | 1.2.18 | LLM abstractions, init_chat_model | Core framework. ModelRequest.override(model=...) confirmed for dynamic model switching. |
| langchain-deepseek | 1.0.1 | DeepSeek text model | Default text model. init_chat_model("deepseek:deepseek-chat") already in agent.py. |
| deepagents | 0.5.9 | Agent framework, AgentMiddleware | Provides create_deep_agent, SkillsMiddleware, FilesystemBackend. Middleware base class confirmed. |
| openpyxl | 3.1.5 | Excel read/write | Already used for Excel export. Will also be used for reading uploaded Excel files. |
| pillow | 12.2.0 | Image processing | Available if needed for image preprocessing before GPT-4o. Not strictly required since GPT-4o accepts base64 directly. |
| pydantic-settings | 2.14.1 | Configuration management | Settings class in config.py. Will add openai_api_key and ENABLE_PDF_MULTIMODAL fields. |

### Frontend (Already Installed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| @base-ui/react | ^1.4.1 | Switch primitive component | Shadcn Switch component already built on this. Available at webui/src/components/ui/switch.tsx. |
| nuqs | ^2.8.9 | URL state management | Could be used for multimodal toggle state persistence in URL, though localStorage (via StandaloneConfig) is simpler. |

### No New Installations Required
All dependencies for Phase 4 are already installed. No `npm install` or `pip install` commands needed.

**Verification:**
- langchain-openai 1.2.1: confirmed via importlib.metadata
- ChatOpenAI(model="gpt-4o"): verified instantiation succeeds
- init_chat_model("openai:gpt-4o"): verified returns ChatOpenAI instance
- openpyxl 3.1.5: confirmed
- Shadcn Switch component: exists at webui/src/components/ui/switch.tsx

## Architecture Patterns

### Current Middleware Chain (Phase 2-3)
```
|-- SkillsMiddleware (outer)         -> loads 6 SKILL.md into system prompt
|   |-- PDFContextMiddleware (inner)  -> injects PDF document context
|   |-- LLM (deepseek:deepseek-chat)
```

### Target Middleware Chain (Phase 4)
```
|-- SkillsMiddleware (outer)              -> loads 7 SKILL.md (incl. test-data-generator)
|   |-- DynamicModelSelection (middle)    -> detects images -> swaps model to GPT-4o
|   |   |-- FileContextMiddleware (inner)  -> injects PDF/Image/Excel context
|   |   |-- LLM (deepseek or gpt-4o, selected by DynamicModelSelection)
```

### Recommended Project Structure Changes
```
src/app/
  agents/testcase/
    agent.py           -- MODIFY: add DynamicModelSelection to middleware chain, update tools
    tools.py           -- MODIFY: add unified export_test_cases, keep export_test_cases_to_excel as alias
  middleware/
    pdf_context.py     -- RENAME/REFACTOR to file_context.py (FileContextMiddleware)
    dynamic_model.py   -- NEW: DynamicModelSelection middleware
  processors/
    pdf.py             -- KEEP: existing PDFProcessor (no changes needed)
    image.py           -- NEW: ImageProcessor (GPT-4o based)
    excel.py           -- NEW: ExcelProcessor (openpyxl based)
  core/
    config.py          -- MODIFY: add openai_api_key, enable_pdf_multimodal
  skills/
    test-data-generator/  -- NEW: SKILL.md for test data generation
webui/src/
  app/components/
    ConfigDialog.tsx   -- MODIFY: add ENABLE_PDF_MULTIMODAL Switch
  lib/
    config.ts          -- MODIFY: add enablePdfMultimodal to StandaloneConfig
  app/hooks/
    useChat.ts         -- MODIFY: pass enablePdfMultimodal via additional_kwargs or config
```

### Pattern 1: DynamicModelSelection Middleware
**What:** AgentMiddleware subclass that inspects messages for image content and swaps the model.
**When to use:** Every LLM call passes through this middleware.
**Implementation:**

```python
# src/app/middleware/dynamic_model.py
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage

class DynamicModelSelection(AgentMiddleware):
    def __init__(self, vision_model_name: str = "openai:gpt-4o", api_key: str = ""):
        self._vision_model = init_chat_model(vision_model_name, api_key=api_key)

    async def awrap_model_call(self, request, handler):
        if self._has_image_content(request):
            request = request.override(model=self._vision_model)
        return await handler(request)

    def _has_image_content(self, request) -> bool:
        # Check messages for image_url content blocks
        # Check attachments for image/* MIME types
        ...
```

**Key API verified:** `ModelRequest.override(model=...)` is supported -- it creates a new ModelRequest with the model replaced. The handler then calls the overridden model.

### Pattern 2: FileContextMiddleware (Refactored from PDFContextMiddleware)
**What:** Unified middleware that dispatches file processing by MIME type.
**When to use:** Every LLM call (innermost middleware layer).
**Refactoring approach:**

```python
# src/app/middleware/file_context.py (renamed from pdf_context.py)
class FileContextMiddleware(AgentMiddleware):
    def __init__(self, ...):
        self._pdf_processor = PDFProcessor(...)
        self._image_processor = ImageProcessor(...)
        self._excel_processor = ExcelProcessor()
        # Keep existing session isolation dicts
        self._session_docs: dict[str, str] = {}
        self._session_file_hash: dict[str, str] = {}

    def _extract_file_from_last_message(self, request):
        # Extended: check for PDF, image, and Excel MIME types
        # Return (data, filename, mime_type) tuple
        ...

    def _process_file(self, data, filename, mime_type):
        # Dispatch by MIME type
        if mime_type == "application/pdf":
            return self._pdf_processor.extract_text(data, filename)
        elif mime_type.startswith("image/"):
            return self._image_processor.extract_text(data, filename)
        elif mime_type in ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           "application/vnd.ms-excel"):
            return self._excel_processor.extract_text(data, filename)
        ...
```

**Key point:** The existing PDFContextMiddleware's session isolation (thread_id dict), MD5 dedup cache, and immutable system prompt pattern are all preserved. Only the file detection and processing logic expands.

### Pattern 3: Unified Export Function
**What:** Single export_test_cases tool with format parameter.
**When to use:** Agent needs to export test cases.

```python
@tool
def export_test_cases(
    test_cases: list[dict[str, Any]],
    output_path: str,
    format: str = "excel",  # excel | csv | json | markdown
    sheet_name: str = "测试用例",
) -> str:
    """Export test cases in multiple formats."""
    if format == "excel":
        return _export_excel(test_cases, output_path, sheet_name)
    elif format == "csv":
        return _export_csv(test_cases, output_path)
    elif format == "json":
        return _export_json(test_cases, output_path)
    elif format == "markdown":
        return _export_markdown(test_cases, output_path)
```

**Key point:** Existing `_extract_field`, `_flatten_steps`, `_flatten_test_data`, `_flatten_expected_results`, `_flatten_preconditions` helpers are reused across all formats.

### Anti-Patterns to Avoid
- **Do NOT create a separate DynamicModelSelection per file type:** The middleware should detect ANY image content in the message and switch the model. It should not be file-type-specific.
- **Do NOT rebuild quality-review Skill:** It is complete from Phase 2. Only mark SKILL-05 as done in REQUIREMENTS.md.
- **Do NOT change the existing PDFProcessor class:** It works correctly. Add new ImageProcessor and ExcelProcessor as separate classes, and dispatch in FileContextMiddleware.
- **Do NOT store the multimodal toggle in the LangGraph config:** Use the existing StandaloneConfig localStorage pattern in the frontend. Pass the value via the message's additional_kwargs or a custom config field.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Image-to-text parsing | Custom vision API calls with httpx | ChatOpenAI(model="gpt-4o").invoke() with image_url content | Handles base64 encoding, model protocol, token counting, retry logic |
| Model switching in middleware | Manual model replacement in request state | request.override(model=new_model) | DeepAgents/LangChain immutable request pattern; override() handles all edge cases |
| Excel reading | Custom CSV-style parsing | openpyxl.load_workbook() with data_only=True | Handles merged cells, formulas, formatting, multiple sheets correctly |
| CSV BOM encoding | Manual byte manipulation | io.StringIO + codecs.BOM_UTF8 | BOM is required for Chinese Excel compatibility (ZenTao imports) |
| JSON export format | Custom serialization | json.dumps() with Jira Xray structure | Simple dict structure, no edge cases |
| Switch UI component | Custom toggle HTML | Shadcn Switch (already installed) | Accessible, themed, consistent with existing UI |

**Key insight:** The only "new" code in Phase 4 is the DynamicModelSelection middleware class and two processor classes (ImageProcessor, ExcelProcessor). Everything else is configuration (SKILL.md, config fields) or extension (export formats).

## Common Pitfalls

### Pitfall 1: GPT-4o Requires OpenAI API Key
**What goes wrong:** langchain-openai needs OPENAI_API_KEY (or openai_api_key in Settings). The project currently only has DEEPSEEK_API_KEY and DOUBAO_API_KEY in .env.example.
**Why it happens:** CONTEXT.md mentions reusing OPENAI_API_KEY but the .env.example has DOUBAO_API_KEY instead. The project originally planned for Doubao Vision but switched to GPT-4o.
**How to avoid:** Add OPENAI_API_KEY to .env.example and Settings class. The ChatOpenAI constructor will read it from the environment automatically, or it can be passed explicitly via api_key parameter.
**Warning signs:** ChatOpenAI raises AuthenticationError at runtime.

### Pitfall 2: Image Detection Must Check Both Content Blocks and Attachments
**What goes wrong:** Only checking one source of image data (either image_url in content or image/* in attachments) means some uploaded images are not detected.
**Why it happens:** Frontend sends images via two paths -- directly uploaded images go as image_url content blocks (useChat.ts line 68-73), while images embedded in PDFs or other containers go as attachments.
**How to avoid:** DynamicModelSelection._has_image_content() must scan BOTH: (a) message.content for dicts with type="image_url", and (b) additional_kwargs.attachments for items with mimeType starting with "image/".
**Warning signs:** User uploads an image but agent processes it with DeepSeek instead of GPT-4o.

### Pitfall 3: CSV Encoding for Chinese Characters
**What goes wrong:** CSV exported without BOM cannot be opened correctly in Chinese Excel or ZenTao import. Chinese characters show as garbled text.
**Why it happens:** Excel on Windows defaults to the system locale encoding (GBK for Chinese Windows). UTF-8 without BOM is misinterpreted.
**How to avoid:** Always write CSV with UTF-8 BOM prefix (b'\xef\xbb\xbf'). Use `io.StringIO` for writing then prepend BOM.
**Warning signs:** ZenTao or TestRail import fails with encoding errors.

### Pitfall 4: FileContextMiddleware Must Handle Multiple File Types in One Message
**What goes wrong:** User uploads both a PDF and an image in the same message. Only one is processed.
**Why it happens:** Current PDFContextMiddleware only extracts the FIRST PDF attachment. The refactored version must process ALL files and concatenate their context.
**How to avoid:** Change _extract_file_from_last_message to _extract_files_from_last_message (returns list). Process each file with the appropriate processor. Concatenate all results into the system_message injection.
**Warning signs:** User uploads PDF + image but only PDF content appears in agent context.

### Pitfall 5: ConfigDialog Switch State Not Reaching Backend
**What goes wrong:** Frontend toggle state changes but backend middleware never sees the updated value.
**Why it happens:** The useChat hook sends messages via LangGraph SDK's stream.submit(). Config values like ENABLE_PDF_MULTIMODAL are not automatically forwarded.
**How to avoid:** Two options: (a) Pass enable_multimodal in the message's additional_kwargs and check it in DynamicModelSelection, or (b) Pass it in the config dict of stream.submit() and read it from langgraph.config.get_config(). Option (a) is simpler and consistent with how attachments are already passed.
**Warning signs:** Toggling the Switch has no effect on model selection behavior.

### Pitfall 6: Forgetting to Update the MockModelRequest in Tests
**What goes wrong:** conftest.py has a MockModelRequest that only handles messages and system_message in override(). Tests for DynamicModelSelection will fail because override(model=...) is not mocked.
**Why it happens:** The mock was written for Phase 2 when model switching didn't exist.
**How to avoid:** Update MockModelRequest.override() to also handle the model parameter:
```python
def override(self, **kwargs):
    new_req = MockModelRequest(
        messages=kwargs.get("messages", self.messages),
        system_message=kwargs.get("system_message", self.system_message),
    )
    new_req.model = kwargs.get("model", getattr(self, "model", None))
    return new_req
```
**Warning signs:** DynamicModelSelection tests fail with AttributeError on MockModelRequest.

## Code Examples

### DynamicModelSelection Middleware
```python
# Source: Verified from langchain.agents.middleware source inspection
# ModelRequest.override(model=...) confirmed supported

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage
from typing import Any, Awaitable, Callable

class DynamicModelSelection(AgentMiddleware):
    """Switch between DeepSeek (text) and GPT-4o (multimodal) based on content."""

    def __init__(self, api_key: str = "", vision_model: str = "openai:gpt-4o"):
        self._vision_model = init_chat_model(vision_model, api_key=api_key)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> Any:
        if self._has_image_content(request):
            request = request.override(model=self._vision_model)
        return await handler(request)

    def _has_image_content(self, request: ModelRequest) -> bool:
        """Check if any message contains image content."""
        for msg in request.messages:
            if not isinstance(msg, HumanMessage):
                continue
            # Check content blocks for image_url
            content = msg.content
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "image_url":
                        return True
            # Check attachments for image/* MIME type
            attachments = msg.additional_kwargs.get("attachments", [])
            if isinstance(attachments, list):
                for att in attachments:
                    if isinstance(att, dict):
                        mime = att.get("mimeType", "")
                        if mime.startswith("image/"):
                            return True
        return False
```

### ImageProcessor (GPT-4o Vision)
```python
# Source: Verified ChatOpenAI(model="gpt-4o") instantiation works
# langchain-openai 1.2.1 supports image_url content blocks

import base64
import logging
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

class ImageProcessor:
    """Parse image content using GPT-4o multimodal model."""

    def __init__(self, api_key: str = ""):
        self._model = init_chat_model("openai:gpt-4o", api_key=api_key)

    def extract_text(self, image_data: bytes, filename: str = "image.png") -> str:
        """Extract text description from image bytes using GPT-4o."""
        b64 = base64.b64encode(image_data).decode()
        # Infer MIME type from filename extension
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "png"
        mime_map = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "gif": "gif", "webp": "webp"}
        mime = f"image/{mime_map.get(ext, 'png')}"

        message = HumanMessage(content=[
            {"type": "text", "text": "请详细描述这张图片中的所有文字、UI元素、布局结构和功能点。如果图片包含测试相关的需求文档、流程图或界面设计，请完整提取其中的信息。"},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ])
        response = self._model.invoke([message])
        return response.content
```

### ExcelProcessor (openpyxl)
```python
# Source: openpyxl 3.1.5, standard usage pattern

import logging
import tempfile
import os
from openpyxl import load_workbook

logger = logging.getLogger(__name__)

class ExcelProcessor:
    """Parse Excel files into Markdown tables for context injection."""

    def extract_text(self, excel_data: bytes, filename: str = "data.xlsx") -> str:
        """Convert Excel file to Markdown tables (one per sheet)."""
        temp_file = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        try:
            temp_file.write(excel_data)
            temp_file.flush()
            temp_path = temp_file.name
        finally:
            temp_file.close()

        try:
            wb = load_workbook(temp_path, data_only=True)
            parts = []
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                rows = list(ws.iter_rows(values_only=True))
                if not rows:
                    continue
                # Build markdown table
                header = rows[0]
                parts.append(f"### Sheet: {sheet_name}\n")
                parts.append("| " + " | ".join(str(c or "") for c in header) + " |")
                parts.append("| " + " | ".join("---" for _ in header) + " |")
                for row in rows[1:]:
                    parts.append("| " + " | ".join(str(c or "") for c in row) + " |")
                parts.append("")
            return "\n".join(parts)
        except Exception as e:
            logger.error("Excel parsing failed: %s", e)
            return f"Excel processing error: {e}"
        finally:
            try:
                os.unlink(temp_path)
            except Exception:
                pass
```

### CSV Export with BOM
```python
# Source: D-13: UTF-8 with BOM for ZenTao/TestRail compatibility

import csv
import io

def _export_csv(test_cases: list[dict], output_path: str) -> str:
    """Export test cases as CSV with UTF-8 BOM."""
    from pathlib import Path
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    HEADERS_CN = [
        "用例编号", "用例标题", "所属模块", "用例类型", "优先级",
        "前置条件", "测试步骤", "测试数据", "预期结果", "备注",
    ]

    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_ALL)
    writer.writerow(HEADERS_CN)

    for case in test_cases:
        writer.writerow([
            _extract_field(case, "id", "用例编号"),
            _extract_field(case, "title", "用例标题"),
            _extract_field(case, "module", "所属模块"),
            _extract_field(case, "type", "用例类型"),
            _extract_field(case, "priority", "优先级"),
            _flatten_preconditions(_extract_field(case, "preconditions", "前置条件", default=None)),
            _flatten_steps(_extract_field(case, "steps", "测试步骤", default=None)),
            _flatten_test_data(_extract_field(case, "test_data", "测试数据", default=None)),
            _flatten_expected_results(_extract_field(case, "expected_results", "预期结果", default=None)),
            _extract_field(case, "remarks", "备注"),
        ])

    # Write BOM + content
    with open(output_path, "wb") as f:
        f.write(b'\xef\xbb\xbf')  # UTF-8 BOM
        f.write(buf.getvalue().encode("utf-8"))

    return str(output_path.resolve())
```

### JSON Export (Jira Xray Format)
```python
# Source: D-14: Jira Xray compatible format

import json
from pathlib import Path

def _export_json(test_cases: list[dict], output_path: str) -> str:
    """Export test cases as JSON compatible with Jira Xray."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    xray_cases = []
    for case in test_cases:
        steps = _extract_field(case, "steps", "测试步骤", default=None) or []
        xray_steps = []
        if isinstance(steps, list):
            for step in steps:
                xray_steps.append({
                    "action": step.get("action", step.get("操作描述", "")),
                    "result": step.get("expected", step.get("预期结果", "")),
                    "data": step.get("data", ""),
                })

        xray_cases.append({
            "testCaseKey": _extract_field(case, "id", "用例编号"),
            "summary": _extract_field(case, "title", "用例标题"),
            "type": _extract_field(case, "type", "用例类型"),
            "priority": _extract_field(case, "priority", "优先级"),
            "status": "DRAFT",
            "folder": _extract_field(case, "module", "所属模块"),
            "steps": xray_steps,
            "preconditions": _flatten_preconditions(
                _extract_field(case, "preconditions", "前置条件", default=None)
            ),
            "labels": [_extract_field(case, "module", "所属模块")],
        })

    data = {"testCases": xray_cases}
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return str(output_path.resolve())
```

### ConfigDialog Switch Addition
```tsx
// Source: Shadcn Switch at webui/src/components/ui/switch.tsx (verified exists)
// Uses @base-ui/react Switch primitive

import { Switch } from "@/components/ui/switch";

// Inside ConfigDialog component, add after langsmithApiKey field:
<div className="flex items-center justify-between gap-4">
  <Label htmlFor="multimodal">多模态模式</Label>
  <Switch
    id="multimodal"
    checked={enablePdfMultimodal}
    onCheckedChange={setEnablePdfMultimodal}
  />
</div>
```

### StandaloneConfig Extension
```typescript
// webui/src/lib/config.ts -- extend existing interface
export interface StandaloneConfig {
  deploymentUrl: string;
  assistantId: string;
  langsmithApiKey?: string;
  enablePdfMultimodal?: boolean;  // NEW: Phase 4 multimodal toggle
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Doubao Vision for multimodal | GPT-4o via langchain-openai | Phase 4 CONTEXT.md | Use ChatOpenAI, not Doubao-specific SDK. langchain-openai already installed. |
| Separate export function per format | Unified export_test_cases(format=...) | Phase 4 D-12 | Single tool registration, simpler agent prompt |
| PDFContextMiddleware (PDF only) | FileContextMiddleware (PDF + Image + Excel) | Phase 4 D-05 | Extend, don't rebuild. Keep session isolation pattern. |
| DOUBAO_API_KEY in config | OPENAI_API_KEY for GPT-4o | Phase 4 | Replace doubao_api_key with openai_api_key in Settings |

**Deprecated/outdated:**
- DOUBAO_API_KEY: Replace with OPENAI_API_KEY in .env.example and config.py. The doubao_api_key field can be removed or kept for backward compatibility.

## Open Questions

1. **How should enablePdfMultimodal reach the backend middleware?**
   - What we know: Frontend has Switch state. useChat.ts sends messages via stream.submit() with additional_kwargs for PDFs.
   - What's unclear: Whether LangGraph config or additional_kwargs is the better transport mechanism.
   - Recommendation: Use additional_kwargs on the message (consistent with how attachments are passed). DynamicModelSelection checks the message's additional_kwargs for enable_multimodal flag. This avoids needing LangGraph config changes.

2. **Should export_test_cases_to_excel be kept as a backward-compatible alias?**
   - What we know: The tool is registered in agent.py and referenced in SYSTEM_PROMPT ("调用 export_test_cases_to_excel 工具").
   - What's unclear: Whether the agent's learned behavior will break if the tool name changes.
   - Recommendation: Keep export_test_cases_to_excel as a thin wrapper that calls export_test_cases(format="excel"). Update SYSTEM_PROMPT to reference export_test_cases. Register only export_test_cases in the tools list.

3. **Should FileContextMiddleware handle Excel files uploaded as base64 in attachments?**
   - What we know: Frontend supports file upload (ContentBlock type "file" with any mimeType). Excel MIME types are application/vnd.openxmlformats-officedocument.spreadsheetml.sheet (.xlsx) and application/vnd.ms-excel (.xls).
   - What's unclear: Whether the frontend's ContentBlocksPreview supports Excel file display.
   - Recommendation: Yes, handle Excel in attachments. The frontend already sends any file type as a ContentBlock. The middleware should detect Excel MIME types and dispatch to ExcelProcessor.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12+ | Backend runtime | Available | 3.13 | -- |
| langchain-openai | GPT-4o multimodal | Available | 1.2.1 | -- |
| openpyxl | Excel read/write | Available | 3.1.5 | -- |
| pillow | Image preprocessing | Available | 12.2.0 | Not strictly required |
| Shadcn Switch | Multimodal toggle UI | Available | @base-ui/react ^1.4.1 | -- |
| OPENAI_API_KEY | GPT-4o authentication | NOT SET | -- | Must be added to .env |
| Node.js | Frontend dev | Available | (via Next.js) | -- |

**Missing dependencies with no fallback:**
- OPENAI_API_KEY: Must be added to .env file. The user must provide their OpenAI API key. Add it to .env.example as documentation.

**Missing dependencies with fallback:**
- None. All code dependencies are satisfied.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (already in .venv) |
| Config file | none (defaults) |
| Quick run command | `.venv/Scripts/python -m pytest tests/ -x -q` |
| Full suite command | `.venv/Scripts/python -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PARS-02 | Image parsed by GPT-4o, text injected into system_message | unit | `pytest tests/test_image_processor.py -x` | Wave 0 |
| PARS-03 | Excel parsed by openpyxl, Markdown table injected | unit | `pytest tests/test_excel_processor.py -x` | Wave 0 |
| PARS-06 | DynamicModelSelection detects images and swaps model | unit | `pytest tests/test_dynamic_model_middleware.py -x` | Wave 0 |
| MIDW-04 | 3-layer onion middleware chain executes in correct order | unit | `pytest tests/test_dynamic_model_middleware.py::test_middleware_chain -x` | Wave 0 |
| SKILL-04 | test-data-generator SKILL.md loads and parses correctly | unit | `pytest tests/test_skills.py -x` | Exists (extend) |
| SKILL-05 | quality-review already complete (no test needed) | -- | -- | N/A |
| EXPT-03 | CSV/JSON/Markdown export produces correct output | unit | `pytest tests/test_multi_export.py -x` | Wave 0 |
| UI-07 | ConfigDialog renders Switch and saves to config | component | Manual + visual | N/A |

### Sampling Rate
- **Per task commit:** `.venv/Scripts/python -m pytest tests/ -x -q`
- **Per wave merge:** `.venv/Scripts/python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_image_processor.py` -- covers PARS-02 (mock GPT-4o response)
- [ ] `tests/test_excel_processor.py` -- covers PARS-03 (real openpyxl)
- [ ] `tests/test_dynamic_model_middleware.py` -- covers PARS-06, MIDW-04
- [ ] `tests/test_multi_export.py` -- covers EXPT-03 (CSV/JSON/Markdown)
- [ ] `tests/conftest.py` -- update MockModelRequest to support model in override()
- [ ] `tests/test_skills.py` -- extend to test test-data-generator SKILL.md loading

## Project Constraints (from CLAUDE.md)

1. **Technology stack:** Python 3.13 backend + Next.js 15.4.4 frontend, matching classroom code
2. **Agent framework:** DeepAgents >= 0.4.12 as primary framework
3. **LLM providers:** DeepSeek Chat (text) + Doubao Vision (multimodal) -- but Phase 4 CONTEXT overrides to GPT-4o
4. **Port convention:** LangGraph API 2026, Frontend 3000, LightRAG Server 9621
5. **GSD workflow enforcement:** Use `/gsd:execute-phase` for phase work, not direct edits
6. **Middleware pattern:** Follow existing onion model with immutable request.override() pattern

## Sources

### Primary (HIGH confidence)
- Codebase inspection: agent.py, pdf_context.py, pdf.py, tools.py, config.py (all read and verified)
- langchain.agents.middleware.ModelRequest source code (override() supports model= parameter)
- langchain-openai ChatOpenAI instantiation verified with model="gpt-4o"
- Shadcn Switch component verified at webui/src/components/ui/switch.tsx

### Secondary (MEDIUM confidence)
- DeepAgents 0.5.9 API patterns (from existing codebase usage, not separate docs)
- Jira Xray JSON import format (from CONTEXT.md D-14 specification, standard Xray API format)
- ZenTao/TestRail CSV import format (from CONTEXT.md D-13 specification, standard BOM+UTF-8 pattern)

### Tertiary (LOW confidence)
- None. All findings verified against codebase or CONTEXT.md decisions.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all packages verified installed and versions confirmed
- Architecture: HIGH - middleware chain, ModelRequest API, and processor patterns all verified against source code
- Pitfalls: HIGH - identified from codebase inspection and known patterns (BOM encoding, dual image detection)
- Export formats: HIGH - CSV/JSON/Markdown are straightforward; field helpers already exist
- Frontend Switch: HIGH - component exists, StandaloneConfig pattern established

**Research date:** 2026-05-13
**Valid until:** 2026-06-13 (stable -- no fast-moving dependencies)
