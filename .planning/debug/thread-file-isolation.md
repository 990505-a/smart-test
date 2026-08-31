---
status: awaiting_human_verify
trigger: "After implementing thread-scoped file uploads, files still end up in flat directory when threadId is null (new conversation). Also, PDF extraction fails with import error."
created: 2026-06-11T00:00:00Z
updated: 2026-06-11T00:12:00Z
---

## Current Focus

hypothesis: Two bugs confirmed and fixes applied. Awaiting human verification.
test: Self-verified via TypeScript compilation and Python syntax check
expecting: Both issues resolved in real environment
next_action: Wait for user confirmation

## Symptoms

expected: When user uploads a file in a new conversation, the file should be saved to a thread-scoped subdirectory (e.g., /uploads/{thread_id}/xxx.pdf), and the agent should be able to find and read it. PDF extraction should work without import errors.
actual: Two problems: (1) Files uploaded before the first message in a new conversation go to /uploads/ flat directory because currentThreadId is null. The thread is only created when the first message is sent. (2) PDF extraction fails with "No module named 'app'" error.
errors:
  - "No module named 'app'" from extract_pdf.py lines 71 and 137
  - ls("/uploads/{thread_id}/") returns [] because files weren't saved there
reproduction: Start new conversation, upload PDF before first message, send message. Files in flat dir, not thread dir.
started: Just implemented thread-scoped uploads

## Eliminated

## Evidence

- timestamp: 2026-06-11T00:01:00Z
  checked: ChatInterface.tsx line 88 vs line 94
  found: useFileUpload(undefined, currentThreadId ?? undefined) is at line 88, but currentThreadId is declared at line 94 via useQueryState("threadId"). Due to JS hoisting, the const is in TDZ -- but since both are inside the same function component, this actually causes a ReferenceError at runtime. WAIT -- looking more carefully, line 94 is `const [currentThreadId] = useQueryState("threadId");` which IS used at line 88 before its declaration. This is a temporal dead zone bug. HOWEVER, the React component would crash entirely if this were the case. Let me re-read... Actually line 88 comes before line 94 in the source. In React function components, hooks must be called in order but variable declarations with const ARE hoisted to block scope but NOT initialized. So `currentThreadId` at line 88 would be in TDZ. This is a real bug.
  implication: The component should crash. BUT it might work because JS engine may not enforce TDZ strictly in all cases, or the line numbers may be misleading. Need to look more carefully.

- timestamp: 2026-06-11T00:02:00Z
  checked: ChatInterface.tsx line ordering more carefully
  found: Looking at the actual code: Lines 80-88 are inside the component body, and line 94 declares currentThreadId. The useFileUpload call at line 88 passes `currentThreadId ?? undefined` but currentThreadId is declared 6 lines later. This is indeed a TDZ issue. BUT -- wait, `currentThreadId` is a const from useQueryState. In practice, the JS engine evaluates the component body top-to-bottom, so when line 88 executes, `currentThreadId` has NOT been declared yet. This would throw ReferenceError. UNLESS the bundler (Next.js/webpack) hoists or reorders... Actually, looking again: the useQueryState at line 94 is between the useFileUpload (line 88) and handleSubmit. Let me count the exact ordering. The component starts at line 47. Lines 48-69 are state/ref declarations. Lines 72-78 are wiki storage. Lines 80-88 is useFileUpload. Lines 90-94 has the storage key and useQueryState. So YES, currentThreadId is used before it's declared.
  implication: This is a real ordering bug. The fix is to move the useQueryState("threadId") before the useFileUpload call. But even with correct ordering, for new conversations currentThreadId will be null, and the fallback `currentThreadId ?? undefined` means threadId param is undefined, so uploads go to flat dir.

- timestamp: 2026-06-11T00:03:00Z
  checked: extract_pdf.py import paths (lines 71, 137) vs other files in the project
  found: extract_pdf.py uses `from app.processors.pdf import extract_pdf_text` at lines 71 and 137. But the project's import convention is `from src.app.*` -- visible in the same file at line 20: `from src.app.core.config import settings`. Also in agent.py: `from app.middleware.pdf_context import PDFContextMiddleware` -- wait, agent.py uses `from app.*` without `src.` prefix too! Let me check if the PYTHONPATH includes src/ or if there's a sys.path manipulation.
  implication: The import path might depend on the runtime context. When running as a module from src/, `app.*` works. When running directly or from a different working directory, only `src.app.*` works. The extract_pdf.py endpoint might be running in a different context than the agent.

- timestamp: 2026-06-11T00:04:00Z
  checked: agent.py imports at lines 34-39
  found: agent.py uses `from app.middleware.pdf_context import PDFContextMiddleware` (no src. prefix), `from app.agents.testcase.context import ThreadContextMiddleware` (no src. prefix), `from app.core.config import settings` (no src. prefix). So the agent module consistently uses `app.*` imports without `src.`. But extract_pdf.py line 20 uses `from src.app.core.config import settings`. This inconsistency suggests the Python path setup varies by entry point.
  implication: The `from app.processors.pdf import extract_pdf_text` in extract_pdf.py might work IF the server is started from the src/ directory. But if started from the project root, only `from src.app.processors.pdf` would work. The error "No module named 'app'" confirms the server is NOT running from src/ directory. The fix: use `from src.app.processors.pdf import extract_pdf_text` to match line 20's convention in the same file.

## Resolution

root_cause: |
  Bug 1: In ChatInterface.tsx, `currentThreadId` (from useQueryState) is referenced at line 88 BEFORE it is declared at line 94, creating a temporal dead zone error. Additionally, for new conversations currentThreadId is legitimately null, and the code passes undefined as threadId to useFileUpload, causing files to be uploaded without thread isolation.
  
  Bug 2: In extract_pdf.py, lines 71 and 137 use `from app.processors.pdf import extract_pdf_text` but the server runs from the project root where the module path requires `src.app.processors.pdf`. The same file uses `from src.app.core.config import settings` at line 20, confirming the correct import prefix.

fix: |
  Bug 1: 
  - Move `const [currentThreadId] = useQueryState("threadId")` before the useFileUpload call
  - Generate a client-side UUID (uploadSessionId) via useRef + crypto.randomUUID() when threadId is null
  - Pass `currentThreadId ?? uploadSessionId` to useFileUpload
  - Expose uploadSessionId from useFileUpload so it can be passed in the LangGraph configurable
  - In ThreadContextMiddleware, check upload_dir_id as fallback
  
  Bug 2:
  - Change `from app.processors.pdf import extract_pdf_text` to `from src.app.processors.pdf import extract_pdf_text` at lines 71 and 137

verification: |
  - TypeScript compilation: npx tsc --noEmit passes with zero errors
  - Python syntax: py_compile passes for both modified Python files
  - Manual review of data flow: threadId ordering fixed, uploadSessionId generated and passed correctly through configurable chain
  - Import path fix: both extract_pdf.py imports now use src.app.processors.pdf consistent with line 20's convention

files_changed:
  - src/app/api/v2/extract_pdf.py — fixed import paths from app.processors.pdf to src.app.processors.pdf
  - src/app/agents/testcase/context.py — ThreadContextMiddleware now checks upload_dir_id configurable as fallback
  - webui/src/app/hooks/useFileUpload.ts — added uploadSessionId generation, effectiveDirId logic, exposed uploadSessionId
  - webui/src/app/components/ChatInterface.tsx — moved useQueryState before useFileUpload, destructured uploadSessionId, passes it in sendMessage
  - webui/src/app/hooks/useChat.ts — added uploadDirId to context type, passes upload_dir_id in configurable
