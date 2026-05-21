"use client";

import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { mutate } from "swr";
import { apiClient } from "@/lib/api-client";
import type {
  WebTestInfo,
  WebTestCreate,
  WebTestUpdate,
  WebTestRunInfo,
  WebTestResultInfo,
  PaginatedResponse,
} from "@/app/types/api";

// ---------------------------------------------------------------------------
// List web tests (paginated, with function/sub-function/search filters)
// ---------------------------------------------------------------------------
export function useWebTests(
  projectId: string | null,
  page: number = 1,
  pageSize: number = 30,
  functionId?: string | null,
  subFunctionId?: string | null,
  search?: string,
) {
  const params: Record<string, string | number> = { p: page, page_size: pageSize };
  if (functionId) params.function_id = functionId;
  if (subFunctionId) params.sub_function_id = subFunctionId;
  if (search) params.search = search;

  return useSWR<PaginatedResponse<WebTestInfo>>(
    projectId
      ? [`/projects/${projectId}/web-tests`, page, pageSize, functionId, subFunctionId, search]
      : null,
    ([url]) => apiClient.getPaginated<WebTestInfo>(url, params),
  );
}

// ---------------------------------------------------------------------------
// Get single web test
// ---------------------------------------------------------------------------
export function useWebTest(projectId: string | null, testId: string | null) {
  return useSWR(
    projectId && testId ? `/projects/${projectId}/web-tests/${testId}` : null,
    (url: string) => apiClient.get<WebTestInfo>(url),
  );
}

// ---------------------------------------------------------------------------
// Create web test
// ---------------------------------------------------------------------------
export function useCreateWebTest(projectId: string | null) {
  return useSWRMutation(
    projectId ? `/projects/${projectId}/web-tests` : null,
    async (url: string, { arg }: { arg: WebTestCreate }) => {
      const result = await apiClient.post<WebTestInfo>(url, arg);
      mutate(
        (key) =>
          Array.isArray(key) && key[0] === `/projects/${projectId}/web-tests`,
      );
      return result;
    },
  );
}

// ---------------------------------------------------------------------------
// Update web test
// ---------------------------------------------------------------------------
export function useUpdateWebTest(projectId: string | null) {
  return useSWRMutation(
    projectId ? `/projects/${projectId}/web-tests` : null,
    async (
      _url: string,
      { arg }: { arg: { testId: string; data: WebTestUpdate } },
    ) => {
      const result = await apiClient.patch<WebTestInfo>(
        `/projects/${projectId}/web-tests/${arg.testId}`,
        arg.data,
      );
      mutate(
        (key) =>
          Array.isArray(key) && key[0] === `/projects/${projectId}/web-tests`,
      );
      mutate(`/projects/${projectId}/web-tests/${arg.testId}`);
      return result;
    },
  );
}

// ---------------------------------------------------------------------------
// Delete web test
// ---------------------------------------------------------------------------
export function useDeleteWebTest(projectId: string | null) {
  return useSWRMutation(
    projectId ? `/projects/${projectId}/web-tests` : null,
    async (_url: string, { arg }: { arg: string }) => {
      const result = await apiClient.delete(
        `/projects/${projectId}/web-tests/${arg}`,
      );
      mutate(
        (key) =>
          Array.isArray(key) && key[0] === `/projects/${projectId}/web-tests`,
      );
      return result;
    },
  );
}

// ---------------------------------------------------------------------------
// List test runs for a web test
// ---------------------------------------------------------------------------
export function useWebTestRuns(
  projectId: string | null,
  testId: string | null,
  limit: number = 20,
) {
  return useSWR(
    projectId && testId
      ? [`/projects/${projectId}/web-tests/${testId}/runs`, limit]
      : null,
    ([url]) =>
      apiClient.get<WebTestRunInfo[]>(
        `${url}?limit=${limit}`,
      ),
  );
}

// ---------------------------------------------------------------------------
// Get single test run
// ---------------------------------------------------------------------------
export function useWebTestRun(
  projectId: string | null,
  testId: string | null,
  runId: string | null,
) {
  return useSWR(
    projectId && testId && runId
      ? `/projects/${projectId}/web-tests/${testId}/runs/${runId}`
      : null,
    (url: string) => apiClient.get<WebTestRunInfo>(url),
  );
}

// ---------------------------------------------------------------------------
// Get test results for a run
// ---------------------------------------------------------------------------
export function useWebTestResults(
  projectId: string | null,
  testId: string | null,
  runId: string | null,
) {
  return useSWR(
    projectId && testId && runId
      ? `/projects/${projectId}/web-tests/${testId}/runs/${runId}/results`
      : null,
    (url: string) => apiClient.get<WebTestResultInfo[]>(url),
  );
}

// ---------------------------------------------------------------------------
// Trigger web test execution
// ---------------------------------------------------------------------------
export async function triggerWebTestExecution(
  projectId: string,
  testId: string,
  executionConfig?: Record<string, unknown>,
) {
  const body = executionConfig ? { execution_config: executionConfig } : {};
  return apiClient.post<WebTestRunInfo>(
    `/projects/${projectId}/web-tests/${testId}/run`,
    body,
  );
}
