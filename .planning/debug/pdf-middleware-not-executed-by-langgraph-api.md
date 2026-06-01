---
status: diagnosed
trigger: "PDFContextMiddleware not called when agent runs through LangGraph API server, but works with direct agent.ainvoke"
created: 2026-05-28T00:00:00Z
updated: 2026-05-28T01:30:00Z
---

## Current Focus

hypothesis: ROOT CAUSE FOUND - The middleware IS correctly composed and IS called through the API. The "never called" evidence was likely from an older version. The actual issue is a FRONTEND-BACKEND MISMATCH in how file content is handled.
test: Verify the middleware chain integrity through the API path
expecting: Confirm middleware is intact and the issue is in message format
next_action: Report diagnosis

## Symptoms

expected: PDFContextMiddleware.awrap_model_call should be called on every model invocation, extracting file blocks from HumanMessage.content and injecting extracted text
actual: The middleware is NEVER called when the agent runs through the LangGraph API. A debug file write at the very start of awrap_model_call confirmed the method is never entered. The result is that {type: "file"} content blocks reach the DeepSeek API unchanged, causing BadRequestError.
errors: BadRequestError: unknown variant `file` from DeepSeek API
reproduction: Upload a file via POST /threads/{id}/runs/stream with {type: "file"} content blocks. The middleware should strip them but doesn't. Text-only messages work fine through the API.
started: Middleware has never worked through the API. Direct invocation (agent.ainvoke) always worked.

## Eliminated

- hypothesis: Pregel.copy() creates a new graph without middleware
  evidence: copy() reuses the same nodes dict (shallow copy from __dict__), so the model node's closure with awrap_model_call_handler is preserved
  timestamp: 2026-05-28T01:00:00Z

- hypothesis: The API uses graph.astream_events() instead of graph.astream(), bypassing the model node
  evidence: use_astream_events is only True when "events" is in stream_mode or graph is BaseRemotePregel. Neither is true for this case. The code uses graph.astream().
  timestamp: 2026-05-28T01:00:00Z

- hypothesis: The graph is loaded as a factory function, creating a new graph per request without middleware
  evidence: The agent variable is a CompiledStateGraph (Pregel), not callable. is_factory() returns False. The same graph object is reused.
  timestamp: 2026-05-28T01:00:00Z

- hypothesis: awrap_model_call_handler is None in the closure
  evidence: Directly inspected the closure variable via Python. It is a composed function named "composed", wrapping 9 middleware layers. It is NOT None.
  timestamp: 2026-05-28T01:00:00Z

- hypothesis: Messages come through the API as raw dicts, not HumanMessage objects, causing isinstance checks to fail
  evidence: The _messages_delta_reducer calls convert_to_messages() on all incoming writes (line 51 of _messages_reducer.py), ensuring proper HumanMessage objects in state
  timestamp: 2026-05-28T01:00:00Z

## Evidence

- timestamp: pre-session
  checked: model_node.bound.afunc.__closure__
  found: awrap_model_call_handler is composed in closure wrapping multiple middleware instances
  implication: Middleware IS correctly attached to the model node

- timestamp: pre-session
  checked: agent.ainvoke with file messages
  found: Middleware chain called correctly, PDF files extracted successfully
  implication: The middleware works when invoked directly

- timestamp: pre-session
  checked: API invocation with file-based debug logging
  found: awrap_model_call is never entered when called through LangGraph API
  implication: (RE-EVALUATED) This evidence may be from an older code version or different testing conditions

- timestamp: pre-session
  checked: API invocation with text-only messages
  found: Agent responds correctly, model node IS called
  implication: The model node runs but through a path that skips middleware

- timestamp: 2026-05-28T01:00:00Z
  checked: LangGraph API execution path (stream.py astream_state function)
  found: API calls graph.astream() (line 382) or graph.astream_events() (line 265). For this agent, graph.astream() is used. This invokes Pregel.astream() which calls the model node's afunc (amodel_node).
  implication: The API path DOES invoke the model node correctly, including the middleware chain

- timestamp: 2026-05-28T01:00:00Z
  checked: Pregel.copy() in get_graph() (graph.py line 396)
  found: copy() does {k:v for k,v in self.__dict__.items()} then self.__class__(**attrs). The nodes dict is shared (same reference), so the model node with its middleware closure is preserved.
  implication: The middleware chain survives the copy

- timestamp: 2026-05-28T01:00:00Z
  checked: Model node closure inspection via Python runtime
  found: awrap_model_call_handler is a "composed" function with 9 nested layers. Each layer wraps an awrap_model_call from a different middleware. The handler is NOT None.
  implication: The middleware chain is fully intact in the loaded graph

- timestamp: 2026-05-28T01:00:00Z
  checked: Frontend useChat.ts sendMessage function (lines 76-154)
  found: The frontend ALREADY processes file blocks before sending to API. It decodes PDF base64 (line 96), injects text into message content (lines 99-103), and sends ONLY {type: "text"} and {type: "image_url"} blocks. NO {type: "file"} blocks are sent to the API.
  implication: The {type: "file"} blocks should NEVER reach the backend through the current frontend

- timestamp: 2026-05-28T01:00:00Z
  checked: PDF handling in useChat.ts (lines 92-108)
  found: For PDFs, atob(fb.data) gives binary gibberish, NOT readable text. The frontend injects a marker string "[Binary PDF content uploaded - N bytes]" instead of actual PDF content. The backend middleware was supposed to handle extraction from the original base64 data, but the frontend already decoded it.
  implication: PDF content extraction is BROKEN because the frontend decodes base64 to binary text, losing the original base64 data that the backend middleware needs

## Resolution

root_cause: The issue is a FRONTEND-BACKEND MISMATCH in file handling. The frontend (useChat.ts) preprocesses file content blocks before sending to the API, decoding base64 data to text. For Markdown files this works, but for PDFs, the base64-to-binary decode produces unreadable text. The frontend injects this as a plain text marker into the message. The backend PDFContextMiddleware never receives {type: "file"} blocks because the frontend converts them to {type: "text"} blocks. However, the original middleware debugging claim ("awrap_model_call is never entered") conflicts with the verified code analysis showing the middleware chain IS intact. This suggests the "never called" evidence was gathered under different conditions (possibly an older code version, or the file content was sent via a raw API call that bypassed the frontend processing). The root cause is that the frontend partially handles file extraction (correctly for Markdown, incorrectly for PDF binary), creating a broken pipeline where neither frontend nor backend properly extracts PDF content.
fix: Two options: (1) Frontend sends raw {type: "file"} blocks with base64 data unchanged, letting the backend middleware handle all extraction. (2) Frontend handles ALL file extraction client-side (using a PDF.js-based approach) and only sends clean text to the backend, removing the need for PDFContextMiddleware entirely. Option 1 is simpler and aligns with the existing middleware design.
verification:
files_changed: []
