"use client";

import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { mutate } from "swr";
import { apiClient } from "@/lib/api-client";
import type {
  WebFunctionInfo,
  WebSubFunctionInfo,
  WebFunctionCreate,
  WebFunctionUpdate,
  PaginatedResponse,
} from "@/app/types/api";

// ---------------------------------------------------------------------------
// List web functions (paginated, with search and folder_id filters)
// ---------------------------------------------------------------------------
export function useWebFunctions(
  projectId: string | null,
  page: number = 1,
  pageSize: number = 30,
  search?: string,
  folderId?: string,
) {
  const params: Record<string, string | number> = { p: page, page_size: pageSize };
  if (search) params.search = search;
  if (folderId) params.folder_id = folderId;

  return useSWR<PaginatedResponse<WebFunctionInfo>>(
    projectId ? [`/projects/${projectId}/web-functions`, page, pageSize, search, folderId] : null,
    ([url]) => apiClient.getPaginated<WebFunctionInfo>(url, params),
  );
}

// ---------------------------------------------------------------------------
// Get single web function
// ---------------------------------------------------------------------------
export function useWebFunction(projectId: string | null, functionId: string | null) {
  return useSWR(
    projectId && functionId ? `/projects/${projectId}/web-functions/${functionId}` : null,
    (url: string) => apiClient.get<WebFunctionInfo>(url),
  );
}

// ---------------------------------------------------------------------------
// List sub-functions for a web function
// ---------------------------------------------------------------------------
export function useSubFunctions(
  projectId: string | null,
  functionId: string | null,
  page: number = 1,
  pageSize: number = 50,
) {
  const params: Record<string, string | number> = { p: page, page_size: pageSize };

  return useSWR<PaginatedResponse<WebSubFunctionInfo>>(
    projectId && functionId
      ? [`/projects/${projectId}/web-functions/${functionId}/sub-functions`, page, pageSize]
      : null,
    ([url]) => apiClient.getPaginated<WebSubFunctionInfo>(url, params),
  );
}

// ---------------------------------------------------------------------------
// Create web function
// ---------------------------------------------------------------------------
export function useCreateWebFunction(projectId: string | null) {
  return useSWRMutation(
    projectId ? `/projects/${projectId}/web-functions` : null,
    async (url: string, { arg }: { arg: WebFunctionCreate }) => {
      const result = await apiClient.post<WebFunctionInfo>(url, arg);
      mutate(
        (key) =>
          Array.isArray(key) && key[0] === `/projects/${projectId}/web-functions`,
      );
      return result;
    },
  );
}

// ---------------------------------------------------------------------------
// Update web function
// ---------------------------------------------------------------------------
export function useUpdateWebFunction(projectId: string | null) {
  return useSWRMutation(
    projectId ? `/projects/${projectId}/web-functions` : null,
    async (
      _url: string,
      { arg }: { arg: { functionId: string; data: WebFunctionUpdate } },
    ) => {
      const result = await apiClient.patch<WebFunctionInfo>(
        `/projects/${projectId}/web-functions/${arg.functionId}`,
        arg.data,
      );
      mutate(
        (key) =>
          Array.isArray(key) && key[0] === `/projects/${projectId}/web-functions`,
      );
      mutate(`/projects/${projectId}/web-functions/${arg.functionId}`);
      return result;
    },
  );
}

// ---------------------------------------------------------------------------
// Delete web function
// ---------------------------------------------------------------------------
export function useDeleteWebFunction(projectId: string | null) {
  return useSWRMutation(
    projectId ? `/projects/${projectId}/web-functions` : null,
    async (_url: string, { arg }: { arg: string }) => {
      const result = await apiClient.delete(
        `/projects/${projectId}/web-functions/${arg}`,
      );
      mutate(
        (key) =>
          Array.isArray(key) && key[0] === `/projects/${projectId}/web-functions`,
      );
      return result;
    },
  );
}

// ---------------------------------------------------------------------------
// Create sub-function
// ---------------------------------------------------------------------------
export function useCreateSubFunction(
  projectId: string | null,
  functionId: string | null,
) {
  return useSWRMutation(
    projectId && functionId
      ? `/projects/${projectId}/web-functions/${functionId}/sub-functions`
      : null,
    async (url: string, { arg }: { arg: Partial<WebSubFunctionInfo> }) => {
      const result = await apiClient.post<WebSubFunctionInfo>(url, arg);
      // Invalidate sub-functions list and parent function detail
      mutate(
        (key) =>
          Array.isArray(key) &&
          key[0] === `/projects/${projectId}/web-functions/${functionId}/sub-functions`,
      );
      mutate(`/projects/${projectId}/web-functions/${functionId}`);
      return result;
    },
  );
}
