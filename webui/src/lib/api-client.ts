import { getFastapiUrl } from "@/lib/config";
import type { PaginatedResponse, SuccessResponse, MessageResponse } from "@/app/types/api";

export function getApiBaseUrl(): string {
  return getFastapiUrl();
}

/**
 * 拼一个带 `/api/v2` 前缀的绝对地址。
 *
 * 给「浏览器自己要发的请求」用：`<img src>`、`<video>`、`<iframe>`、新标签页——
 * 它们不走 apiClient，不会自动补前缀，少了这段就会拿到 404 的 JSON，然后被
 * 浏览器的 ORB 拦成 ERR_BLOCKED_BY_ORB（看起来像"图片挂了"，其实是 404）。
 */
export function apiV2Url(path: string): string {
  return `${getApiBaseUrl()}/api/v2${path}`;
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

    // 平台是本地单机模式（2026-09 去掉登录页）：不再附带 token。
    // 后端 CurrentUserDep 在没有 token 时返回内置本地用户，见 api/v2/auth.py。

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
      // 去登录页之后这里不该再出现 401；出现就是配置问题（例如反代 Basic Auth），
      // 把原因原样抛给调用方，而不是跳一个不存在的登录页。
      throw new Error("后端返回 401（平台已无登录功能，请检查反代是否要求 Basic Auth）");
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
