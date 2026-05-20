"use client";

import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { mutate } from "swr";
import { apiClient } from "@/lib/api-client";
import type { WorkspaceInfo, WorkspaceCreate } from "@/app/types/api";

/** Revalidation key for workspace SWR caches. */
const WORKSPACE_KEY = "/workspaces";

/** List all workspaces (no pagination -- workspace lists are small). */
export function useWorkspaces() {
  return useSWR<{ success: boolean; data: WorkspaceInfo[] }>(
    WORKSPACE_KEY,
    (url: string) => apiClient.get<WorkspaceInfo[]>(url)
  );
}

/** Create a new workspace. Revalidates the workspace list on success. */
export function useCreateWorkspace() {
  return useSWRMutation(
    WORKSPACE_KEY,
    async (url: string, { arg }: { arg: WorkspaceCreate }) => {
      const result = await apiClient.post<WorkspaceInfo>(url, arg);
      mutate(WORKSPACE_KEY);
      return result;
    }
  );
}

/** Delete a workspace by slug. Revalidates the workspace list on success. */
export function useDeleteWorkspace() {
  return useSWRMutation(
    WORKSPACE_KEY,
    async (_url: string, { arg }: { arg: string }) => {
      const result = await apiClient.delete(`/workspaces/${arg}`);
      mutate(WORKSPACE_KEY);
      return result;
    }
  );
}

/** Revalidate all workspace SWR caches. */
export function revalidateWorkspaces() {
  mutate(WORKSPACE_KEY);
}
