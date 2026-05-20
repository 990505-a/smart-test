export type AgentKey = "testcase" | "web" | "api";

export interface AgentConfig {
  key: string;
  label: string;
  graphKey: string;
}

export const AGENT_CONFIG: Record<AgentKey, AgentConfig> = {
  testcase: { key: "testcase", label: "用例生成", graphKey: "testcase_agent" },
  web: { key: "web", label: "Web自动化", graphKey: "web_agent" },
  api: { key: "api", label: "API自动化", graphKey: "api_agent" },
};

export interface ContentBlock {
  type: "image" | "file";
  mimeType: string;
  data: string;
  metadata?: { name?: string; filename?: string };
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

/** Workspace identifier -- the slug string from the API (e.g., "default", "project-alpha"). */
export type WorkspaceId = string;

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
