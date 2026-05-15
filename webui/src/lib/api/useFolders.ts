"use client";

import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { mutate } from "swr";
import { apiClient } from "@/lib/api-client";
import type { FolderInfo, FolderTreeNode, FolderCreate, FolderUpdate } from "@/app/types/api";

// List folders flat
export function useFolders(projectId: string | null) {
  return useSWR(
    projectId ? ["/folders", projectId] : null,
    ([url, pid]) => apiClient.getPaginated<FolderInfo>(url, { project_id: pid })
  );
}

// Get folder tree
export function useFolderTree(projectId: string | null) {
  return useSWR(
    projectId ? ["/folders/tree", projectId] : null,
    ([url, pid]) => apiClient.get<FolderTreeNode[]>(url, { project_id: pid })
  );
}

// Create folder
export function useCreateFolder() {
  return useSWRMutation(
    "/folders",
    async (url: string, { arg }: { arg: FolderCreate }) => {
      const result = await apiClient.post<FolderInfo>(url, arg);
      mutate(key => Array.isArray(key) && key[0] === "/folders");
      mutate(key => Array.isArray(key) && key[0] === "/folders/tree");
      return result;
    }
  );
}

// Update folder (for drag-drop reorder: update parent_id or reorder)
export function useUpdateFolder() {
  return useSWRMutation(
    "/folders",
    async (_url: string, { arg }: { arg: { id: string; data: FolderUpdate } }) => {
      const result = await apiClient.patch<FolderInfo>(`/folders/${arg.id}`, arg.data);
      mutate(key => Array.isArray(key) && key[0] === "/folders/tree");
      return result;
    }
  );
}

// Delete folder
export function useDeleteFolder() {
  return useSWRMutation(
    "/folders",
    async (_url: string, { arg }: { arg: string }) => {
      const result = await apiClient.delete(`/folders/${arg}`);
      mutate(key => Array.isArray(key) && key[0] === "/folders/tree");
      mutate(key => Array.isArray(key) && key[0] === "/folders");
      return result;
    }
  );
}
