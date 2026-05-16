"use client";

import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { mutate } from "swr";
import { apiClient } from "@/lib/api-client";
import type {
  ScenarioInfo,
  ScenarioStepInfo,
  ScenarioRunInfo,
  PaginatedResponse,
} from "@/app/types/api";

// ---------------------------------------------------------------------------
// List scenarios (paginated, optional project_id and status filters)
// ---------------------------------------------------------------------------
export function useScenarios(
  page: number = 1,
  pageSize: number = 30,
  projectId?: string,
  status?: string,
) {
  const params: Record<string, string | number> = { p: page, page_size: pageSize };
  if (projectId) params.project_id = projectId;
  if (status) params.status = status;

  return useSWR<PaginatedResponse<ScenarioInfo>>(
    ["/scenarios", page, pageSize, projectId, status],
    ([url]) => apiClient.getPaginated<ScenarioInfo>(url, params),
  );
}

// ---------------------------------------------------------------------------
// Get single scenario with steps
// ---------------------------------------------------------------------------
export function useScenario(scenarioId: string | null) {
  return useSWR(
    scenarioId ? `/scenarios/${scenarioId}` : null,
    (url: string) => apiClient.get<ScenarioInfo>(url),
  );
}

// ---------------------------------------------------------------------------
// List scenario runs
// ---------------------------------------------------------------------------
export function useScenarioRuns(scenarioId: string | null, limit: number = 20) {
  return useSWR(
    scenarioId ? `/scenarios/${scenarioId}/runs?limit=${limit}` : null,
    (url: string) => apiClient.get<ScenarioRunInfo[]>(url),
  );
}

// ---------------------------------------------------------------------------
// Create scenario
// ---------------------------------------------------------------------------
export function useCreateScenario() {
  return useSWRMutation(
    "/scenarios",
    async (
      url: string,
      { arg }: { arg: { project_id: string; name: string; description?: string } },
    ) => {
      const result = await apiClient.post<ScenarioInfo>(url, arg);
      mutate((key) => Array.isArray(key) && key[0] === "/scenarios");
      return result;
    },
  );
}

// ---------------------------------------------------------------------------
// Update scenario
// ---------------------------------------------------------------------------
export function useUpdateScenario() {
  return useSWRMutation(
    "/scenarios",
    async (
      _url: string,
      { arg }: { arg: { scenarioId: string; data: Record<string, unknown> } },
    ) => {
      const result = await apiClient.patch<ScenarioInfo>(
        `/scenarios/${arg.scenarioId}`,
        arg.data,
      );
      mutate((key) => Array.isArray(key) && key[0] === "/scenarios");
      mutate(`/scenarios/${arg.scenarioId}`);
      return result;
    },
  );
}

// ---------------------------------------------------------------------------
// Delete scenario
// ---------------------------------------------------------------------------
export function useDeleteScenario() {
  return useSWRMutation(
    "/scenarios",
    async (_url: string, { arg }: { arg: string }) => {
      const result = await apiClient.delete(`/scenarios/${arg}`);
      mutate((key) => Array.isArray(key) && key[0] === "/scenarios");
      return result;
    },
  );
}

// ---------------------------------------------------------------------------
// Add step to scenario
// ---------------------------------------------------------------------------
export async function addScenarioStep(
  scenarioId: string,
  stepData: Record<string, unknown>,
) {
  const result = await apiClient.post<ScenarioStepInfo>(
    `/scenarios/${scenarioId}/steps`,
    stepData,
  );
  mutate(`/scenarios/${scenarioId}`);
  return result;
}

// ---------------------------------------------------------------------------
// Update step
// ---------------------------------------------------------------------------
export async function updateScenarioStep(
  scenarioId: string,
  stepId: string,
  stepData: Record<string, unknown>,
) {
  const result = await apiClient.patch<ScenarioStepInfo>(
    `/scenarios/${scenarioId}/steps/${stepId}`,
    stepData,
  );
  mutate(`/scenarios/${scenarioId}`);
  return result;
}

// ---------------------------------------------------------------------------
// Delete step
// ---------------------------------------------------------------------------
export async function deleteScenarioStep(scenarioId: string, stepId: string) {
  const result = await apiClient.delete(
    `/scenarios/${scenarioId}/steps/${stepId}`,
  );
  mutate(`/scenarios/${scenarioId}`);
  return result;
}

// ---------------------------------------------------------------------------
// Reorder steps
// ---------------------------------------------------------------------------
export async function reorderScenarioSteps(
  scenarioId: string,
  stepIds: string[],
) {
  const result = await apiClient.post<ScenarioStepInfo[]>(
    `/scenarios/${scenarioId}/steps/reorder`,
    { step_ids: stepIds },
  );
  mutate(`/scenarios/${scenarioId}`);
  return result;
}

// ---------------------------------------------------------------------------
// Add data mapping
// ---------------------------------------------------------------------------
export async function addDataMapping(
  scenarioId: string,
  stepId: string,
  mappingData: Record<string, unknown>,
) {
  const result = await apiClient.post(
    `/scenarios/${scenarioId}/steps/${stepId}/mappings`,
    mappingData,
  );
  mutate(`/scenarios/${scenarioId}`);
  return result;
}

// ---------------------------------------------------------------------------
// Delete data mapping
// ---------------------------------------------------------------------------
export async function deleteDataMapping(
  scenarioId: string,
  stepId: string,
  mappingId: string,
) {
  const result = await apiClient.delete(
    `/scenarios/${scenarioId}/steps/${stepId}/mappings/${mappingId}`,
  );
  mutate(`/scenarios/${scenarioId}`);
  return result;
}

// ---------------------------------------------------------------------------
// Execute scenario
// ---------------------------------------------------------------------------
export async function executeScenario(
  scenarioId: string,
  mode?: string,
  executionConfig?: Record<string, unknown>,
) {
  const body: Record<string, unknown> = {};
  if (mode) body.mode = mode;
  if (executionConfig) body.execution_config = executionConfig;
  return apiClient.post<ScenarioRunInfo>(
    `/scenarios/${scenarioId}/execute`,
    body,
  );
}
