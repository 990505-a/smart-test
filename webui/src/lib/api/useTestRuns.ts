"use client";

import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { mutate } from "swr";
import { apiClient } from "@/lib/api-client";
import type { TestRunInfo, TestRunCreate, TestRunUpdate, TestResultInfo, TestResultCreate, PaginatedResponse } from "@/app/types/api";

// List test runs (paginated, optional project filter)
export function useTestRuns(page: number = 1, pageSize: number = 30, projectId?: string) {
  const params: Record<string, string | number> = { p: page, page_size: pageSize };
  if (projectId) params.project_id = projectId;
  return useSWR<PaginatedResponse<TestRunInfo>>(
    ["/test-runs", page, pageSize, projectId],
    ([url]) => apiClient.getPaginated<TestRunInfo>(url, params)
  );
}

// Get single test run
export function useTestRun(id: string | null) {
  return useSWR(
    id ? `/test-runs/${id}` : null,
    (url: string) => apiClient.get<TestRunInfo>(url)
  );
}

// Create test run
export function useCreateTestRun() {
  return useSWRMutation(
    "/test-runs",
    async (url: string, { arg }: { arg: TestRunCreate }) => {
      const result = await apiClient.post<TestRunInfo>(url, arg);
      mutate(key => Array.isArray(key) && key[0] === "/test-runs");
      return result;
    }
  );
}

// Update test run (e.g., change run_state)
export function useUpdateTestRun() {
  return useSWRMutation(
    "/test-runs",
    async (_url: string, { arg }: { arg: { id: string; data: TestRunUpdate } }) => {
      const result = await apiClient.patch<TestRunInfo>(`/test-runs/${arg.id}`, arg.data);
      mutate(key => Array.isArray(key) && key[0] === "/test-runs");
      mutate(`/test-runs/${arg.id}`);
      return result;
    }
  );
}

// Delete test run
export function useDeleteTestRun() {
  return useSWRMutation(
    "/test-runs",
    async (_url: string, { arg }: { arg: string }) => {
      const result = await apiClient.delete(`/test-runs/${arg}`);
      mutate(key => Array.isArray(key) && key[0] === "/test-runs");
      return result;
    }
  );
}

// Add test result to a run
export function useAddTestResult(runId: string | null) {
  return useSWRMutation(
    runId ? `/test-runs/${runId}/results` : null,
    async (url: string, { arg }: { arg: TestResultCreate }) => {
      const result = await apiClient.post<TestResultInfo>(url, arg);
      mutate(key => Array.isArray(key) && key[0] === "/test-runs");
      mutate(`/test-runs/${runId}`);
      return result;
    }
  );
}
