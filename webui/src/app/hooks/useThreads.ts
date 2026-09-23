"use client";

import useSWRInfinite from "swr/infinite";
import { getFastapiUrl } from "@/lib/config";

export interface ThreadItem {
  id: string;
  updatedAt: Date;
  title: string;
  description: string;
  /** LangGraph assistant id（这个会话用哪个智能体模式）；旧会话可能为空 */
  agent: string;
  /** 会话级设置快照（权限/思考强度/模型预设/智能体/仓库）；旧会话可能为空 */
  config?: ThreadConversationConfig | null;
}

/** thread_infos.config 的键（与 run configurable 对齐）。 */
export interface ThreadConversationConfig {
  permission_mode?: string;
  llm_reasoning_effort?: string;
  model_preset?: string;
  agent_id?: string;
  repo_id?: string;
}

const DEFAULT_PAGE_SIZE = 20;

async function fetcher(url: string) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch threads: ${res.status}`);
  return res.json();
}

export function useThreads() {
  return useSWRInfinite(
    (pageIndex: number, previousPageData: { threads: ThreadItem[] } | null) => {
      if (previousPageData && previousPageData.threads.length === 0) {
        return null;
      }

      const apiBase = getFastapiUrl();
      // codebase_agent 的会话（无头影响分析 + 已删除的「AI 分析」Tab 留下的历史
      // 会话）不属于对话页，交给后端排除（前端过滤会打乱分页与 total）。
      return `${apiBase}/api/v2/threads?limit=${DEFAULT_PAGE_SIZE}&offset=${pageIndex * DEFAULT_PAGE_SIZE}&exclude_agent=codebase_agent`;
    },
    async (url: string) => {
      const data = await fetcher(url);
      return {
        threads: (data.threads || []).map(
          (t: {
            thread_id: string;
            title: string;
            description: string;
            updated_at: string;
            /** 后端 GET /api/v2/threads 会带上会话的模式；旧数据可能为空 */
            agent?: string;
            /** 会话级设置快照；旧会话可能为空 */
            config?: ThreadConversationConfig | null;
          }) => ({
            id: t.thread_id,
            updatedAt: new Date(t.updated_at),
            title: t.title || "无标题对话",
            description: t.description || "",
            // 必须透传给 ThreadList：会话列表的模式徽标 + 点开会话时切回模式
            agent: t.agent || "",
            config: t.config ?? null,
          })
        ),
        total: data.total || 0,
      };
    },
    {
      revalidateFirstPage: true,
    }
  );
}
