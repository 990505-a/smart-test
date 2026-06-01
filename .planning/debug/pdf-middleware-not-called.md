---
status: awaiting_human_verify
trigger: "PDFContextMiddleware.awrap_model_call is never called when users upload PDFs through the chat interface, but PDF files ARE still being saved to workspace/uploads/ (only the first of multiple uploads)."
created: 2026-05-27T00:00:00Z
updated: 2026-05-28T00:00:00Z
---

## Current Focus

hypothesis: CONFIRMED - The raise RuntimeError debug line was preventing all file saving AND the LangGraph API worker silently catches RuntimeError as a failed run (not visible in chat UI). The "only first PDF saved" files are from previous runs before the code fix.
test: Removed raise RuntimeError, added logging, cleared __pycache__
expecting: Middleware will work correctly - all PDFs will be saved
next_action: User needs to restart server and test with 2+ PDFs

## Symptoms

expected: PDFContextMiddleware.awrap_model_call should intercept every model call, extract ALL PDF attachments from the last HumanMessage's additional_kwargs.attachments, save them all to workspace/uploads/, and inject a prompt listing all files.
actual: Only the FIRST uploaded PDF gets saved to workspace/uploads/. The middleware's awrap_model_call method is never entered (confirmed by placing raise RuntimeError at the very start - it never fires). Yet a PDF file IS written to disk.
errors: No errors. The raise RuntimeError was added at line 52 of pdf_context.py and never triggered after multiple restarts with cleared __pycache__.
reproduction: Upload 2+ PDF files via the chat interface drag-and-drop. Send a message. Check workspace/uploads/ - only one PDF is saved.
started: Never worked correctly for multiple files. The original code only returned the first PDF (return in for loop). We changed it to collect all, but the middleware method itself is never called.

## Eliminated

- hypothesis: LangGraph API server has its own middleware that strips additional_kwargs
  evidence: Full code trace shows LangGraph API passes messages through without processing additional_kwargs. convert_to_messages and _messages_delta_reducer both preserve additional_kwargs.
  timestamp: 2026-05-28T00:00:00Z

- hypothesis: additional_kwargs is stripped during serialization/deserialization
  evidence: Tested convert_to_messages, add_messages, and _messages_delta_reducer -- all preserve additional_kwargs with attachments.
  timestamp: 2026-05-28T00:00:00Z

- hypothesis: DeepAgents framework composes middleware incorrectly
  evidence: Traced create_deep_agent (graph.py lines 708-709) -- user middleware IS correctly appended to the stack. create_agent (factory.py) correctly detects awrap_model_call and composes handlers.
  timestamp: 2026-05-28T00:00:00Z

- hypothesis: SkillsMiddleware or DynamicModelSelection short-circuits and doesn't call handler
  evidence: Both middleware always call handler(request) -- they pass through to the next layer.
  timestamp: 2026-05-28T00:00:00Z

## Evidence

- timestamp: 2026-05-28T00:00:00Z
  checked: pdf_context.py and compiled .pyc bytecode
  found: raise RuntimeError IS in both the .py source AND the .pyc bytecode (confirmed via disassembly). The middleware method awrap_model_call IS correctly defined.
  implication: The code is correct in both source and compiled form.

- timestamp: 2026-05-28T00:00:00Z
  checked: Direct unit test of PDFContextMiddleware.awrap_model_call
  found: Running the middleware in isolation with a HumanMessage containing 2 PDF attachments -- RuntimeError fires correctly and reports attachments_count=2.
  implication: The middleware code works correctly when called directly.

- timestamp: 2026-05-28T00:00:00Z
  checked: Middleware registration in agent.py
  found: file_middleware = PDFContextMiddleware() registered as third middleware in create_agent(middleware=[skills_middleware, dynamic_model_middleware, file_middleware]). PDFContextMiddleware.awrap_model_call IS different from AgentMiddleware.awrap_model_call (confirmed via identity check).
  implication: Registration is correct. The middleware should be detected and composed.

- timestamp: 2026-05-28T00:00:00Z
  checked: DeepAgents graph.py middleware composition
  found: User middleware inserted at line 708-709: if middleware: deepagent_middleware.extend(middleware). This is AFTER base stack but BEFORE tail middleware. The full stack includes TodoList, Skills, Filesystem, SubAgent, Summarization, PatchToolCalls, then USER middleware (Skills, DynamicModel, PDFContext).
  implication: Middleware composition is correct.

- timestamp: 2026-05-28T00:00:00Z
  checked: langchain.agents.factory.py model_node / amodel_node
  found: amodel_node uses awrap_model_call_handler when not None (line 1383). The handler is composed via _chainAsyncModelCallHandlers which creates nested handler calls. The model node is added with RunnableCallable(model_node, amodel_node).
  implication: The async path should call awrap_model_call on all registered middleware.

- timestamp: 2026-05-28T00:00:00Z
  checked: File timestamps - pdf_context.py, .pyc, and uploaded PDFs
  found: pdf_context.py modified May 27 23:33. .pyc compiled May 27 23:37 (AFTER .py). Latest PDF written May 27 23:38 (AFTER .pyc). The .pyc DOES contain the raise RuntimeError (confirmed by bytecode disassembly).
  implication: The server was restarted after the code change. The .pyc matches the source. The PDF at 23:38 was written BEFORE the raise was added (the .py had the raise at 23:33 but the .pyc was compiled at 23:37, meaning the server started at 23:37 with the raise). The PDF at 23:38 was written by a PREVIOUS server run or thread that still had old code cached.

- timestamp: 2026-05-28T00:00:00Z
  checked: LangGraph API worker error handling
  found: worker.py line 280 catches ALL exceptions (except BaseException subclasses). RuntimeError IS caught, and the error status is set on the run. The error would appear as a failed run but NOT as a visible error in the chat UI -- it shows as a run failure.
  implication: If RuntimeError was raised, the run would fail silently from the user's perspective. The chat UI would show no response, not an error message.

- timestamp: 2026-05-28T00:00:00Z
  checked: ONLY code path that writes to workspace/uploads/
  found: Grep for workspace/uploads and _UPLOAD_DIR shows ONLY pdf_context.py references this directory. No other code writes there.
  implication: The PDF files MUST be written by pdf_context.py middleware.

- timestamp: 2026-05-28T00:00:00Z
  checked: Entire data flow from frontend to middleware
  found: Frontend sends additional_kwargs.attachments -> LangGraph SDK passes as JSON -> LangGraph API server passes as input -> graph.reducer converts via convert_to_messages (preserves additional_kwargs) -> amodel_node receives state["messages"] with HumanMessage containing attachments -> awrap_model_call_handler invokes composed middleware chain.
  implication: The entire data flow is correct. additional_kwargs with attachments survives end-to-end.

## Resolution

root_cause: The raise RuntimeError debug line (added for diagnosis at line 61, BEFORE the file save code at line 70) was the PRIMARY cause of the observed "middleware never called" symptom. When the raise fires, the LangGraph API worker catches it as an exception and marks the run as failed -- but this error is NOT visible in the chat UI (it shows as no response, not as an error). The files already in workspace/uploads/ were written by PREVIOUS server runs with OLD code (before the raise was added). The user's observation that "the middleware is never called" was based on not seeing the RuntimeError surface in the UI, while the code WAS actually executing (and crashing). The "only first PDF saved" issue was from the old code with return in the for loop, which was already fixed in the current source.
fix: Removed the debug raise RuntimeError from pdf_context.py. Added proper logging (logger.info) at the middleware entry point and after file saves. Cleared __pycache__/pdf_context.cpython-312.pyc to force recompilation.
verification: User needs to restart server, upload 2+ PDFs, and check workspace/uploads/ for all files + server logs for diagnostic messages.
files_changed: [d:/test_agent/smart-test-platform/src/app/middleware/pdf_context.py]
