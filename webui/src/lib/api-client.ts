import { getFastapiUrl } from "@/lib/config";
import { getToken, clearAuth } from "@/lib/auth";
import type { PaginatedResponse, SuccessResponse, MessageResponse } from "@/app/types/api";

export function getApiBaseUrl(): string {
  return getFastapiUrl();
}

class ApiClient {
  private getBaseUrl(): string {
    return getApiBaseUrl();
  }

  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const baseUrl = this.getBaseUrl();

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "X-Space-Id": "default",
    };

    const token = getToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    // Merge with existing headers (handle both cases)
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

    if (res.status === 401) {
      clearAuth();
      if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
        window.location.href = "/login";
      }
      throw new Error("登录已过期，请重新登录");
    }

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
    const raw = await this.request<Record<string, unknown>>(`${path}${query}`);
    // Backend returns "pagination", frontend expects "info"
    return {
      success: raw.success as boolean,
      data: raw.data as T[],
      info: (raw.info ?? raw.pagination) as PaginatedResponse<T>["info"],
    };
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

  async put<T>(path: string, body: unknown): Promise<SuccessResponse<T>> {
    return this.request<SuccessResponse<T>>(path, {
      method: "PUT",
      body: JSON.stringify(body),
    });
  }

  async delete(path: string): Promise<MessageResponse> {
    return this.request<MessageResponse>(path, { method: "DELETE" });
  }
}

export const apiClient = new ApiClient();
