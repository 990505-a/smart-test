// TypeScript types matching Phase 8 Pydantic backend schemas exactly.
// See: src/app/api/v2/*.py, src/app/db/schemas/*.py

// === Response Envelopes ===
export interface PaginationInfo {
  page: number;
  page_size: number;
  count: number;
  total: number;
  prev: string | null;
  next: string | null;
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

// === Project ===
export interface ProjectInfo {
  id: string;
  identifier: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface ProjectCreate {
  name: string;
  description?: string;
}

export interface ProjectUpdate {
  name?: string;
  description?: string;
}

// === Folder ===
export interface FolderInfo {
  id: string;
  project_id: string;
  parent_id: string | null;
  name: string;
  description: string | null;
  folder_type: "test_case" | "api_test";
  created_at: string;
  updated_at: string | null;
}

export interface FolderTreeNode extends FolderInfo {
  children: FolderTreeNode[];
}

export interface FolderCreate {
  project_id: string;
  parent_id?: string | null;
  name: string;
  description?: string;
  folder_type?: "test_case" | "api_test";
}

export interface FolderUpdate {
  name?: string;
  description?: string;
  parent_id?: string | null;
}

// === Test Case ===
export interface TestStepInfo {
  id: string;
  step_number: number;
  action: string;
  expected_result: string | null;
}

export interface TestCaseInfo {
  id: string;
  project_id: string;
  folder_id: string | null;
  identifier: string;
  name: string;
  description: string | null;
  preconditions: string | null;
  priority: "low" | "medium" | "high" | "critical";
  state: "new" | "review_pending" | "reviewed" | "not_run" | "passed" | "failed" | "blocked" | "skipped";
  test_case_type: string;
  template: "test_case" | "test_case_bdd";
  feature: string | null;
  scenario: string | null;
  background: string | null;
  automation_status: string | null;
  custom_fields: Record<string, unknown> | null;
  version: number;
  steps: TestStepInfo[];
  created_at: string;
  updated_at: string | null;
}

export interface TestCaseCreate {
  project_id: string;
  folder_id?: string | null;
  name: string;
  description?: string;
  preconditions?: string;
  priority?: "low" | "medium" | "high" | "critical";
  template?: "test_case" | "test_case_bdd";
  feature?: string;
  scenario?: string;
  background?: string;
  steps?: Array<{ step_number: number; action: string; expected_result?: string }>;
}

export interface TestCaseUpdate {
  name?: string;
  description?: string;
  preconditions?: string;
  priority?: "low" | "medium" | "high" | "critical";
  state?: string;
  folder_id?: string | null;
  custom_fields?: Record<string, unknown> | null;
  feature?: string;
  scenario?: string;
  background?: string;
  steps?: Array<{ step_number: number; action: string; expected_result?: string }>;
}

// === Test Run ===
export interface TestRunTestCaseInfo {
  id: string;
  test_run_id: string;
  test_case_id: string;
  latest_status: "passed" | "failed" | "skipped" | "blocked" | "not_executed";
  created_at: string;
  updated_at: string | null;
}

export interface TestRunInfo {
  id: string;
  project_id: string;
  identifier: string;
  name: string;
  description: string | null;
  run_state: "new_run" | "in_progress" | "under_review" | "rejected" | "done" | "closed";
  active_state: "active" | "closed";
  test_cases_count: number;
  passed_count: number;
  failed_count: number;
  skipped_count: number;
  blocked_count: number;
  not_executed_count: number;
  test_run_cases: TestRunTestCaseInfo[];
  created_at: string;
  updated_at: string | null;
}

export interface TestRunCreate {
  project_id: string;
  name: string;
  description?: string;
  test_case_ids?: string[];
}

export interface TestRunUpdate {
  name?: string;
  description?: string;
  run_state?: string;
}

// === Test Result (matches test_result.py schema) ===
export interface TestStepResultInfo {
  id: string;
  test_result_id: string;
  step_index: number;
  step_number: number;
  action: string;
  expected_result: string | null;
  actual_result: string | null;
  description: string | null;
  status: "passed" | "failed" | "skipped" | "blocked";
  created_at: string;
  updated_at: string | null;
}

export interface TestResultInfo {
  id: string;
  test_run_id: string;
  test_case_id: string;
  status: "passed" | "failed" | "skipped" | "blocked" | "not_executed";
  description: string | null;
  duration_ms: number | null;
  step_results: TestStepResultInfo[];
  created_at: string;
  updated_at: string | null;
}

export interface TestResultCreate {
  test_run_id: string;
  test_case_id: string;
  status: "passed" | "failed" | "skipped" | "blocked" | "not_executed";
  description?: string;
  duration_ms?: number;
  step_results?: Array<{
    step_index: number;
    step_number: number;
    actual_result?: string;
    status: "passed" | "failed" | "skipped" | "blocked";
    description?: string;
  }>;
}
