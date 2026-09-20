"use client";

/**
 * Agent 记忆（harness 风格 Markdown 记忆模块）的 SWR hooks。
 *
 * 记忆 = workspace/<space>/memory/ 下的一组 .md（AGENTS.md / MEMORY.md /
 * USER.md / failures.md / PROJECT.md / DECISIONS.md + 用户自建）。文件是唯一
 * 事实源：页面读写的都是文件本身，每个模块可以单独启用/停用。
 */

import useSWR, { mutate as globalMutate } from "swr";
import { apiClient } from "@/lib/api-client";

const fetcher = <T,>(path: string) => apiClient.get<T>(path).then((r) => r.data);
const MEMORY_KEY_PREFIX = "/memories";

export interface MemoryModule {
  id: string;
  file: string;
  label: string;
  description: string;
  enabled: boolean;
  builtin: boolean;
  chars: number;
  updated_at: number | null;
}

export interface MemoryModuleDetail extends MemoryModule {
  content: string;
}

export interface MemoryStatus {
  root: string;
  enabled_modules: number;
  total_modules: number;
  chars: number;
}

export interface MemoryHit {
  module_id: string;
  file: string;
  label: string;
  line: number;
  text: string;
  score: number;
}

export function useMemoryModules() {
  return useSWR("/memories/modules", () => fetcher<MemoryModule[]>("/memories/modules"));
}

export function useMemoryStatus() {
  return useSWR("/memories/status", () => fetcher<MemoryStatus>("/memories/status"));
}

export function useMemoryModule(id: string | null) {
  const key = id ? `/memories/modules/${encodeURIComponent(id)}` : null;
  return useSWR(key, () => fetcher<MemoryModuleDetail>(key as string), {
    revalidateOnFocus: false,
  });
}

/** 任何写入后刷新所有 /memories 的缓存（列表 + 详情 + 状态）。仅本模块内部使用 */
function revalidateMemories() {
  void globalMutate(
    (key) => typeof key === "string" && key.startsWith(MEMORY_KEY_PREFIX),
    undefined,
    { revalidate: true },
  );
}

export async function saveMemoryModule(id: string, content: string) {
  const response = await apiClient.put<MemoryModule>(
    `/memories/modules/${encodeURIComponent(id)}`, { content });
  revalidateMemories();
  return response.data;
}

export async function setMemoryModuleEnabled(id: string, enabled: boolean) {
  const response = await apiClient.patch<MemoryModule>(
    `/memories/modules/${encodeURIComponent(id)}`, { enabled });
  revalidateMemories();
  return response.data;
}

export async function createMemoryModule(body: {
  label: string; file?: string; content?: string; description?: string;
}) {
  const response = await apiClient.post<MemoryModule>("/memories/modules", body);
  revalidateMemories();
  return response.data;
}

export async function deleteMemoryModule(id: string) {
  await apiClient.delete(`/memories/modules/${encodeURIComponent(id)}`);
  revalidateMemories();
}

export async function appendMemoryEntry(body: {
  module: string; content: string; category?: string;
}) {
  const response = await apiClient.post<MemoryModule>("/memories/entries", body);
  revalidateMemories();
  return response.data;
}

export async function searchMemories(query: string, limit = 8) {
  const response = await apiClient.post<{ count: number; hits: MemoryHit[] }>(
    "/memories/search", { query, limit });
  return response.data;
}

/**
 * 记忆总闸（设置页那个 `MEMORY_ENABLED`）。
 *
 * 它和"模块开关"不是一回事，所以没有随总开关一起删掉、而是搬到了本页：
 *  - 模块全关：官方模板**照旧注入**（正文是"No memory loaded"），模型仍然知道
 *    "我有记忆、可以用 edit_file 写记忆"——它照样会写；
 *  - 总闸关掉：`sources` 为空 **且** 模板不贴，模型完全不知道记忆这回事。
 * 所以排障（怀疑记忆在带偏行为、想让它彻底闭嘴）只有这个闸能做到。
 *
 * 读写走平台设置 API（`memory_enabled` 是 PLATFORM_KEYS 里的一项），与设置页
 * 当年的写法一致：存 DB + 同步 .env。
 */
export function useMemoryGlobalSwitch() {
  return useSWR("/settings/platform?memory-gate", () =>
    fetcher<Record<string, string | null>>("/settings/platform"));
}

export async function setMemoryGlobalSwitch(enabled: boolean) {
  const res = await apiClient.put("/settings/platform", {
    values: { memory_enabled: enabled ? "true" : "false" },
  });
  await globalMutate("/settings/platform?memory-gate");
  revalidateMemories();
  return res.data;
}
