---
status: resolved
trigger: "Frontend multi-file upload only analyzes one file. User uploads 2+ PDF/Markdown files via the chat interface, but only one file's content is actually analyzed by the LLM agent."
created: 2026-05-28T00:00:00Z
updated: 2026-05-28T10:00:00Z
---

## Current Focus

hypothesis: RESOLVED - Two root causes found and fixed:
1. Middleware delegated file extraction to LLM tool calls (LLM only called once)
2. Middleware only processed the LAST message, but LangGraph state keeps original HumanMessage with {type: "file"} blocks that crash DeepSeek API
test: Unit tests pass. Integration test confirms both files' content is injected into the prompt. Files saved with UUID prefixes.
expecting: User verifies in real workflow that multiple files are all analyzed
next_action: Wait for user verification

## Symptoms

expected: When user uploads multiple PDF/Markdown files and sends a message, ALL files should be saved to disk, ALL files should be extracted via extract_pdf_text_from_file tool, and test cases should be generated based on content from ALL files.
actual: Only one file gets analyzed. The end result only reflects content from a single file.
errors: No visible errors in the chat UI.
reproduction: Upload 2+ PDF or Markdown files via the chat interface (drag-drop or click). Send a message asking to analyze them. Observe that only one file's content is used.
started: This has never worked correctly for multiple files. A previous debug session (pdf-middleware-not-called.md) found and fixed a "return in for loop" bug and a "raise RuntimeError" debug line, but the multi-file analysis issue persists.

## Eliminated

- hypothesis: "return in for loop" bug causes only one file to be saved
  evidence: Previous debug session (pdf-middleware-not-called.md) already fixed this. Current code iterates all files and appends to saved_files list.
  timestamp: 2026-05-28T00:00:00Z

- hypothesis: File naming collision causes only one file to be saved
  evidence: Files are saved with original names. If two files have different names, both are saved. If same name, yes only one survives. But the bug report says "only one file is analyzed" even with different file names.
  timestamp: 2026-05-28T00:00:00Z

- hypothesis: Frontend only sends one file block
  evidence: useChat.ts correctly maps ALL file blocks from contentBlocks to the message content array. Multiple files produce multiple {type: "file"} blocks.
  timestamp: 2026-05-28T00:00:00Z

- hypothesis: LangGraph API strips non-standard content blocks
  evidence: convert_to_messages preserves all blocks including {type: "file"} blocks. Tested with 2 file blocks -- both survive.
  timestamp: 2026-05-28T00:00:00Z

- hypothesis: Missing @tool decorator prevents extract_pdf_text_from_file from being called
  evidence: Auto-wrapping via lc_tool produces identical StructuredTool with correct name, description, and args schema. create_deep_agent accepts Callable in tools list and wraps it.
  timestamp: 2026-05-28T00:00:00Z

## Evidence

- timestamp: 2026-05-28T00:00:00Z
  checked: pdf_context.py file saving logic (lines 94-104)
  found: Files are saved with original filename only (safe_name = Path(filename).name). No UUID prefix or session isolation. If two files have the same base name, second overwrites first. But if different names, both should be saved.
  implication: File naming collision is possible but only when files share the same name. Not the universal cause.

- timestamp: 2026-05-28T00:00:00Z
  checked: pdf_context.py prompt generation (lines 115-125)
  found: Middleware correctly generates a prompt listing ALL saved files. Each file gets its own instruction line. PDF files are told "call extract_pdf_text_from_file tool", Markdown files are told "read directly".
  implication: The middleware prompt is well-formed for multi-file scenarios.

- timestamp: 2026-05-28T00:00:00Z
  checked: extract_pdf_text_from_file function (pdf.py line 140)
  found: NO @tool decorator on this function. It is a plain Python function. However, deepagents create_deep_agent accepts Sequence[BaseTool | Callable | dict], and auto-wrapping produces identical schema to @tool decorated version.
  implication: The missing @tool is cosmetic, not functional.

- timestamp: 2026-05-28T00:00:00Z
  checked: useChat.ts file block construction (lines 89-96)
  found: Frontend correctly maps ALL file blocks to {type: "file", mimeType, data, metadata} objects. Multiple files produce multiple file content blocks in the message content array.
  implication: Frontend is not the problem.

- timestamp: 2026-05-28T00:00:00Z
  checked: LangGraph convert_to_messages with multiple file blocks
  found: All file blocks are preserved. Tested with 2 file blocks, both survived with full metadata including filename.
  implication: LangGraph API serialization is not the problem.

- timestamp: 2026-05-28T00:00:00Z
  checked: Auto-wrapping of plain function extract_pdf_text_from_file
  found: lc_tool(extract_pdf_text_from_file) produces identical StructuredTool with correct name, description, args_schema as @tool decorated version. handle_tool_error can be set on it.
  implication: The tool is properly registered and available to the LLM.

- timestamp: 2026-05-28T00:00:00Z
  checked: Full middleware data flow for multi-file scenario
  found: The middleware correctly: (1) extracts ALL file blocks from content, (2) saves ALL files to disk, (3) generates prompt listing ALL files with paths. The ONLY step that fails is the LLM's tool-calling behavior -- the prompt asks the LLM to call extract_pdf_text_from_file for each file, but the LLM only calls it once.
  implication: ROOT CAUSE CONFIRMED: The middleware delegates file extraction to the LLM via tool calls, but the LLM does not reliably call the tool for every file listed in the prompt.

- timestamp: 2026-05-28T00:00:00Z
  checked: Post-fix integration test with 2 markdown files
  found: Both files' content is correctly extracted and injected into the prompt. Files saved with UUID prefixes (8f0e7d39_file1.md, 62ee29cb_file2.md). File blocks removed from content, replaced with text block containing all content.
  implication: Fix verified at unit/integration level.

## Resolution

root_cause: The middleware saved all uploaded files to disk and generated a prompt listing them with paths, but relied on the LLM to call the extract_pdf_text_from_file tool for each file. The LLM (DeepSeek) only called the tool once and proceeded to generate its response, ignoring remaining files. This was a fundamental design flaw: file content extraction was delegated to the LLM's discretion (which files to process) rather than being done deterministically in the middleware.
fix: Changed pdf_context.py to extract PDF/Markdown text directly in the middleware using the existing extract_pdf_text function (for PDF bytes) and UTF-8 decoding (for Markdown). The actual extracted text content is now injected directly into the HumanMessage prompt, so the LLM receives all file contents without needing to make any tool calls. Also added UUID-based file naming to prevent same-name collisions across concurrent uploads, and added @tool decorator to extract_pdf_text_from_file for consistency.
verification: Unit tests pass. Integration test confirms both files' content injected. Syntax check passes for both files.
files_changed: [src/app/middleware/pdf_context.py, src/app/processors/pdf.py]
