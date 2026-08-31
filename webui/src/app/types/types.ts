export type AgentKey = "testcase" | "unity" | "codeanalyst";

export interface AgentConfig {
  key: string;
  label: string;
  graphKey: string;
}

export const AGENT_CONFIG: Record<AgentKey, AgentConfig> = {
  testcase: { key: "testcase", label: "用例生成", graphKey: "testcase_agent" },
  unity: { key: "unity", label: "UI自动化", graphKey: "unity_agent" },
  codeanalyst: { key: "codeanalyst", label: "代码分析", graphKey: "code_analyst_agent" },
};

export interface ContentBlock {
  type: "image" | "file";
  mimeType: string;
  data: string;
  metadata?: {
    name?: string;
    filename?: string;
    /** @deprecated Use workspacePath instead. Full text embedding causes thread state bloat. */
    extractedText?: string;
    /** Virtual absolute path where file is saved (e.g., /uploads/abc_doc.pdf). Agent reads via read_file tool. */
    workspacePath?: string;
    /** Virtual absolute path to extracted text file (e.g., /uploads/abc_doc_extracted.txt). */
    textFilePath?: string;
    /** Preview of extracted text (first 200 chars) for display. */
    textPreview?: string;
  };
}

export interface StateType {
  messages: Array<{
    id: string;
    type: "human" | "ai" | "system";
    content: string | Array<Record<string, unknown>>;
    additional_kwargs?: Record<string, unknown>;
  }>;
  todos?: TodoItem[];
  files?: Record<string, string>;
  ui?: unknown[];
}

/** 7-Agent Director Pipeline stages for Web Automation sub-agent visualization. */
export const PIPELINE_STAGES = [
  { id: "script-analyst", label: "Script Analyst", marker: "[Script Analyst]" },
  { id: "stage-manager", label: "Stage Manager", marker: "[Stage Manager]" },
  { id: "blocking-coach", label: "Blocking Coach", marker: "[Blocking Coach]" },
  { id: "set-designer", label: "Set Designer", marker: "[Set Designer]" },
  { id: "choreographer", label: "Choreographer", marker: "[Choreographer]" },
  { id: "assistant-director", label: "Assistant Director", marker: "[Assistant Director]" },
  { id: "continuity-lead", label: "Continuity Lead", marker: "[Continuity Lead]" },
] as const;

export type PipelineStageId = (typeof PIPELINE_STAGES)[number]["id"];

/** Tool call with status tracking for UI display. */
export interface ToolCall {
  id: string;
  name: string;
  args: Record<string, unknown>;
  result?: string;
  status: "pending" | "completed" | "error" | "interrupted";
}

/** Sub-agent spawned via "task" tool call. */
export interface SubAgent {
  id: string;
  name: string;
  subAgentName: string;
  input: Record<string, unknown>;
  output?: Record<string, unknown>;
  status: "pending" | "active" | "completed" | "error";
}

/** Todo item tracked by agent via write_todos tool. */
export interface TodoItem {
  id: string;
  content: string;
  status: "pending" | "in_progress" | "completed";
  updatedAt?: Date;
}

/** File tracked in agent workspace state. */
export interface FileItem {
  path: string;
  content: string;
}

/** Message shape returned by the paginated backend endpoint. */
export interface PaginatedMessage {
  id: string;
  type: "human" | "ai" | "system" | "tool";
  content: string | Array<Record<string, unknown>>;
  additional_kwargs?: Record<string, unknown>;
  tool_calls?: Array<{ name: string; args?: Record<string, unknown>; id?: string }>;
  name?: string;
}

/** Response shape from GET /api/v2/threads/{threadId}/messages */
export interface PaginatedMessagesResponse {
  messages: PaginatedMessage[];
  total: number;
  has_more: boolean;
  next_cursor: string | null;
}

/** Extract displayable text from sub-agent input/output objects. */
export function extractSubAgentContent(data: unknown): string {
  if (typeof data === "string") return data;
  if (data && typeof data === "object") {
    const obj = data as Record<string, unknown>;
    if (typeof obj.description === "string") return obj.description;
    if (typeof obj.prompt === "string") return obj.prompt;
    if (typeof obj.result === "string") return obj.result;
    return JSON.stringify(data, null, 2);
  }
  return JSON.stringify(data, null, 2);
}
