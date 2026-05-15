"use client";

import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { mutate } from "swr";
import { apiClient } from "@/lib/api-client";
import type { TestCaseInfo, TestCaseCreate, TestCaseUpdate, PaginatedResponse } from "@/app/types/api";

// List test cases (paginated, optional project_id and folder_id filters)
export function useTestCases(page: number = 1, pageSize: number = 30, projectId?: string, folderId?: string) {
  const params: Record<string, string | number> = { p: page, page_size: pageSize };
  if (projectId) params.project_id = projectId;
  if (folderId) params.folder_id = folderId;
  return useSWR<PaginatedResponse<TestCaseInfo>>(
    ["/test-cases", page, pageSize, projectId, folderId],
    ([url]) => apiClient.getPaginated<TestCaseInfo>(url, params)
  );
}

// Get single test case by ID
export function useTestCase(id: string | null) {
  return useSWR(
    id ? `/test-cases/${id}` : null,
    (url: string) => apiClient.get<TestCaseInfo>(url)
  );
}

// Create test case
export function useCreateTestCase() {
  return useSWRMutation(
    "/test-cases",
    async (url: string, { arg }: { arg: TestCaseCreate }) => {
      const result = await apiClient.post<TestCaseInfo>(url, arg);
      mutate(key => Array.isArray(key) && key[0] === "/test-cases");
      return result;
    }
  );
}

// Update test case
export function useUpdateTestCase() {
  return useSWRMutation(
    "/test-cases",
    async (_url: string, { arg }: { arg: { id: string; data: TestCaseUpdate } }) => {
      const result = await apiClient.patch<TestCaseInfo>(`/test-cases/${arg.id}`, arg.data);
      mutate(key => Array.isArray(key) && key[0] === "/test-cases");
      mutate(`/test-cases/${arg.id}`);
      return result;
    }
  );
}

// Delete test case
export function useDeleteTestCase() {
  return useSWRMutation(
    "/test-cases",
    async (_url: string, { arg }: { arg: string }) => {
      const result = await apiClient.delete(`/test-cases/${arg}`);
      mutate(key => Array.isArray(key) && key[0] === "/test-cases");
      return result;
    }
  );
}

/** Revalidate all test case SWR caches. Call after Agent auto-saves. */
export function revalidateTestCases() {
  mutate(key => Array.isArray(key) && key[0] === "/test-cases");
}
