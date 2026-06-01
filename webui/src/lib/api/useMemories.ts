"use client";

import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { mutate } from "swr";
import { apiClient } from "@/lib/api-client";
import type { PaginatedResponse } from "@/app/types/api";

// === Memory Types ===

export interface MemoryInfo {
  id: string;
  space_id: string;
  key: string;
  content: string;
  category: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface MemoryCreate {
  key: string;
  content: string;
  category?: string;
}

export interface MemoryUpdate {
  key?: string;
  content?: string;
  category?: string;
}

// === SWR Hooks ===

/** List memories with pagination, optional category and search filters */
export function useMemories(
  page: number = 1,
  pageSize: number = 30,
  category?: string,
  search?: string
) {
  const params: Record<string, string | number> = { p: page, page_size: pageSize };
  if (category) params.category = category;
  if (search) params.search = search;

  return useSWR<PaginatedResponse<MemoryInfo>>(
    ["/memories", page, pageSize, category ?? "", search ?? ""],
    ([url]) => apiClient.getPaginated<MemoryInfo>(url, params)
  );
}

/** Create a new memory */
export function useCreateMemory() {
  return useSWRMutation(
    "/memories",
    async (url: string, { arg }: { arg: MemoryCreate }) => {
      const result = await apiClient.post<MemoryInfo>(url, arg);
      mutate(key => Array.isArray(key) && key[0] === "/memories");
      return result;
    }
  );
}

/** Update an existing memory */
export function useUpdateMemory() {
  return useSWRMutation(
    "/memories",
    async (_url: string, { arg }: { arg: { id: string; data: MemoryUpdate } }) => {
      const result = await apiClient.patch<MemoryInfo>(`/memories/${arg.id}`, arg.data);
      mutate(key => Array.isArray(key) && key[0] === "/memories");
      mutate(`/memories/${arg.id}`);
      return result;
    }
  );
}

/** Delete a memory */
export function useDeleteMemory() {
  return useSWRMutation(
    "/memories",
    async (_url: string, { arg }: { arg: string }) => {
      const result = await apiClient.delete(`/memories/${arg}`);
      mutate(key => Array.isArray(key) && key[0] === "/memories");
      return result;
    }
  );
}

/** Revalidate all memory SWR caches */
export function revalidateMemories() {
  mutate(key => Array.isArray(key) && key[0] === "/memories");
}
