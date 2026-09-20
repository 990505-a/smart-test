import type { ComponentType } from "react";
import { Bug, CodeXml, Gamepad2, Globe, Sparkles } from "lucide-react";

export type AgentKey = "general" | "testcase" | "unity" | "webui" | "codebase";

export interface AgentConfig {
  key: string;
  label: string;
  graphKey: string;
  /** 一句话说明这个 graph 挂载了哪些工具/技能 */
  description: string;
}

export const AGENT_CONFIG: Record<AgentKey, AgentConfig> = {
  // 对话页唯一的智能体。专项能力（用例生成 / Unity / Web-UI）全挂在它的工具面上，
  // 由它自己判断该用哪一类 —— 用户不再需要先选模式。
  general: {
    key: "general",
    label: "通用测试助手",
    graphKey: "smart_test_agent",
    description: "一个入口：需求分析、用例设计与入库、Unity / Web-UI 自动化，按任务自动选能力。",
  },
  // 以下三个是**历史会话的兼容 graph**：早先每个能力是独立模式，会话里记着自己的
  // graph 名。新会话一律用 general；这三个只为让老会话还能续跑而保留。
  testcase: {
    key: "testcase",
    label: "用例生成（旧）",
    graphKey: "testcase_agent",
    description: "历史模式：只挂用例生成能力。新会话请用「通用测试助手」。",
  },
  unity: {
    key: "unity",
    label: "Unity 自动化（旧）",
    graphKey: "unity_agent",
    description: "历史模式：只挂 Unity 能力。新会话请用「通用测试助手」。",
  },
  webui: {
    key: "webui",
    label: "Web-UI 自动化（旧）",
    graphKey: "webui_agent",
    description: "历史模式：只挂 Web-UI 能力。新会话请用「通用测试助手」。",
  },
  // codebase_agent 现在只被无头「增量影响分析」使用（页面内那个 AI 分析 Tab
  // 2026-09 已删除，交互式代码问答统一走对话页的「代码图谱仓库」选择器 + 通用智能体）。
  // 留在 AGENT_CONFIG 是为了让历史会话、测评数据集等共用同一份 graphKey。
  codebase: {
    key: "codebase",
    label: "代码分析",
    graphKey: "codebase_agent",
    description: "代码图谱里的代码问答：功能定位、调用链、影响面；图谱优先，缺失时降级文件检索。",
  },
};

/** 对话页默认（也是新会话唯一）使用的智能体。 */
export const DEFAULT_AGENT_KEY: AgentKey = "general";

/** 由 graph 名反查配置键；未知 graph（例如已被移除的模式）返回 undefined。 */
export function agentKeyForGraph(graphKey?: string): AgentKey | undefined {
  if (!graphKey) return undefined;
  return (Object.keys(AGENT_CONFIG) as AgentKey[]).find(
    (key) => AGENT_CONFIG[key].graphKey === graphKey,
  );
}

/** 智能体图标（会话列表徽标等共用） */
export const AGENT_ICONS: Record<AgentKey, ComponentType<{ className?: string }>> = {
  general: Sparkles,
  testcase: Bug,
  unity: Gamepad2,
  webui: Globe,
  codebase: CodeXml,
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
    /** Absolute path where the file is saved. The agent reads it with read_file. */
    workspacePath?: string;
    /** Absolute path to the extracted text file. */
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
