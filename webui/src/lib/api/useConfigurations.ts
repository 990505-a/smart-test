"use client";

import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { mutate } from "swr";
import { apiClient } from "@/lib/api-client";
import type {
  ConfigurationInfo,
  ConfigurationCreate,
  ConfigurationUpdate,
  PaginatedResponse,
} from "@/app/types/api";

// ---------------------------------------------------------------------------
// List configurations (paginated)
// ---------------------------------------------------------------------------
export function useConfigurations(page: number = 1, pageSize: number = 30) {
  return useSWR<PaginatedResponse<ConfigurationInfo>>(
    ["/configurations", page, pageSize],
    ([url, p, ps]) =>
      apiClient.getPaginated<ConfigurationInfo>(url, { p: p as number, page_size: ps as number }),
  );
}

// ---------------------------------------------------------------------------
// Get single configuration
// ---------------------------------------------------------------------------
export function useConfiguration(id: number | null) {
  return useSWR(
    id !== null ? `/configurations/${id}` : null,
    (url: string) => apiClient.get<ConfigurationInfo>(url),
  );
}

// ---------------------------------------------------------------------------
// Create configuration
// ---------------------------------------------------------------------------
export function useCreateConfiguration() {
  return useSWRMutation(
    "/configurations",
    async (url: string, { arg }: { arg: ConfigurationCreate }) => {
      const result = await apiClient.post<ConfigurationInfo>(url, arg);
      mutate((key) => Array.isArray(key) && key[0] === "/configurations");
      return result;
    },
  );
}

// ---------------------------------------------------------------------------
// Update configuration
// ---------------------------------------------------------------------------
export function useUpdateConfiguration() {
  return useSWRMutation(
    "/configurations",
    async (
      _url: string,
      { arg }: { arg: { id: number; data: ConfigurationUpdate } },
    ) => {
      const result = await apiClient.patch<ConfigurationInfo>(
        `/configurations/${arg.id}`,
        arg.data,
      );
      mutate((key) => Array.isArray(key) && key[0] === "/configurations");
      mutate(`/configurations/${arg.id}`);
      return result;
    },
  );
}

// ---------------------------------------------------------------------------
// Delete configuration
// ---------------------------------------------------------------------------
export function useDeleteConfiguration() {
  return useSWRMutation(
    "/configurations",
    async (_url: string, { arg }: { arg: number }) => {
      const result = await apiClient.delete(`/configurations/${arg}`);
      mutate((key) => Array.isArray(key) && key[0] === "/configurations");
      return result;
    },
  );
}

// ---------------------------------------------------------------------------
// Get system configurations (all system-flagged configs, not paginated)
// ---------------------------------------------------------------------------
export function useSystemConfigurations() {
  return useSWR(
    "/configurations/system",
    (url: string) => apiClient.get<ConfigurationInfo[]>(url),
  );
}
