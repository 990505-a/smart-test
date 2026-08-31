---
status: awaiting_human_verify
trigger: "chat-file-upload-not-working - 在聊天界面上传文件（PDF/图片等）给智能体分析时，前端看起来没有上传成功。需要调查前端上传组件和后端上传 API 的完整链路。"
created: 2026-06-02T00:00:00Z
updated: 2026-06-02T00:02:00Z
---

## Current Focus

hypothesis: CONFIRMED AND FIXED - Next.js API route handlers proxy to wrong port (8000 instead of 8001)
test: Fixed all localhost:8000 defaults to localhost:8001. Verified both API routes return correct data via curl.
expecting: File upload should now work end-to-end
next_action: Awaiting human verification in browser

## Symptoms

expected: 用户在聊天界面上传文件后，文件应该成功传递给智能体，智能体能读取并分析文件内容
actual: 前端看起来没有上传成功（具体表现需要调查）
errors: 未知，需要检查前端 console 和后端日志
reproduction: 在聊天界面选择文件上传
started: 不确定何时开始，可能是最近的问题

## Eliminated

## Evidence

- timestamp: 2026-06-02T00:00:30Z
  checked: Upload chain files (useFileUpload.ts, multimodal.ts, useChat.ts, ChatInterface.tsx, route.ts files)
  found: Full upload chain is properly wired - file input -> processFiles -> fileToContentBlock -> sendMessage -> LangGraph stream
  implication: Frontend code logic is correct; issue must be in the API call layer

- timestamp: 2026-06-02T00:00:50Z
  checked: Next.js route handlers (/api/extract-pdf/route.ts, /api/upload-to-workspace/route.ts)
  found: Both use `process.env.PYTHON_API_URL || "http://localhost:8000"` as the backend URL
  implication: If PYTHON_API_URL env var is not set, requests go to port 8000

- timestamp: 2026-06-02T00:01:00Z
  checked: Port 8000 vs 8001 - what's actually running
  found: Port 8000 is GSD tool server (gs.exe), NOT FastAPI. FastAPI runs on port 8001 (verified by curl). Next.js extract-pdf route returns "Backend extraction unavailable" while direct curl to 8001 returns proper PDF text.
  implication: ROOT CAUSE CONFIRMED - Next.js route handlers proxy to wrong port (GSD server on 8000 instead of FastAPI on 8001)

- timestamp: 2026-06-02T00:01:10Z
  checked: start.bat and architecture
  found: start.bat launches FastAPI on port 8001, LangGraph on 2026, Next.js on 3000. The default port in route handlers was never updated from 8000 to 8001.
  implication: The port mismatch has been there since the deployment was changed to use port 8001

- timestamp: 2026-06-02T00:01:40Z
  checked: All localhost:8000 references across webui/src
  found: 14 occurrences across 8 files, all using localhost:8000 as the default FastAPI URL
  implication: Also fixed all client-side fallbacks for consistency

- timestamp: 2026-06-02T00:01:55Z
  checked: Verification via curl after fix
  found: curl http://localhost:3000/api/extract-pdf returns {"text":"Hello\n\n\n","filename":"test.pdf","size":309,"chars":8} - SUCCESS. curl http://localhost:3000/api/upload-to-workspace returns workspace_path and text_file_path - SUCCESS
  implication: Both API routes now correctly proxy to FastAPI on port 8001

## Resolution

root_cause: Next.js API route handlers (extract-pdf, upload-to-workspace) default to http://localhost:8000 for the Python backend, but the FastAPI server actually runs on port 8001. Port 8000 is occupied by the GSD tool server which returns "not found" for all requests. This causes PDF text extraction and workspace upload to silently fail, resulting in files being sent to the agent without extracted text content.
fix: Changed all default FastAPI URL fallbacks from localhost:8000 to localhost:8001 across the webui codebase (8 files, route handlers + client-side config)
verification: Verified both /api/extract-pdf and /api/upload-to-workspace routes now return correct data via curl
files_changed: [webui/src/app/api/extract-pdf/route.ts, webui/src/app/api/upload-to-workspace/route.ts, webui/src/app/components/ConfigDialog.tsx, webui/src/lib/config.ts, webui/src/app/hooks/useChat.ts, webui/src/lib/api/messages.ts, webui/src/lib/api/useApiTests.ts, webui/src/app/cases/page.tsx, webui/src/app/components/ThreadList.tsx, webui/src/app/hooks/useThreads.ts]
