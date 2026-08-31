"use client";

// EverOS 文件化记忆 hooks（2026-08-31 记忆系统重构）
// 存储 = EverOS 管理的 Markdown 文件；检索 = EverOS 服务（hybrid/keyword 自动）。

import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { mutate } from "swr";
import { apiClient } from "@/lib/api-client";

// === Types ===

export interface MemoryFileMeta {
  path: string;
  size: number;
  modified_at: string;
  track: "user" | "agent";
}

export interface MemoryStatus {
  up: boolean;
  error?: string;
  version?: string;
  capabilities?: { llm?: boolean; embed?: boolean; rerank?: boolean };
  disabled_features?: string[];
  root?: string;
  files?: number;
}

export interface MemoryHit {
  id: string | null;
  subject: string;
  summary: string | null;
  timestamp: string | null;
  score: number | null;
}

// === SWR Hooks ===

/** EverOS 服务状态（版本/能力/embedding 是否解锁/文件数） */
export function useMemoryStatus() {
  return useSWR("/memories/status", () =>
    apiClient.get<MemoryStatus>("/memories/status").then((r) => r.data));
}

/** 记忆文件列表（MD 单一事实源） */
export function useMemoryFiles() {
  return useSWR("/memories/files", () =>
    apiClient.get<MemoryFileMeta[]>("/memories/files").then((r) => r.data));
}

/** 读取单个记忆文件内容 */
export function useReadMemoryFile(path: string | null) {
  return useSWR(path ? ["/memories/file", path] : null, ([, p]) =>
    apiClient
      .get<{ path: string; content: string }>("/memories/file", { path: p })
      .then((r) => r.data));
}

/** 保存记忆文件（人工编辑由 EverOS watcher 自动回灌索引） */
export function useWriteMemoryFile() {
  return useSWRMutation(
    "/memories/files",
    async (_url: string, { arg }: { arg: { path: string; content: string } }) => {
      const result = await apiClient.put<{ path: string; saved: boolean }>(
        "/memories/file", arg);
      mutate("/memories/files");
      mutate(["/memories/file", arg.path]);
      return result;
    }
  );
}

/** 删除记忆文件 */
export function useDeleteMemoryFile() {
  return useSWRMutation(
    "/memories/files",
    async (_url: string, { arg }: { arg: string }) => {
      const result = await apiClient.delete(
        `/memories/file?path=${encodeURIComponent(arg)}`);
      mutate("/memories/files");
      return result;
    }
  );
}

/** 检索记忆（等价 Agent 的 search_memories 工具） */
export async function searchMemories(query: string, topK = 8): Promise<MemoryHit[]> {
  const result = await apiClient.post<MemoryHit[]>("/memories/search", {
    query,
    top_k: topK,
  });
  return result.data ?? [];
}

/** 手动写入一条长期记忆（等价 Agent 的 save_memory 工具，触发 LLM 蒸馏固化） */
export async function saveMemory(
  key: string,
  content: string,
  category?: string
): Promise<{ key: string; flush_status?: string } | null> {
  const result = await apiClient.post<{ key: string; flush_status?: string }>(
    "/memories/save", { key, content, category });
  mutate("/memories/files");
  return result.data;
}

/** Revalidate all memory SWR caches */
export function revalidateMemories() {
  mutate("/memories/files");
  mutate("/memories/status");
}
