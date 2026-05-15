import { getConfig } from "@/lib/config";
import type { PaginatedResponse, SuccessResponse, MessageResponse } from "@/app/types/api";

class ApiClient {
  private getBaseUrl(): string {
    const config = getConfig();
    return config?.fastapiUrl || "http://localhost:8000";
  }

  private getWorkspaceId(): string {
    const config = getConfig();
    return config?.workspaceId || "default";
  }

  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const baseUrl = this.getBaseUrl();
    const workspaceId = this.getWorkspaceId();

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "X-Space-Id": workspaceId,
    };

    // Merge with existing headers
    if (options.headers) {
      if (options.headers instanceof Headers) {
        options.headers.forEach((value, key) => { headers[key] = value; });
      } else if (typeof options.headers === "object") {
        Object.assign(headers, options.headers);
      }
    }

    const res = await fetch(`${baseUrl}/api/v2${path}`, {
      ...options,
      headers,
    });

    if (!res.ok) {
      const error = await res.json().catch(() => ({ message: `HTTP ${res.status}` }));
      throw new Error(error.message || error.detail || `HTTP ${res.status}`);
    }

    return res.json();
  }

  async get<T>(path: string, params?: Record<string, string>): Promise<SuccessResponse<T>> {
    const query = params ? "?" + new URLSearchParams(params).toString() : "";
    return this.request<SuccessResponse<T>>(`${path}${query}`);
  }

  async getPaginated<T>(path: string, params?: Record<string, string | number>): Promise<PaginatedResponse<T>> {
    const query = params
      ? "?" + new URLSearchParams(
          Object.entries(params).map(([k, v]) => [k, String(v)])
        ).toString()
      : "";
    return this.request<PaginatedResponse<T>>(`${path}${query}`);
  }

  async post<T>(path: string, body: unknown): Promise<SuccessResponse<T>> {
    return this.request<SuccessResponse<T>>(path, {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  async patch<T>(path: string, body: unknown): Promise<SuccessResponse<T>> {
    return this.request<SuccessResponse<T>>(path, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  }

  async delete(path: string): Promise<MessageResponse> {
    return this.request<MessageResponse>(path, { method: "DELETE" });
  }
}

export const apiClient = new ApiClient();
