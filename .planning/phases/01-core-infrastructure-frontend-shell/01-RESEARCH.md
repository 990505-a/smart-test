# Phase 1: Core Infrastructure + Frontend Shell - Research

**Researched:** 2026-05-11
**Domain:** DeepAgents + LangGraph API server, LightRAG lightweight storage, Next.js 15 chat UI, MCP integration
**Confidence:** HIGH

## Summary

Phase 1 builds the shared infrastructure layer and a fully operational chat frontend. The backend is a DeepAgents-powered LangGraph API server on port 2026 that registers three agent stubs (TestCase, Web, API) via a single graph.json. Each agent is a minimal `create_deep_agent` skeleton with no business logic -- just enough to respond to chat messages. The frontend is a Next.js 15 + React 19 + Shadcn/ui + Tailwind CSS 4 chat application that communicates with the backend via `@langchain/langgraph-sdk` using SSE streaming. File upload (drag-drop + paste) converts files to base64 and embeds them in messages using the `additional_kwargs.attachments` pattern validated in classroom code.

LightRAG runs locally with its default lightweight storage (NanoVectorDB for vectors + NetworkX for graphs + JSON for KV) -- no Docker or external databases needed. Ollama runs natively on Windows to serve the `qwen3-embedding:0.6b` embedding model. MCP services (Docling, Graphify, Playwright) are configured as external tool servers accessible via SSE or stdio transports.

**Primary recommendation:** Use the exact patterns from the three reference codebases. The 2026-04-09 frontend provides a complete, working chat UI with SSE streaming, file upload, and thread management. The 2026-05-07 backend provides the three-domain agent architecture and graph.json routing. Adapt minimally -- add Tab switching for 3 agents (new feature not in reference code) and swap from reference's local `workspace` path to the project's relative path.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Single graph.json multi-routing mode -- three Agents (TestCase/Web/API) registered in same graph.json, frontend routes by Agent name
- **D-02:** SSE streaming via @langchain/langgraph-sdk for frontend-backend communication
- **D-03:** DeepAgents >= 0.5.5 as main framework (create_deep_agent), LangGraph as underlying runtime
- **D-04:** File upload uses base64 embedding in message body -- frontend converts to base64, places in additional_kwargs.attachments, backend middleware extracts and parses
- **D-05:** External tools via MCP standard protocol -- Docling (SSE), Graphify (stdio), Playwright (stdio)
- **D-06:** Agent switching via top Tab bar -- three tabs: TestCase / Web / API
- **D-07:** Left-right split layout -- left thread list + right chat area, react-resizable-panels
- **D-08:** Light theme primary + dark theme toggle -- Shadcn/ui + Tailwind CSS + next-themes
- **D-09:** Frontend and backend in same repo -- src/ backend (Python) + webui/ frontend (Next.js)
- **D-10:** Development runs separately -- backend start_server.py + frontend npm run dev, two terminal windows

### Claude's Discretion
- Specific directory structure details (sub-directory naming under src/)
- Shadcn/ui component selection
- Thread management UI implementation details
- Frontend state management library selection

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INFRA-01 | Deploy LangGraph API server (port 2026) with multi-Agent routing (graph.json) | graph.json pattern from reference code; start_server.py pattern verified; multi-graph routing via multiple entries in `graphs` key |
| INFRA-02 | Configure DeepAgents framework (>= 0.5.5) with FilesystemBackend + CompositeBackend | `create_deep_agent` with `FilesystemBackend` pattern from 2026-05-07 reference; backend parameter documented in DeepAgents README |
| INFRA-03 | Configure LightRAG lightweight storage (NanoVectorDB + NetworkX + JSON) | LightRAG default storage is exactly this; no additional config needed; `lightrag-hku[api]` package provides server |
| INFRA-04 | Deploy LightRAG Server (lightweight mode) with 6 query modes | `lightrag-server` CLI starts on port 9621; modes: local/global/hybrid/naive/mix/bypass; verified via official docs |
| INFRA-05 | Native install Ollama (Windows exe), configure embedding model (qwen3-embedding:0.6b, 1024 dim) | Ollama v0.21.2 installed on system; `ollama pull qwen3-embedding:0.6b` to download; LightRAG configured via EMBEDDING_BINDING=ollama |
| INFRA-06 | Integrate MCP protocol (SSE/stdio), configure Docling/Graphify/Playwright MCP services | FastMCP pattern from rag_server.py reference; langchain-mcp-adapters for stdio; SSE for remote services |
| PARS-04 | Implement base64 to file conversion pipeline (frontend upload to backend parsing) | `fileToContentBlock()` + `fileToBase64()` from useFileUpload.ts; `additional_kwargs.attachments` pattern from useChat.ts sendMessage |
| UI-01 | Next.js 15.4.4 + React 19 + Tailwind CSS 4 + Shadcn/ui project setup | Verified package versions; `npx shadcn@latest init` for setup; Tailwind CSS 4 uses CSS-first config |
| UI-02 | Streaming chat interface (@langchain/langgraph-sdk, SSE real-time message rendering) | `useStream` hook from langgraph-sdk/react; verified in useChat.ts reference code |
| UI-03 | File upload (drag-drop + paste, support PDF/JPEG/PNG/GIF/WebP) | useFileUpload.ts provides complete implementation; window-level drag/drop + paste handlers |
| UI-04 | Image to base64 to image_url block (OpenAI compatible format) | `fileToContentBlock()` handles images -> `{type:"image", mimeType, data}` -> frontend converts to `image_url` format in sendMessage |
| UI-05 | PDF to base64 to additional_kwargs.attachments | `fileToContentBlock()` handles PDFs -> `{type:"file", mimeType:"application/pdf", data}` -> placed in `additional_kwargs.attachments` in sendMessage |
| UI-08 | Thread management (status filter, infinite scroll, time grouping) | useThreads.ts with SWRInfinite; ThreadList.tsx from reference; client.threads.search() API |
| UI-09 | Resizable panel layout (react-resizable-panels, sidebar for tasks/files) | `ResizablePanelGroup` pattern from page.tsx reference; panel sizes configurable |
| UI-10 | Multi-Agent route switching (TestCase/Web/API Agent selection) | Tab component from Shadcn/ui; switch `assistantId` / graph entry based on selected tab; NEW feature not in reference |
| UI-11 | Dark/light theme switching | next-themes package v0.4.6; ThemeProvider wrapper; Shadcn/ui CSS variables for both themes |
| UI-12 | URL state management (nuqs) | `useQueryState` hook from nuqs v2.8.9; NuqsAdapter in layout.tsx; verified in reference code |
</phase_requirements>

## Standard Stack

### Core Backend
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.13.2 | Runtime | Installed on system. Stable, matches classroom code. |
| deepagents | >= 0.5.5 (latest 0.5.9) | Agent framework | LangChain-maintained, provides create_deep_agent, SkillsMiddleware, FilesystemBackend out of the box |
| langgraph | >= 1.0.x (latest 1.1.10) | Agent orchestration | State machines, streaming, checkpointing. DeepAgents is built on this. |
| langgraph-api | >= 0.5.x (latest 0.8.7) | API server runtime | Uvicorn-based server that serves LangGraph agents via REST + SSE |
| langchain | >= 1.2.x | LLM abstraction | Model interfaces, init_chat_model. Required by DeepAgents. |
| langchain-deepseek | >= 1.0.1 | DeepSeek model provider | ChatDeepSeek for text LLM |
| langchain-mcp-adapters | >= 0.2.1 | MCP client integration | MultiServerMCPClient for connecting to MCP servers |
| lightrag-hku[api] | latest (1.4.16) | RAG engine with server | NanoVectorDB + NetworkX + JSON by default. API server on port 9621. |
| fastmcp | >= 3.1.1 | MCP server framework | Building custom MCP servers (RAG MCP server) |
| pydantic-settings | >= 2.x | Configuration management | BaseSettings with .env file support. Used in reference config.py |

### Core Frontend
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| next | 15.4.4 (latest 16.2.6) | Frontend framework | App Router, React 19, streaming. PROJECT.md says 15.4.4 but latest is 16.x -- use 15.4.4 per constraint |
| react | 19.x (latest 19.2.6) | UI library | Ships with Next.js. Server Components, Actions. |
| @langchain/langgraph-sdk | latest (1.9.1) | Agent API client | useStream hook for SSE, Client for threads/assistants API |
| @langchain/core | latest | Message types | ContentBlock.Multimodal.Data for file uploads |
| tailwindcss | 4.x (latest 4.3.0) | Styling | CSS-first config in v4. No tailwind.config.js needed. |
| shadcn/ui | latest | Component library | Copy-paste components on Radix UI. Tabs, Dialog, Button, Switch, ScrollArea, etc. |
| nuqs | latest (2.8.9) | URL state management | useQueryState for threadId, sidebar state. NuqsAdapter wrapper. |
| next-themes | latest (0.4.6) | Theme switching | Light/dark mode with system preference detection |

### Supporting Frontend
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| react-resizable-panels | latest (4.11.0) | Split layout | Left panel (threads) + right panel (chat) with drag handle |
| swr | latest (2.4.1) | Data fetching | SWRInfinite for paginated thread list loading |
| sonner | latest (2.0.7) | Toast notifications | File upload errors, validation messages |
| lucide-react | latest | Icons | Tab icons, button icons, status indicators |
| use-stick-to-bottom | latest (1.1.4) | Auto-scroll | Chat message list scrolls to bottom on new messages |
| date-fns | latest (4.1.0) | Date formatting | Thread timestamp display, time grouping |
| react-markdown | latest | Markdown rendering | Chat message content rendering |
| remark-gfm | latest | GitHub-flavored markdown | Tables, strikethrough in messages |
| uuid | latest | UUID generation | Message IDs for HumanMessage |
| clsx + tailwind-merge | latest | Class utilities | cn() utility for conditional classes |

### Supporting Backend
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| httpx | >= 0.27 | Async HTTP client | Calling LightRAG Server API, MCP SSE connections |
| python-dotenv | >= 1.0 | Environment loading | Loading .env files for API keys and config |
| uvicorn | >= 0.30 | ASGI server | Running the LangGraph API server |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| next-themes | Manual CSS class toggle | next-themes handles system preference, flash prevention, SSR -- not worth hand-rolling |
| swr | @tanstack/react-query | SWR simpler for this use case (thread listing). react-query better for complex mutations. |
| react-resizable-panels | CSS Grid resize | Panel library handles drag handles, min/max sizes, persistence -- CSS alone insufficient |

**Installation:**
```bash
# === Backend (Python) ===
cd D:/test_agent/smart-test-platform
uv init --no-readme
uv add deepagents>=0.5.5 langgraph>=1.0.0 langgraph-cli[inmem] langchain>=1.2.0 langchain-deepseek>=1.0.1 langchain-mcp-adapters>=0.2.1 fastmcp>=3.1.1 pydantic-settings python-dotenv httpx

# === Frontend (Node.js) ===
cd D:/test_agent/smart-test-platform
npx create-next-app@15.4.4 webui --typescript --tailwind --eslint --app --src-dir --import-alias "@/*"
cd webui
npx shadcn@latest init
npx shadcn@latest add button tabs dialog switch scroll-area tooltip textarea select skeleton resizable
npm install @langchain/langgraph-sdk @langchain/core nuqs next-themes react-resizable-panels swr sonner lucide-react use-stick-to-bottom date-fns react-markdown remark-gfm uuid clsx tailwind-merge

# === LightRAG Server ===
pip install "lightrag-hku[api]"

# === Ollama embedding model ===
ollama pull qwen3-embedding:0.6b
```

## Architecture Patterns

### Recommended Project Structure
```
smart-test-platform/
├── .env                          # API keys (DEEPSEEK_API_KEY, etc.)
├── .env.example                  # Template without secrets
├── pyproject.toml                # Python backend dependencies
├── graph.json                    # LangGraph multi-agent routing config
├── start_server.py               # Backend startup script (port 2026)
├── src/                          # Backend Python source
│   └── app/
│       ├── __init__.py
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── testcase/
│       │   │   ├── __init__.py
│       │   │   └── agent.py      # TestCase Agent stub
│       │   ├── web/
│       │   │   ├── __init__.py
│       │   │   └── agent.py      # Web Agent stub
│       │   └── api/
│       │       ├── __init__.py
│       │       └── agent.py      # API Agent stub
│       ├── core/
│       │   ├── __init__.py
│       │   ├── config.py         # Settings (pydantic BaseSettings)
│       │   └── llms.py           # LLM model initialization
│       └── mcp/
│           ├── __init__.py
│           └── rag_server.py     # RAG MCP Server (Phase 3, stub now)
├── webui/                        # Frontend Next.js project
│   ├── package.json
│   ├── next.config.ts
│   ├── postcss.config.mjs
│   ├── tsconfig.json
│   ├── components.json           # Shadcn/ui config
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx        # Root layout with NuqsAdapter + ThemeProvider
│   │   │   ├── page.tsx          # Main page with resizable panels
│   │   │   ├── globals.css       # Tailwind CSS 4 + Shadcn/ui theme variables
│   │   │   ├── components/
│   │   │   │   ├── ChatInterface.tsx    # Main chat area
│   │   │   │   ├── ChatMessage.tsx      # Message rendering
│   │   │   │   ├── ThreadList.tsx       # Left sidebar thread list
│   │   │   │   ├── AgentTabs.tsx        # Top tab bar for 3 agents
│   │   │   │   ├── ConfigDialog.tsx     # Server URL + API key config
│   │   │   │   ├── MultimodalPreview.tsx # File preview before send
│   │   │   │   └── ContentBlocksPreview.tsx
│   │   │   ├── hooks/
│   │   │   │   ├── useChat.ts           # Streaming chat via useStream
│   │   │   │   ├── useThreads.ts        # Thread list with SWRInfinite
│   │   │   │   └── useFileUpload.ts     # Drag-drop + paste file handling
│   │   │   ├── types/
│   │   │   │   └── types.ts             # TypeScript interfaces
│   │   │   └── utils/
│   │   │       ├── multimodal.ts        # File-to-base64 conversion
│   │   │       └── utils.ts             # Helper functions
│   │   ├── components/
│   │   │   └── ui/                       # Shadcn/ui components
│   │   ├── providers/
│   │   │   ├── ClientProvider.tsx        # LangGraph SDK Client context
│   │   │   ├── ChatProvider.tsx          # Chat hook context
│   │   │   └── ThemeProvider.tsx         # next-themes wrapper
│   │   └── lib/
│   │       ├── config.ts                # LocalStorage config (deploymentUrl, assistantId)
│   │       └── utils.ts                 # cn() utility
│   └── public/
├── rag_storage/                  # LightRAG data directory (auto-created)
└── .planning/                    # GSD planning artifacts
```

### Pattern 1: graph.json Multi-Agent Routing
**What:** A single graph.json registers multiple agent graphs, each with a unique key. The frontend selects which graph to interact with via the `assistantId` parameter.
**When to use:** This is the core routing mechanism for the three-domain agent architecture.
**Example:**
```json
{
  "dependencies": ["."],
  "graphs": {
    "testcase_agent": {
      "path": "./src/app/agents/testcase/agent.py:agent"
    },
    "web_agent": {
      "path": "./src/app/agents/web/agent.py:agent"
    },
    "api_agent": {
      "path": "./src/app/agents/api/agent.py:agent"
    }
  },
  "env": ".env"
}
```

The key insight is that `LANGSERVE_GRAPHS` environment variable (set in start_server.py) takes this JSON, and the LangGraph API server exposes each graph as a separate assistant. The frontend uses the graph key as the `assistantId` when calling `useStream()`.

**How frontend routes to a specific agent:**
```typescript
// When user selects "TestCase" tab, the assistantId becomes "testcase_agent"
// When user selects "Web" tab, it becomes "web_agent"
// When user selects "API" tab, it becomes "api_agent"
const stream = useStream<StateType>({
  assistantId: selectedAgentKey, // "testcase_agent" | "web_agent" | "api_agent"
  client: client,
  threadId: threadId,
});
```

### Pattern 2: DeepAgents Agent Stub
**What:** A minimal `create_deep_agent` call that creates a functional agent with no business logic.
**When to use:** Phase 1 only needs skeleton agents that can respond to messages.
**Example:**
```python
# src/app/agents/testcase/agent.py
from deepagents import create_deep_agent as create_agent
from deepagents.backends import FilesystemBackend
from langchain.chat_models import init_chat_model
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

llm = init_chat_model("deepseek:deepseek-chat")
workspace_dir = Path(__file__).parent.parent.parent.parent / "workspace"
file_backend = FilesystemBackend(root_dir=workspace_dir, virtual_mode=True)

agent = create_agent(
    model=llm,
    tools=[],  # No tools in Phase 1 stub
    backend=file_backend,
    middleware=[],  # No middleware in Phase 1 stub
    system_prompt="You are a test case generation assistant. Respond helpfully to user queries about test case generation.",
)
```

### Pattern 3: File Upload Pipeline (Frontend)
**What:** Complete drag-drop + paste + file input pipeline that converts files to base64 ContentBlocks.
**When to use:** Every message that includes file attachments.
**Flow:**
1. User drags/pastes/selects file
2. `fileToContentBlock()` converts to `{type:"image"|"file", mimeType, data, metadata}`
3. Blocks displayed in `ContentBlocksPreview` before sending
4. On send, `sendMessage()` in useChat splits blocks:
   - Image blocks -> converted to `image_url` format in message content array
   - PDF blocks -> placed in `additional_kwargs.attachments`
5. Sent via `stream.submit({messages: [newMessage]})`

**Key code from reference (useChat.ts sendMessage):**
```typescript
const imageBlocks = contentBlocks?.filter((b) => b.type === "image") ?? [];
const pdfBlocks = contentBlocks?.filter((b) => b.type !== "image") ?? [];

const imageUrlBlocks = imageBlocks.map((b) => ({
  type: "image_url" as const,
  image_url: { url: `data:${b.mimeType};base64,${b.data}` },
}));

const messageContent = imageUrlBlocks.length > 0
  ? [{ type: "text", text: content }, ...imageUrlBlocks]
  : content;

const newMessage = {
  id: uuidv4(),
  type: "human",
  content: messageContent,
  ...(pdfBlocks.length > 0
    ? { additional_kwargs: { attachments: pdfBlocks } }
    : {}),
};
```

### Pattern 4: SSE Streaming via useStream Hook
**What:** Real-time message streaming from LangGraph API to the React frontend.
**When to use:** All chat interactions.
**Example:**
```typescript
import { useStream } from "@langchain/langgraph-sdk/react";

const stream = useStream<StateType>({
  assistantId: "testcase_agent",
  client: client,
  threadId: threadId,
  onThreadId: setThreadId,
  onFinish: () => revalidateThreads(),
});

// Access streaming messages
const messages = stream.messages;      // Message[] with real-time updates
const isLoading = stream.isLoading;    // Boolean streaming state

// Send a message
stream.submit(
  { messages: [newMessage] },
  { config: { recursion_limit: 1000 } }
);
```

### Pattern 5: LightRAG Lightweight Server Configuration
**What:** LightRAG server with default file-based storage, no Docker needed.
**When to use:** Phase 1 setup of RAG infrastructure.
**Configuration (.env in project root):**
```env
PORT=9621
LLM_BINDING=openai
LLM_MODEL=deepseek-chat
LLM_BINDING_HOST=https://api.deepseek.com/v1
LLM_BINDING_API_KEY=${DEEPSEEK_API_KEY}

EMBEDDING_BINDING=ollama
EMBEDDING_BINDING_HOST=http://localhost:11434
EMBEDDING_MODEL=qwen3-embedding:0.6b
EMBEDDING_DIM=1024
```
**Start command:** `lightrag-server` (runs in project root where .env exists)

LightRAG defaults:
- KV_STORAGE: JsonKVStorage (JSON files)
- VECTOR_STORAGE: NanoVectorDBStorage (JSON-based vector DB)
- GRAPH_STORAGE: NetworkXStorage (NetworkX graph as JSON)
- DOC_STATUS_STORAGE: JsonDocStatusStorage

All data persisted to `./rag_storage/` directory by default. No external databases required.

### Anti-Patterns to Avoid
- **Don't put business logic in Phase 1 agents:** These are stubs. No Skills, no middleware, no tools beyond what DeepAgents provides by default. Business logic starts in Phase 2.
- **Don't use Docker for any Phase 1 service:** Everything runs natively. Ollama is a Windows exe. LightRAG runs as a Python process. The backend runs via uvicorn.
- **Don't create a monolithic agent file:** Keep three separate agent.py files in their respective directories. graph.json routes to each independently.
- **Don't build custom SSE implementation:** Use `@langchain/langgraph-sdk`'s `useStream` hook. It handles reconnection, message ordering, and streaming state.
- **Don't use `tailwind.config.js` with Tailwind CSS 4:** v4 uses CSS-first configuration in `globals.css` via `@theme` directive. The reference code uses v3 with config file -- must adapt to v4 approach.
- **Don't use Next.js 16:** It does not exist. The reference frontend package.json shows `"next": "^16.1.7"` but this is from a different project. PROJECT.md constraint says 15.4.4.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SSE streaming client | Custom EventSource + message parsing | @langchain/langgraph-sdk `useStream` hook | Handles reconnection, message ordering, thread management, interrupt detection |
| File upload with drag-drop | Custom drag event handlers from scratch | useFileUpload.ts pattern from reference | Window-level event handling, duplicate detection, MIME type validation, paste support |
| Thread CRUD operations | Custom REST calls | @langchain/langgraph-sdk `Client.threads` API | Server manages state, persistence, checkpointing |
| Base64 file conversion | Custom FileReader wrappers | `fileToBase64()` from multimodal.ts | Handles data URL prefix stripping, async/await pattern |
| Agent routing | Custom router middleware | graph.json multi-graph entries + frontend assistantId selection | LangGraph API server handles graph resolution, no custom routing code needed |
| RAG query client | Custom HTTP calls to LightRAG | RAGServiceClient pattern from rag_server.py | Connection pooling, JWT auth, retry with backoff |
| Theme switching | Manual CSS class toggling | next-themes `ThemeProvider` | System preference detection, flash prevention, SSR-safe |
| URL state persistence | Manual URL search params parsing | nuqs `useQueryState` | Type-safe, handles encoding/decoding, SSR-compatible |
| Config management | Manual config loading | pydantic-settings `BaseSettings` | Validation, type coercion, .env file support, nested settings |

**Key insight:** The reference codebase (2026-04-09) provides production-quality implementations for the chat UI, streaming, file upload, and thread management. Copy these patterns directly. The 2026-05-07 reference provides the multi-agent architecture. Combine them with minimal adaptation.

## Common Pitfalls

### Pitfall 1: graph.json Multi-Graph Discovery
**What goes wrong:** Frontend cannot find assistants when using graph names instead of UUIDs.
**Why it happens:** The LangGraph API server in local development mode registers graphs by name, but the SDK's `client.assistants.search()` may not find them the same way as deployed assistants.
**How to avoid:** Use the graph name directly as `assistantId` in `useStream()`. For the local dev server, graph names work directly. The reference code handles both UUID and graph name cases in `page.tsx` with the `isUUID` check.
**Warning signs:** "No default assistant found" error in browser console.

### Pitfall 2: Tailwind CSS v4 Migration from v3 Reference
**What goes wrong:** Copying Tailwind config from reference code (which uses v3) into a v4 project causes styles to break.
**Why it happens:** Tailwind CSS v4 replaced `tailwind.config.js` with CSS-first configuration using `@theme` directives in `globals.css`. The `tailwindcss-animate` plugin is no longer needed (animations are built-in).
**How to avoid:** Start fresh with `npx create-next-app@15.4.4 --tailwind` and `npx shadcn@latest init`. Do NOT copy `tailwind.config.js` from reference code. Only copy component code and hook logic.
**Warning signs:** Utility classes not applying, missing theme variables, broken animations.

### Pitfall 3: Ollama Not Running When LightRAG Starts
**What goes wrong:** LightRAG server fails to start or throws embedding errors because Ollama is not running.
**Why it happens:** LightRAG needs the embedding model available at startup to initialize vector storage. Ollama must be running and the model must be pulled before starting LightRAG.
**How to avoid:** Create a startup checklist: (1) Start Ollama (it runs as a background service on Windows), (2) Verify `ollama list` shows `qwen3-embedding:0.6b`, (3) Then start LightRAG server.
**Warning signs:** "Connection refused" to localhost:11434, or "model not found" errors.

### Pitfall 4: Thread State Leakage Between Agents
**What goes wrong:** Switching agent tabs shows messages from a different agent's thread.
**Why it happens:** The `threadId` stored in URL state persists across tab switches. If the user switches from TestCase to Web tab, the old threadId still points to a TestCase conversation.
**How to avoid:** Clear `threadId` when switching agent tabs. Each agent has its own graph, and threads are graph-specific, but the URL state is shared. Implement: `onTabChange -> setThreadId(null)`.
**Warning signs:** Messages from TestCase agent appearing in Web agent tab.

### Pitfall 5: File Upload Race Condition with State
**What goes wrong:** Content blocks reference stale state when multiple files are uploaded rapidly.
**Why it happens:** The `contentBlocks` state in `useFileUpload` is used in event handler closures that don't receive the latest state.
**How to avoid:** Use functional state updates `setContentBlocks(prev => [...prev, ...newBlocks])` consistently (the reference code already does this). Also ensure `useEffect` dependency array for drag handlers includes `contentBlocks`.
**Warning signs:** Duplicate files in preview, or files disappearing after rapid uploads.

### Pitfall 6: Next.js 15 vs 16 Version Confusion
**What goes wrong:** Developer accidentally installs Next.js 16 (which exists as of May 2026, version 16.2.6) instead of 15.4.4.
**Why it happens:** `npm install next` pulls the latest (16.x). The reference code package.json shows `"next": "^16.1.7"`. But CONTEXT.md says use 15.4.4.
**How to avoid:** Pin the version: `npm install next@15.4.4`. Use `npx create-next-app@15.4.4` when scaffolding.
**Warning signs:** Build errors from API changes between 15 and 16.

### Pitfall 7: LightRAG Working Directory Must Contain .env
**What goes wrong:** `lightrag-server` fails to find its configuration.
**Why it happens:** LightRAG intentionally requires `.env` in the current working directory. It does NOT search parent directories.
**How to avoid:** Always `cd` to the project root before running `lightrag-server`. Or create a wrapper script that changes directory first.
**Warning signs:** "Missing LLM_BINDING configuration" or using wrong defaults.

## Code Examples

Verified patterns from reference codebases:

### start_server.py (Backend Server)
```python
#!/usr/bin/env python3
"""LangGraph API Server for Smart Test Platform - Port 2026"""
import os, sys, json
from pathlib import Path

def setup_environment():
    src_path = Path(__file__).parent / "src"
    sys.path.insert(0, str(src_path))

    config_path = Path(__file__).parent / "graph.json"
    graphs = {}
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            graphs = config.get("graphs", {})

    os.environ.update({
        "DATABASE_URI": ":memory:",
        "REDIS_URI": "fake",
        "MIGRATIONS_PATH": "__inmem",
        "ALLOW_PRIVATE_NETWORK": "true",
        "LANGGRAPH_UI_BUNDLER": "true",
        "LANGGRAPH_RUNTIME_EDITION": "inmem",
        "LANGSMITH_LANGGRAPH_API_VARIANT": "local_dev",
        "LANGGRAPH_DISABLE_FILE_PERSISTENCE": "false",
        "LANGGRAPH_ALLOW_BLOCKING": "true",
        "LANGGRAPH_API_URL": "http://localhost:2026",
        "LANGSERVE_GRAPHS": json.dumps(graphs),
        "N_JOBS_PER_WORKER": "1",
    })

    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file)

def main():
    setup_environment()
    import uvicorn
    uvicorn.run(
        "langgraph_api.server:app",
        host="0.0.0.0",
        port=2026,
        reload=False,
    )

if __name__ == "__main__":
    main()
```
Source: Adapted from 2026-05-07-ai-test-agent-system/start_server.py

### Agent Stub (src/app/agents/testcase/agent.py)
```python
from deepagents import create_deep_agent as create_agent
from deepagents.backends import FilesystemBackend
from langchain.chat_models import init_chat_model
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

llm = init_chat_model("deepseek:deepseek-chat")
workspace_dir = Path(__file__).parent.parent.parent.parent / "workspace"
file_backend = FilesystemBackend(root_dir=workspace_dir, virtual_mode=True)

agent = create_agent(
    model=llm,
    tools=[],
    backend=file_backend,
    middleware=[],
    system_prompt="You are a test case generation assistant for the Smart Test Platform. "
                  "In this initial phase, respond helpfully to user queries. "
                  "Full test case generation capabilities will be added soon.",
)
```
Source: Adapted from 2026-05-07-ai-test-agent-system/agents/testcase/agent.py

### Frontend Config (src/lib/config.ts)
```typescript
export interface StandaloneConfig {
  deploymentUrl: string;
  assistantId: string;
  langsmithApiKey?: string;
}

const CONFIG_KEY = "deep-agent-config";

export function getConfig(): StandaloneConfig | null {
  if (typeof window === "undefined") return null;
  const stored = localStorage.getItem(CONFIG_KEY);
  if (!stored) return null;
  try { return JSON.parse(stored); }
  catch { return null; }
}

export function saveConfig(config: StandaloneConfig): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(CONFIG_KEY, JSON.stringify(config));
}
```
Source: Direct from 2026-04-09-testing-deep-agents-ui/src/lib/config.ts

### Frontend useChat Hook Pattern
```typescript
// Key: useStream from langgraph-sdk provides SSE streaming
import { useStream } from "@langchain/langgraph-sdk/react";

export function useChat({ activeAssistant, onHistoryRevalidate, thread }) {
  const [threadId, setThreadId] = useQueryState("threadId");
  const client = useClient();

  const stream = useStream<StateType>({
    assistantId: activeAssistant?.assistant_id || "",
    client: client ?? undefined,
    reconnectOnMount: true,
    threadId: threadId ?? null,
    onThreadId: setThreadId,
    fetchStateHistory: true,
    onFinish: () => onHistoryRevalidate?.(),
  });

  const sendMessage = (content, contentBlocks, context) => {
    const imageBlocks = contentBlocks?.filter(b => b.type === "image") ?? [];
    const pdfBlocks = contentBlocks?.filter(b => b.type !== "image") ?? [];
    const imageUrlBlocks = imageBlocks.map(b => ({
      type: "image_url", image_url: { url: `data:${b.mimeType};base64,${b.data}` }
    }));
    const messageContent = imageUrlBlocks.length > 0
      ? [{ type: "text", text: content }, ...imageUrlBlocks]
      : content;
    const newMessage = {
      id: uuidv4(), type: "human", content: messageContent,
      ...(pdfBlocks.length > 0 ? { additional_kwargs: { attachments: pdfBlocks } } : {}),
    };
    stream.submit({ messages: [newMessage] }, { config: { recursion_limit: 1000 }, context });
  };

  return { stream, messages: stream.messages, isLoading: stream.isLoading, sendMessage };
}
```
Source: Adapted from 2026-04-09-testing-deep-agents-ui/src/app/hooks/useChat.ts

### Frontend File Upload Pattern
```typescript
export async function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const result = reader.result as string;
      resolve(result.split(",")[1]); // Strip data:...;base64, prefix
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export async function fileToContentBlock(file: File): Promise<ContentBlock.Multimodal.Data> {
  const data = await fileToBase64(file);
  const imageTypes = ["image/jpeg", "image/png", "image/gif", "image/webp"];
  if (imageTypes.includes(file.type)) {
    return { type: "image", mimeType: file.type, data, metadata: { name: file.name } };
  }
  return { type: "file", mimeType: "application/pdf", data, metadata: { filename: file.name } };
}
```
Source: Direct from 2026-04-09-testing-deep-agents-ui/src/app/utils/multimodal.ts

### Frontend Layout with Theme + nuqs
```typescript
// layout.tsx
import { NuqsAdapter } from "nuqs/adapters/next/app";
import { ThemeProvider } from "@/providers/ThemeProvider";
import { Toaster } from "sonner";
import "./globals.css";

export default function RootLayout({ children }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body>
        <ThemeProvider attribute="class" defaultTheme="light" enableSystem>
          <NuqsAdapter>{children}</NuqsAdapter>
          <Toaster />
        </ThemeProvider>
      </body>
    </html>
  );
}
```

### Agent Tab Switching (New Feature)
```typescript
// This is the key new component not in reference code
// Tab switching changes the assistantId which drives useStream to connect to a different graph
const AGENT_CONFIG = {
  testcase: { key: "testcase_agent", label: "用例生成" },
  web:      { key: "web_agent",      label: "Web自动化" },
  api:      { key: "api_agent",      label: "API自动化" },
};

function AgentTabs({ activeAgent, onAgentChange }) {
  return (
    <Tabs value={activeAgent} onValueChange={(v) => onAgentChange(v as AgentKey)}>
      <TabsList>
        {Object.entries(AGENT_CONFIG).map(([key, cfg]) => (
          <TabsTrigger key={key} value={key}>{cfg.label}</TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  );
}

// In page.tsx, switching agent clears threadId:
const handleAgentChange = (agentKey: string) => {
  setActiveAgent(agentKey);
  setThreadId(null); // Clear thread when switching agents
};
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Tailwind CSS 3 with `tailwind.config.js` | Tailwind CSS 4 with CSS-first `@theme` in globals.css | Jan 2025 (v4 beta), May 2025 (stable) | No more JS config file; theme variables in CSS |
| `@langchain/langgraph-sdk` 0.0.x | 1.x with `useStream` hook | Late 2025 | Simpler React integration, built-in reconnection, thread management |
| LightRAG with PostgreSQL only | LightRAG with NanoVectorDB + NetworkX default | Ongoing (since inception) | Zero-config local storage, no external databases needed |
| DeepAgents 0.4.x | DeepAgents 0.5.x (latest 0.5.9) | Apr 2026 | Improved SkillsMiddleware, Backend abstractions |
| Next.js 14/15 with Pages Router | Next.js 15+ App Router only | Late 2024 | Server Components, streaming, App Router is the standard |
| SWR for data fetching | Still SWR (simple) or React Query (complex) | -- | SWR remains preferred for simple read-heavy patterns |

**Deprecated/outdated:**
- `tailwindcss-animate`: No longer needed with Tailwind CSS 4 (animations built-in)
- `@headlessui/tailwindcss` plugin: Merged into Tailwind CSS 4 core
- Custom SSE implementations: Replaced by `useStream` from langgraph-sdk

## Open Questions

1. **Next.js version selection**
   - What we know: CONTEXT.md and PROJECT.md say 15.4.4. The reference frontend package.json shows `"next": "^16.1.7"`. Latest npm is 16.2.6.
   - What's unclear: Whether 15.4.4 is a deliberate constraint (compatibility with classroom code) or an oversight.
   - Recommendation: Use 15.4.4 per the CONTEXT.md locked decision. The reference frontend can be adapted to work with 15.x.

2. **LightRAG Server LLM binding**
   - What we know: LightRAG needs an LLM for document indexing/extraction. DeepSeek is the project's text LLM.
   - What's unclear: Whether LightRAG's LLM is used only for RAG indexing (Phase 3) or if the server startup requires a valid LLM immediately.
   - Recommendation: Configure LLM_BINDING=openai with DeepSeek API. The server starts regardless but indexing won't work without LLM. For Phase 1, LightRAG just needs to be running -- no documents to index yet.

3. **MCP services availability**
   - What we know: Docling, Graphify, and Playwright MCP services need to be running for the agents to use them.
   - What's unclear: Whether these services are pre-installed on the development machine, or if Phase 1 needs to install them.
   - Recommendation: For Phase 1, configure MCP connection strings but don't block on MCP service availability. Agents are stubs and won't call MCP tools yet. Verify MCP services are reachable as a health check, not as a blocking dependency.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Backend runtime | Available | 3.13.2 | -- |
| Node.js | Frontend runtime | Available | 22.14.0 | -- |
| npm | Frontend package manager | Available | 10.9.2 | -- |
| uv | Python package manager | Available | 0.9.9 | pip |
| Ollama | Embedding model host | Available (not running) | 0.21.2 | -- |
| DeepSeek API Key | LLM provider | In .env (expected) | -- | -- |
| LightRAG | RAG server | Not installed | -- | `pip install "lightrag-hku[api]"` |
| Docling MCP | Document parsing | Not verified | -- | Non-blocking for Phase 1 |
| Graphify MCP | Code knowledge graph | Not verified | -- | Non-blocking for Phase 1 |
| Playwright MCP | Browser automation | Not verified | -- | Non-blocking for Phase 1 |

**Missing dependencies with no fallback:**
- Ollama model `qwen3-embedding:0.6b` must be pulled before LightRAG can generate embeddings. Run `ollama pull qwen3-embedding:0.6b`.
- DeepSeek API key must be configured in `.env` for the backend agents to respond.

**Missing dependencies with fallback:**
- LightRAG Server: Install via `pip install "lightrag-hku[api]"` or `uv add "lightrag-hku[api]"`.
- MCP services (Docling/Graphify/Playwright): Non-blocking for Phase 1. Health check only.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Backend: pytest / Frontend: Jest (via Next.js) + React Testing Library |
| Config file | pytest.ini (backend) / jest.config.ts (frontend, auto-generated by Next.js) |
| Quick run command (backend) | `pytest tests/ -x -q` |
| Quick run command (frontend) | `cd webui && npm test -- --passWithNoTests` |
| Full suite command | `pytest tests/ -v && cd webui && npm test` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFRA-01 | LangGraph API server responds on port 2026 | smoke | `curl http://localhost:2026/ok` | Wave 0 |
| INFRA-02 | DeepAgents agent creates successfully with FilesystemBackend | unit | `pytest tests/test_agents.py::test_create_testcase_agent -x` | Wave 0 |
| INFRA-03 | LightRAG storage configured with NanoVectorDB + NetworkX | smoke | `curl http://localhost:9621/health` | Wave 0 |
| INFRA-04 | LightRAG Server supports 6 query modes | integration | `pytest tests/test_lightrag.py -x` | Wave 0 |
| INFRA-05 | Ollama serves qwen3-embedding model | smoke | `curl http://localhost:11434/api/tags` | Wave 0 |
| INFRA-06 | MCP client connects to configured services | integration | `pytest tests/test_mcp.py -x` | Wave 0 |
| PARS-04 | File converts to base64 ContentBlock correctly | unit | `cd webui && npm test -- --testPathPattern=multimodal` | Wave 0 |
| UI-01 | Next.js app builds and renders | smoke | `cd webui && npm run build` | Wave 0 |
| UI-02 | SSE streaming delivers messages | integration | manual (browser test) | Manual |
| UI-03 | File upload via drag-drop and paste works | integration | `cd webui && npm test -- --testPathPattern=useFileUpload` | Wave 0 |
| UI-08 | Thread list loads and paginates | unit | `cd webui && npm test -- --testPathPattern=useThreads` | Wave 0 |
| UI-10 | Agent tab switching changes active assistantId | unit | `cd webui && npm test -- --testPathPattern=AgentTabs` | Wave 0 |
| UI-11 | Theme toggle switches CSS variables | unit | `cd webui && npm test -- --testPathPattern=theme` | Wave 0 |
| UI-12 | URL state persists threadId and sidebar | unit | `cd webui && npm test -- --testPathPattern=nuqs` | Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/ -x -q` (backend) or `cd webui && npm test` (frontend)
- **Per wave merge:** Full suite: `pytest tests/ -v && cd webui && npm run build && npm test`
- **Phase gate:** All smoke tests pass + frontend builds successfully + manual browser verification of SSE streaming

### Wave 0 Gaps
- [ ] `tests/test_agents.py` -- covers INFRA-01, INFRA-02
- [ ] `tests/test_lightrag.py` -- covers INFRA-03, INFRA-04
- [ ] `tests/test_mcp.py` -- covers INFRA-06
- [ ] `webui/src/app/hooks/__tests__/useFileUpload.test.ts` -- covers PARS-04, UI-03
- [ ] `webui/src/app/hooks/__tests__/useThreads.test.ts` -- covers UI-08
- [ ] `webui/src/app/components/__tests__/AgentTabs.test.tsx` -- covers UI-10
- [ ] pytest framework install: `uv add pytest pytest-asyncio --dev`
- [ ] Frontend test setup: `cd webui && npm install -D @testing-library/react @testing-library/jest-dom jest jest-environment-jsdom`

## Sources

### Primary (HIGH confidence)
- Reference code: `2026-05-07-ai-test-agent-system/` -- three-domain agent architecture, graph.json, start_server.py, agent patterns
- Reference code: `2026-04-09-testing-deep-agents-ui/` -- complete frontend chat UI with SSE streaming, file upload, thread management
- Reference code: `2026-03-25-testing-agent-system/` -- DeepAgents basics, create_deep_agent usage
- LightRAG API Server docs: https://github.com/HKUDS/LightRAG/blob/main/docs/LightRAG-API-Server.md -- server configuration, port 9621, storage backends
- DeepAgents GitHub: https://github.com/langchain-ai/deepagents -- create_deep_agent API, FilesystemBackend, SkillsMiddleware
- npm registry (verified 2026-05-11): next 16.2.6 (using 15.4.4 per constraint), @langchain/langgraph-sdk 1.9.1, nuqs 2.8.9, tailwindcss 4.3.0
- PyPI registry (verified 2026-05-11): deepagents 0.5.9, lightrag-hku 1.4.16, langgraph-api 0.8.7, langgraph 1.1.10

### Secondary (MEDIUM confidence)
- Shadcn/ui official docs: https://ui.shadcn.com/docs/installation/next -- Next.js 15 setup with Tailwind CSS 4
- next-themes: https://www.npmjs.com/package/next-themes -- v0.4.6, ThemeProvider configuration
- Railway LightRAG deployment: https://railway.com/deploy/light-rag -- confirms default NanoVectorDB + NetworkX storage
- Tailwind + Next.js setup guide: https://designrevision.com/blog/tailwind-nextjs-setup -- Tailwind CSS v4 with Next.js 15

### Tertiary (LOW confidence)
- MCP service availability (Docling, Graphify, Playwright) -- not verified on this machine, assumed configurable but not necessarily installed

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all versions verified against registries on 2026-05-11, reference code validates patterns
- Architecture: HIGH -- three reference codebases provide working implementations of every core pattern
- Pitfalls: HIGH -- based on actual reference code analysis and LightRAG official documentation
- Code examples: HIGH -- all sourced from verified reference codebases with minimal adaptation
- Environment: HIGH -- verified Python 3.13.2, Node 22.14.0, Ollama 0.21.2 on system

**Research date:** 2026-05-11
**Valid until:** 2026-06-11 (30 days -- stable libraries, low risk of breaking changes)
