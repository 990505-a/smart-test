---
status: awaiting_human_verify
trigger: "上传多个 PDF 文件后，PDF 全文嵌入 HumanMessage content，导致 LangGraph 线程状态膨胀，/state 和 /history 端点返回 500 Internal Server Error"
created: 2026-05-28T00:00:00Z
updated: 2026-05-28T00:30:00Z
---

## Current Focus

hypothesis: CONFIRMED - PDF full text embedded in HumanMessage causes thread state bloat
test: Fix implemented, awaiting human verification
expecting: Messages now contain only ~200 bytes of path references instead of up to 200KB of full PDF text
next_action: User verifies fix by uploading multiple PDFs and confirming agent can read files and generate cases without crash

## Symptoms

expected: User uploads multiple PDF files, agent analyzes requirements and generates test cases, cases saved to database
actual: Agent thread state balloons to 405KB (89 messages, 56 tool_calls) during case generation, LangGraph API /state returns 500, frontend crashes with "Failed to fetch", cases never saved
errors: Frontend Console TypeError: Failed to fetch (useStream calls /state gets 500)
reproduction: Upload 4 PDF files + select repo path -> agent starts generating cases -> thread state grows too large -> crash
started: Always triggers when uploading multiple PDFs; inherent design flaw

## Eliminated

## Evidence

- timestamp: 2026-05-28T00:01:00Z
  checked: webui/src/app/utils/multimodal.ts fileToContentBlock()
  found: PDF upload calls /api/extract-pdf, stores full extracted text in block.metadata.extractedText (no size limit at storage time, extract_pdf.py truncates to 50,000 chars)
  implication: Full PDF text is stored in the ContentBlock metadata object in memory on the frontend

- timestamp: 2026-05-28T00:02:00Z
  checked: webui/src/app/hooks/useChat.ts sendMessage()
  found: Lines 101-108: For PDF files, reads fb.metadata.extractedText and embeds it directly into fileTextParts as "### File: xxx.pdf (PDF)\n\n{extracted}". This text becomes part of the HumanMessage content string sent to LangGraph via stream.submit()
  implication: CONFIRMED - full PDF text (up to 50,000 chars per file) is embedded verbatim into the HumanMessage content. 4 PDFs = up to 200,000 chars in a single message

- timestamp: 2026-05-28T00:03:00Z
  checked: src/app/agents/testcase/agent.py backend configuration
  found: FilesystemBackend configured with root_dir = workspace/default/testcase/. CompositeBackend routes /skills/ to skills_backend, other paths to file_backend. Agent has file tools to read workspace files
  implication: Infrastructure already exists for agent to read files from workspace. Fix can save PDFs to workspace and let agent read them via file tools

- timestamp: 2026-05-28T00:04:00Z
  checked: src/app/middleware/pdf_context.py
  found: Lines 106-108 comment: "LangGraph API bypasses the model node's middleware chain entirely. File extraction is handled by the frontend + /api/v2/extract-pdf-text endpoint." The middleware would normally save files to uploads/ and inject text, but it is NOT active when using LangGraph API
  implication: PDFContextMiddleware is dead code for the LangGraph API path. File saving must happen either in frontend (via new backend endpoint) or in a LangGraph-compatible way

- timestamp: 2026-05-28T00:05:00Z
  checked: src/app/api/__init__.py router registration
  found: extract_pdf.router is registered at /api/v2 with tag "PDF Extraction". No upload-file endpoint exists yet. workspace_dir is configured in settings
  implication: Need to add a new endpoint POST /api/v2/upload-to-workspace that saves extracted PDF text to workspace files

## Resolution

root_cause: PDF full text (up to 50,000 chars per file) is embedded verbatim into HumanMessage content by useChat.ts sendMessage(). With multiple PDFs, the message content can exceed 200KB. Each HumanMessage is stored in the LangGraph thread state. With 89 messages and 56 tool calls, thread state balloons to 405KB+ causing inmem serialization to fail with 500 error on /state and /history endpoints.
fix: Implemented file-reference pattern across 5 files. New backend endpoint POST /api/v2/upload-to-workspace saves PDF text to workspace/uploads/ and returns virtual absolute paths. Frontend multimodal.ts calls new endpoint instead of /api/extract-pdf. useChat.ts sendMessage embeds only ~200 bytes of path references instead of up to 200KB of full text. Agent system prompt updated with instructions to read files via read_file tool.
verification: Python modules compile successfully. TypeScript changes are syntactically correct (pre-existing module resolution config issues unrelated to this fix). Awaiting end-to-end human verification.
files_changed: [src/app/api/v2/extract_pdf.py, webui/src/app/api/upload-to-workspace/route.ts, webui/src/app/types/types.ts, webui/src/app/utils/multimodal.ts, webui/src/app/hooks/useChat.ts, src/app/agents/testcase/agent.py]
