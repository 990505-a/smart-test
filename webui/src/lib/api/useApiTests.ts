"use client";

import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { mutate } from "swr";
import { apiClient } from "@/lib/api-client";
import type {
  APITestInfo,
  APITestCreate,
  APITestUpdate,
  APITestRunInfo,
  APITestResultInfo,
  PaginatedResponse,
} from "@/app/types/api";

// ---------------------------------------------------------------------------
// List API tests (paginated, with search and script_format filters)
// ---------------------------------------------------------------------------
export function useApiTests(
  projectId: string | null,
  page: number = 1,
  pageSize: number = 30,
  search?: string,
  scriptFormat?: string,
) {
  const params: Record<string, string | number> = { p: page, page_size: pageSize };
  if (search) params.search = search;
  if (scriptFormat) params.script_format = scriptFormat;

  return useSWR<PaginatedResponse<APITestInfo>>(
    projectId ? [`/projects/${projectId}/api-tests`, page, pageSize, search, scriptFormat] : null,
    ([url]) => apiClient.getPaginated<APITestInfo>(url, params),
  );
}

// ---------------------------------------------------------------------------
// Get single API test
// ---------------------------------------------------------------------------
export function useApiTest(projectId: string | null, testId: string | null) {
  return useSWR(
    projectId && testId ? `/projects/${projectId}/api-tests/${testId}` : null,
    (url: string) => apiClient.get<APITestInfo>(url),
  );
}

// ---------------------------------------------------------------------------
// List test runs for an API test
// ---------------------------------------------------------------------------
export function useApiTestRuns(
  projectId: string | null,
  testId: string | null,
  limit: number = 20,
) {
  return useSWR(
    projectId && testId ? `/projects/${projectId}/api-tests/${testId}/runs?limit=${limit}` : null,
    (url: string) => apiClient.get<APITestRunInfo[]>(url),
  );
}

// ---------------------------------------------------------------------------
// Get test results for a specific run
// ---------------------------------------------------------------------------
export function useApiTestResults(
  projectId: string | null,
  testId: string | null,
  runId: string | null,
) {
  return useSWR(
    projectId && testId && runId
      ? `/projects/${projectId}/api-tests/${testId}/runs/${runId}/results`
      : null,
    (url: string) => apiClient.get<APITestResultInfo[]>(url),
  );
}

// ---------------------------------------------------------------------------
// Create API test
// ---------------------------------------------------------------------------
export function useCreateApiTest(projectId: string | null) {
  return useSWRMutation(
    projectId ? `/projects/${projectId}/api-tests` : null,
    async (url: string, { arg }: { arg: APITestCreate }) => {
      const result = await apiClient.post<APITestInfo>(url, arg);
      mutate(
        (key) =>
          Array.isArray(key) && key[0] === `/projects/${projectId}/api-tests`,
      );
      return result;
    },
  );
}

// ---------------------------------------------------------------------------
// Update API test
// ---------------------------------------------------------------------------
export function useUpdateApiTest(projectId: string | null) {
  return useSWRMutation(
    projectId ? `/projects/${projectId}/api-tests` : null,
    async (
      _url: string,
      { arg }: { arg: { testId: string; data: APITestUpdate } },
    ) => {
      const result = await apiClient.patch<APITestInfo>(
        `/projects/${projectId}/api-tests/${arg.testId}`,
        arg.data,
      );
      mutate(
        (key) =>
          Array.isArray(key) && key[0] === `/projects/${projectId}/api-tests`,
      );
      mutate(`/projects/${projectId}/api-tests/${arg.testId}`);
      return result;
    },
  );
}

// ---------------------------------------------------------------------------
// Delete API test
// ---------------------------------------------------------------------------
export function useDeleteApiTest(projectId: string | null) {
  return useSWRMutation(
    projectId ? `/projects/${projectId}/api-tests` : null,
    async (_url: string, { arg }: { arg: string }) => {
      const result = await apiClient.delete(
        `/projects/${projectId}/api-tests/${arg}`,
      );
      mutate(
        (key) =>
          Array.isArray(key) && key[0] === `/projects/${projectId}/api-tests`,
      );
      return result;
    },
  );
}

// ---------------------------------------------------------------------------
// Upload script content
// ---------------------------------------------------------------------------
export async function uploadScript(
  projectId: string,
  testId: string,
  content: string,
  scriptFormat?: string,
) {
  const body: Record<string, unknown> = { content };
  if (scriptFormat) body.script_format = scriptFormat;
  const result = await apiClient.post(
    `/projects/${projectId}/api-tests/${testId}/script`,
    // PUT endpoint for update -- apiClient doesn't have put, use patch
    // Actually the backend uses PUT for script. We need a raw call.
    body,
  );
  // Use fetch directly for PUT since apiClient doesn't have put method
  const baseUrl =
    typeof window !== "undefined"
      ? JSON.parse(localStorage.getItem("st-config") || "{}")?.fastapiUrl ||
        "http://localhost:8000"
      : "http://localhost:8000";
  const res = await fetch(`${baseUrl}/api/v2/projects/${projectId}/api-tests/${testId}/script`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ message: `HTTP ${res.status}` }));
    throw new Error(err.message || err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Trigger test execution
// ---------------------------------------------------------------------------
export async function triggerExecution(
  projectId: string,
  testId: string,
  executionConfig?: Record<string, unknown>,
) {
  const body = executionConfig ? { execution_config: executionConfig } : {};
  return apiClient.post<APITestRunInfo>(
    `/projects/${projectId}/api-tests/${testId}/run`,
    body,
  );
}

// ---------------------------------------------------------------------------
// Upload schema file (multipart form, uses raw fetch)
// ---------------------------------------------------------------------------
export async function uploadSchemaFile(
  projectId: string,
  file: File,
) {
  const baseUrl =
    typeof window !== "undefined"
      ? JSON.parse(localStorage.getItem("st-config") || "{}")?.fastapiUrl ||
        "http://localhost:8000"
      : "http://localhost:8000";

  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(
    `${baseUrl}/api/v2/projects/${projectId}/api-tests/upload-schema`,
    {
      method: "POST",
      headers: { "X-Space-Id": "default" },
      body: formData,
    },
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({ message: `HTTP ${res.status}` }));
    throw new Error(err.message || err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}
