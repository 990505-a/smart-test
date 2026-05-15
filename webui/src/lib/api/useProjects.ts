"use client";

import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { mutate } from "swr";
import { apiClient } from "@/lib/api-client";
import type { ProjectInfo, ProjectCreate, ProjectUpdate, PaginatedResponse } from "@/app/types/api";

// List projects (paginated)
export function useProjects(page: number = 1, pageSize: number = 30) {
  return useSWR<PaginatedResponse<ProjectInfo>>(
    ["/projects", page, pageSize],
    ([url, p, ps]) => apiClient.getPaginated<ProjectInfo>(url, { p: p as number, page_size: ps as number })
  );
}

// Get single project
export function useProject(identifier: string | null) {
  return useSWR(
    identifier ? `/projects/${identifier}` : null,
    (url: string) => apiClient.get<ProjectInfo>(url)
  );
}

// Create project
export function useCreateProject() {
  return useSWRMutation(
    "/projects",
    async (url: string, { arg }: { arg: ProjectCreate }) => {
      const result = await apiClient.post<ProjectInfo>(url, arg);
      mutate(key => Array.isArray(key) && key[0] === "/projects");
      return result;
    }
  );
}

// Update project
export function useUpdateProject() {
  return useSWRMutation(
    "/projects",
    async (_url: string, { arg }: { arg: { identifier: string; data: ProjectUpdate } }) => {
      const result = await apiClient.patch<ProjectInfo>(`/projects/${arg.identifier}`, arg.data);
      mutate(key => Array.isArray(key) && key[0] === "/projects");
      return result;
    }
  );
}

// Delete project
export function useDeleteProject() {
  return useSWRMutation(
    "/projects",
    async (_url: string, { arg }: { arg: string }) => {
      const result = await apiClient.delete(`/projects/${arg}`);
      mutate(key => Array.isArray(key) && key[0] === "/projects");
      return result;
    }
  );
}
