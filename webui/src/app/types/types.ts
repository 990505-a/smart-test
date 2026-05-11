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
}
