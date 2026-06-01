---
status: investigating
trigger: "Frontend calls stream.submit() via @langchain/langgraph-sdk v1.9.1 useStream hook, but immediately throws BlockingError: An internal error occurred from StreamManager.enqueue. The request NEVER reaches the LangGraph server."
created: 2026-05-15T00:00:00.000Z
updated: 2026-05-15T00:00:00.000Z
---

## Current Focus

hypothesis: The error "BlockingError: An internal error occurred" is NOT from the SDK itself - "BlockingError" is not a class anywhere in the SDK or Next.js compiled output. The actual error is being thrown inside StreamManager.enqueue (line 351 of manager.js: `const run = await action(this.abortRef.signal)`) and the action callback in stream.lgp.js (line 338: `client.runs.stream(...)`) is failing. The root cause is likely that client.runs.stream() throws because the Client was constructed with a URL that causes a failure before any HTTP request (possibly invalid URL, missing thread, or SDK internal validation error).
test: Trace the actual error inside the action callback passed to StreamManager.enqueue to find what throws
expecting: Will find the actual error origin in the SDK client code
next_action: Read the SDK client.runs.stream implementation and the Client constructor to understand what validation happens before HTTP

## Symptoms

expected: User sends a message (with or without PDF), useStream submits to LangGraph server, server processes, streaming response displayed in chat UI.
actual: stream.submit() throws BlockingError immediately in browser. No request reaches server. Chat shows error.
errors: Browser console shows BlockingError: An internal error occurred at StreamManager.enqueue (manager.ts:764:25) at async StreamManager.start (manager.ts:1154:5) at async Object.submit (stream.lgp.tsx:514:5)
reproduction: Open http://localhost:3000/chat, create new conversation, type any message and send.
started: Started after removing Next.js proxy rewrite and reverting ClientProvider to use direct URL.

## Eliminated

## Evidence

- timestamp: 2026-05-15T00:00:01
  checked: SDK source files for BlockingError class definition
  found: BlockingError does NOT exist anywhere in @langchain/langgraph-sdk v1.9.1 or Next.js. The name may be a browser/React error overlay wrapper.
  implication: The real error is something else, wrapped as "BlockingError" by the browser or framework

- timestamp: 2026-05-15T00:00:02
  checked: StreamManager.enqueue in ui/manager.js (line 343-511)
  found: The enqueue method has a try/catch. Line 351 runs `const run = await action(this.abortRef.signal)` then iterates `for await (const { event, data } of run)`. The catch at line 500 catches non-AbortError/TimeoutError and calls setState({error}).
  implication: The error is either from the action callback itself or from the stream iteration

- timestamp: 2026-05-15T00:00:03
  checked: stream.lgp.js submit function (line 295-395)
  found: submit calls `stream.start(async (signal) => { ... client.runs.stream(usableThreadId, options.assistantId, {...}) })`. Before calling runs.stream, it first creates a thread (line 318-326) if no usableThreadId exists.
  implication: The failure could be in thread creation OR in runs.stream. Need to check which step fails.

- timestamp: 2026-05-15T00:00:04
  checked: ChatProvider.tsx passes activeAssistant?.assistant_id to useChat
  found: ChatProvider passes `activeAssistant?.assistant_id || ""` as assistantId to useChat. If activeAssistant is null, assistantId becomes empty string "".
  implication: Empty string assistantId would be passed to client.runs.stream as the assistant ID, which could cause an error

- timestamp: 2026-05-15T00:00:05
  checked: chat/page.tsx activeAssistant construction
  found: activeAssistant is always constructed as a non-null object (line 93-106) with assistant_id from AGENT_CONFIG. It uses `currentConfig?.graphKey ?? "testcase_agent"` as fallback.
  implication: assistantId should be a valid non-empty string, likely "testcase_agent"

## Resolution

root_cause:
fix:
verification:
files_changed: []
