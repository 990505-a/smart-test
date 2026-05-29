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
  pagination?: PaginationInfo;
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
  template?: "test_case" | "test_case_bdd";
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

// === API Test ===
export interface APITestInfo {
  id: string;
  project_id: string;
  folder_id: string | null;
  test_case_id: string | null;
  identifier: string;
  name: string;
  description: string | null;
  schema_url: string | null;
  schema_path: string | null;
  schema_type: string;
  script_path: string | null;
  script_format: string;
  script_language: string;
  test_config: Record<string, unknown>;
  generated_by_agent: string | null;
  generation_params: Record<string, unknown>;
  total_endpoints: number;
  total_scenarios: number;
  created_at: string;
  updated_at: string | null;
}

export interface APITestCreate {
  project_id: string;
  folder_id?: string | null;
  name: string;
  description?: string;
  schema_url?: string;
  schema_type?: string;
  script_format?: string;
  script_language?: string;
  test_config?: Record<string, unknown>;
}

export interface APITestUpdate {
  name?: string;
  description?: string;
  schema_url?: string;
  schema_path?: string;
  script_path?: string;
  test_config?: Record<string, unknown>;
}

// === API Test Run ===
export interface APITestRunInfo {
  id: string;
  project_id: string;
  api_test_id: string;
  identifier: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  execution_config: Record<string, unknown>;
  total_tests: number;
  passed_tests: number;
  failed_tests: number;
  skipped_tests: number;
  duration_ms: number | null;
  report_path: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string | null;
}

// === API Test Result ===
export interface APITestResultInfo {
  id: string;
  test_run_id: string;
  api_test_id: string | null;
  scenario_name: string | null;
  endpoint: string | null;
  method: string | null;
  status: "passed" | "failed" | "skipped" | "blocked";
  request_summary: Record<string, unknown> | null;
  response_summary: Record<string, unknown> | null;
  error_message: string | null;
  detail_log_id: string | null;
  duration_ms: number | null;
  retry_count: number;
  created_at: string;
}

// === Scenario ===
export interface ScenarioInfo {
  id: string;
  project_id: string;
  folder_id: string | null;
  identifier: string;
  name: string;
  description: string | null;
  status: string;
  total_steps: number;
  last_run_status: string | null;
  last_run_at: string | null;
  steps: ScenarioStepInfo[];
  created_at: string;
  updated_at: string | null;
}

export interface ScenarioStepInfo {
  id: string;
  scenario_id: string;
  endpoint_id: string | null;
  step_order: number;
  name: string;
  description: string | null;
  request_override: Record<string, unknown>;
  headers_override: Record<string, unknown>;
  extractors: unknown[];
  assertions: unknown[];
  condition_expression: string | null;
  continue_on_failure: boolean;
  delay_ms: number;
  retry_count: number;
}

export interface ScenarioRunInfo {
  id: string;
  scenario_id: string;
  project_id: string;
  identifier: string;
  status: string;
  total_steps: number;
  passed_steps: number;
  failed_steps: number;
  skipped_steps: number;
  duration_ms: number | null;
  report_path: string | null;
  error_message: string | null;
  created_at: string;
}

// === Workspace ===
export interface WorkspaceInfo {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  is_default: boolean;
  created_at: string;
  updated_at: string | null;
}

export interface WorkspaceCreate {
  name: string;
  slug?: string;
  description?: string;
}

// === Web Function ===
export interface WebFunctionInfo {
  id: string;
  project_id: string;
  folder_id: string | null;
  identifier: string;
  display_name: string;
  name: string;
  description: string | null;
  base_url: string | null;
  business_module: string | null;
  navigation: Record<string, unknown> | null;
  pages: unknown[] | null;
  tags: string[] | null;
  custom_config: Record<string, unknown> | null;
  total_sub_functions: number;
  total_test_cases: number;
  total_test_runs: number;
  last_run_status: string | null;
  sort_order: number;
  created_at: string;
  updated_at: string | null;
  sub_functions?: WebSubFunctionInfo[];
}

export interface WebSubFunctionInfo {
  id: string;
  project_id: string;
  function_id: string;
  folder_id: string | null;
  identifier: string;
  display_name: string;
  name: string;
  description: string | null;
  test_type: string;
  target_pages: unknown[] | null;
  test_scenario: string | null;
  test_data: Record<string, unknown> | null;
  expected_results: unknown[] | null;
  priority: string;
  tags: string[] | null;
  custom_config: Record<string, unknown> | null;
  total_test_cases: number;
  total_test_runs: number;
  last_run_status: string | null;
  sort_order: number;
  created_at: string;
  updated_at: string | null;
}

export interface WebFunctionCreate {
  project_id: string;
  folder_id?: string | null;
  display_name: string;
  name: string;
  description?: string;
  base_url?: string;
  business_module?: string;
  navigation?: Record<string, unknown>;
  pages?: unknown[];
  tags?: string[];
  custom_config?: Record<string, unknown>;
}

export interface WebFunctionUpdate {
  display_name?: string;
  name?: string;
  description?: string;
  base_url?: string;
  business_module?: string;
  navigation?: Record<string, unknown>;
  pages?: unknown[];
  tags?: string[];
  custom_config?: Record<string, unknown>;
}

// === Web Test ===
export interface WebTestInfo {
  id: string;
  project_id: string;
  folder_id: string | null;
  test_case_id: string | null;
  function_id: string | null;
  sub_function_id: string | null;
  identifier: string;
  name: string;
  description: string | null;
  base_url: string | null;
  script_path: string | null;
  script_format: string;
  script_language: string;
  test_config: Record<string, unknown>;
  target_pages: Record<string, unknown> | null;
  test_flows: Record<string, unknown> | null;
  generated_by_agent: string;
  generation_params: Record<string, unknown> | null;
  total_pages: number;
  total_flows: number;
  created_at: string;
  updated_at: string | null;
}

export interface WebTestCreate {
  project_id: string;
  folder_id?: string | null;
  function_id?: string | null;
  sub_function_id?: string | null;
  name: string;
  description?: string;
  base_url?: string;
  test_config?: Record<string, unknown>;
}

export interface WebTestUpdate {
  name?: string;
  description?: string;
  base_url?: string;
  test_config?: Record<string, unknown>;
}

export interface WebTestRunInfo {
  id: string;
  project_id: string;
  web_test_id: string;
  identifier: string;
  status: string;
  execution_config: Record<string, unknown> | null;
  total_tests: number;
  passed_tests: number;
  failed_tests: number;
  skipped_tests: number;
  duration_ms: number | null;
  report_path: string | null;
  screenshots_path: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface WebTestResultInfo {
  id: string;
  test_run_id: string;
  web_test_id: string;
  scenario_name: string;
  page_url: string;
  test_type: string;
  status: string;
  test_summary: Record<string, unknown> | null;
  error_details: Record<string, unknown> | null;
  error_message: string | null;
  screenshot_path: string | null;
  duration_ms: number | null;
  retry_count: number;
  created_at: string;
}

// === Configuration ===
export interface ConfigurationInfo {
  id: number;
  name: string;
  os: string | null;
  os_version: string | null;
  device: string | null;
  browser: string | null;
  browser_version: string | null;
  is_system: boolean;
  description: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface ConfigurationCreate {
  name: string;
  os?: string;
  os_version?: string;
  device?: string;
  browser?: string;
  browser_version?: string;
  is_system?: boolean;
  description?: string;
}

export interface ConfigurationUpdate {
  name?: string;
  os?: string;
  os_version?: string;
  device?: string;
  browser?: string;
  browser_version?: string;
  is_system?: boolean;
  description?: string;
}
