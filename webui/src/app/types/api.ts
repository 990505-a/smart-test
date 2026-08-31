// Shared API response envelope types.
// 2026-08 用例 MD 重构：用例/项目/测试运行等实体类型已随关系库链路移除，
// 用例文档类型见 @/lib/api/useCaseDocs；模块专属类型在各模块 hook 内定义。

export interface PaginationInfo {
  page: number;
  page_size: number;
  count: number;
  total: number;
  total_pages: number;
  prev_url: string | null;
  next_url: string | null;
}

export interface PaginatedResponse<T> {
  success: boolean;
  data: T[];
  info: PaginationInfo;
}

export interface SuccessResponse<T> {
  success: boolean;
  data: T;
}

export interface MessageResponse {
  success: boolean;
  message: string;
}

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

export interface ConfigurationInfo {
  key: string;
  value: unknown;
  description: string | null;
  updated_at: string;
  created_at: string;
}

export interface ConfigurationCreate {
  key: string;
  value: unknown;
  description?: string;
}

export interface ConfigurationUpdate {
  value?: unknown;
  description?: string;
}
