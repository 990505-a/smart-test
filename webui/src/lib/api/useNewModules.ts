"use client";

// SWR hooks for the 2026-08 transformation modules.

import useSWR from "swr";
import { apiClient } from "@/lib/api-client";

const fetcher = <T,>(path: string) => apiClient.get<T>(path).then((r) => r.data);

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
// （用例打分/评审沉淀已随 2026-08 MD 重构移除：用户直接在用例 MD 文档上
//  标注 ✅/❌/⚠️ + 批注，见 useCaseDocs.ts 与 /cases 页）
// （自进化模块已移除 2026-08-31：记忆系统改为 EverOS，经验沉淀由其
//  OME 离线进化策略接管，见 useMemories.ts）

export interface SkillTreeNode {
  name: string;
  type: "dir" | "file";
  path?: string;
  children?: SkillTreeNode[];
}

export interface ApiDocImport {
  id: string;
  doc_url: string;
  title: string | null;
  endpoint_count: string;
  status: string;
  error: string | null;
  created_at: string | null;
}

export interface ApiScript {
  id: string;
  name: string;
  module: string | null;
  doc_url: string | null;
  language: string;
  version: number;
  status: string;
  endpoints: string[];
  repair_history: { version: number; error: string; fix_summary: string; at: string }[];
  content?: string;
  updated_at: string | null;
  created_at: string | null;
}

export interface ApiScriptRun {
  id: string;
  script_id: string;
  status: string;
  exit_code: number | null;
  output: string | null;
  duration_ms: number | null;
  triggered_by: string;
  repair_attempt: number;
  created_at: string | null;
}

export interface UiScript {
  id: string;
  name: string;
  module: string | null;
  description: string | null;
  version: number;
  status: string;
  content?: string;
  updated_at: string | null;
  created_at: string | null;
}

export interface UiScriptRun {
  id: string;
  script_id: string;
  status: string;
  exit_code: number | null;
  output: string | null;
  screenshots: string | null;
  duration_ms: number | null;
  triggered_by: string;
  created_at: string | null;
}

export interface UnityStatus {
  available: boolean;
  error?: string;
  hint?: string;
  server?: Record<string, unknown>;
  editor?: { isPlaying?: boolean; isPaused?: boolean };
  is_playing?: boolean;
}

export interface FeishuStatus {
  available: boolean;
  logged_in: boolean;
  identity?: string;
  user?: string | null;
  error?: string;
  install_hint?: string;
}

export interface FeishuDeviceLogin {
  verification_url: string;
  device_code: string;
  expires_in: number;
}

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function useSkillTree() {
  return useSWR("/skills/tree", () => fetcher<SkillTreeNode[]>("/skills/tree"));
}

export function useApiDocs() {
  return useSWR("/api-auto/docs", () => fetcher<ApiDocImport[]>("/api-auto/docs"));
}

export function useApiScripts() {
  return useSWR("/api-auto/scripts", () => fetcher<ApiScript[]>("/api-auto/scripts"));
}

export function useApiScriptRuns(scriptId: string | null) {
  return useSWR(scriptId ? `/api-auto/scripts/${scriptId}/runs` : null, () =>
    fetcher<ApiScriptRun[]>(`/api-auto/scripts/${scriptId}/runs`)
  );
}

export function useUiScripts() {
  return useSWR("/ui-auto/scripts", () => fetcher<UiScript[]>("/ui-auto/scripts"));
}

export function useUiScriptRuns(scriptId: string | null) {
  return useSWR(scriptId ? `/ui-auto/scripts/${scriptId}/runs` : null, () =>
    fetcher<UiScriptRun[]>(`/ui-auto/scripts/${scriptId}/runs`)
  );
}

export function useUnityStatus() {
  return useSWR("/ui-auto/status", () => fetcher<UnityStatus>("/ui-auto/status"), {
    refreshInterval: 15000,
  });
}

export function useFeishuStatus() {
  return useSWR("/feishu/status", () => fetcher<FeishuStatus>("/feishu/status"));
}

/** 发起飞书设备码登录：返回授权链接，用户浏览器打开并授权 */
export async function startFeishuLogin(): Promise<FeishuDeviceLogin> {
  return apiClient.post<FeishuDeviceLogin>("/feishu/auth/start", {}).then((r) => r.data);
}

/** 用户完成浏览器授权后，用 device_code 完成登录绑定 */
export async function completeFeishuLogin(
  deviceCode: string
): Promise<{ logged_in: boolean; user?: string | null }> {
  return apiClient
    .post<{ logged_in: boolean; user?: string | null }>("/feishu/auth/complete", {
      device_code: deviceCode,
    })
    .then((r) => r.data);
}

export function useModelSettings() {
  return useSWR("/settings/model", () => fetcher<Record<string, string | null>>("/settings/model"));
}

export function usePlatformSettings() {
  return useSWR("/settings/platform", () => fetcher<Record<string, string | null>>("/settings/platform"));
}

// ---------------------------------------------------------------------------
// Model presets (模型预设)
// ---------------------------------------------------------------------------

export interface ModelPreset {
  name: string;
  saved_at: string | null;
  values: Record<string, string | null>;
}

export function useModelPresets() {
  return useSWR("/settings/model/presets", () => fetcher<ModelPreset[]>("/settings/model/presets"));
}

export interface ModelTestResult {
  text: { ok: boolean; latency_ms?: number; error?: string; model?: string };
  vision: { ok: boolean; latency_ms?: number; error?: string; model?: string; skipped?: boolean };
}

export function testModelConnection(values: Record<string, string>) {
  return apiClient.post<ModelTestResult>("/settings/model/test", { values }).then((r) => r.data);
}

export function applyModelPreset(name: string) {
  return apiClient
    .post<{ applied: string; values: Record<string, string | null> }>(`/settings/model/presets/${encodeURIComponent(name)}/apply`, {})
    .then((r) => r.data);
}

export function saveModelPreset(name: string, values: Record<string, string>) {
  return apiClient.post<{ name: string }>("/settings/model/presets", { name, values }).then((r) => r.data);
}

export function deleteModelPreset(name: string) {
  return apiClient.delete(`/settings/model/presets/${encodeURIComponent(name)}`);
}

// ---------------------------------------------------------------------------
// Codebase graph (代码图谱模块)
// ---------------------------------------------------------------------------

export interface CbmProject {
  name: string;
  root_path: string;
  nodes: number | null;
  edges: number | null;
  size_bytes: number | null;
}

export interface CbmStatus {
  success: boolean;
  available: boolean;
  error: string | null;
  exe: string;
  projects: CbmProject[];
  graph_daemon: { up: boolean; port: number };
}

export interface CbmRepo {
  id: string;
  repo_path: string;
  display_name: string | null;
  project: string;
  indexed: boolean;
  nodes: number | null;
  edges: number | null;
  file_type_mode: "all" | "include" | "exclude";
  file_types: string[];
  auto_increment: boolean;
  last_index_at: string | null;
  last_index_mode: string | null;
}

export interface CbmIndexRun {
  id: string;
  repo_id: string;
  repo_path: string;
  display_name: string | null;
  trigger: string;
  mode: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  detail: Record<string, unknown> | null;
  error: string | null;
}

export interface CbmIndexProgress {
  repo_path: string;
  phase: string;
  last_line: string;
  started_at: number;
  live: boolean;
  elapsed_s: number;
}

export interface CbmSchedule {
  success: boolean;
  enabled: boolean;
  interval_hours: number;
  next_run: string | null;
}

export function useCbmStatus() {
  return useSWR("/codebase/status", () => fetcher<CbmStatus>("/codebase/status"));
}

export function useCbmRepos(refreshMs = 0) {
  return useSWR("/codebase/repos", () => fetcher<{ success: boolean; repos: CbmRepo[] }>("/codebase/repos"),
    refreshMs ? { refreshInterval: refreshMs } : undefined);
}

export function useCbmRuns(limit = 30) {
  return useSWR(`/codebase/runs?limit=${limit}`, () =>
    fetcher<{ success: boolean; runs: CbmIndexRun[]; indexing: string | null;
              progress: CbmIndexProgress | null }>(`/codebase/runs?limit=${limit}`),
    // 索引进行中加快轮询(2s),空闲时 8s
    { refreshInterval: (latest?: { indexing: string | null }) => (latest?.indexing ? 2000 : 8000) });
}

export function useCbmSchedule() {
  return useSWR("/codebase/schedule", () => fetcher<CbmSchedule>("/codebase/schedule"));
}

export interface CbmGraphData {
  nodes: {
    id: number;
    x: number;
    y: number;
    z: number;
    label: string;
    name: string;
    file_path?: string;
    qualified_name?: string;
    start_line?: number;
    end_line?: number;
    size: number;
    color: string;
    status?: string;
    in_calls?: number;
  }[];
  edges: { source: number; target: number; type: string }[];
  total_nodes?: number;
  linked_projects?: unknown[];
  missed_graph?: unknown;
}

export function fetchCbmGraphData(project: string, maxNodes: number) {
  return apiClient
    .get<CbmGraphData>("/codebase/graph-data", { project, max_nodes: String(maxNodes) })
    .then((r) => r.data);
}

/** 范围视图(大图专用): mode=dir 目录前缀子图 / mode=symbol 符号直接上下游 */
export function fetchCbmSubgraph(project: string, mode: "dir" | "symbol", value: string) {
  return apiClient
    .get<CbmGraphData>("/codebase/graph-subgraph", { project, mode, value })
    .then((r) => r.data);
}

export function fetchCbmIgnore(repoId: string) {
  return apiClient
    .get<{ success: boolean; exists: boolean; content: string; managed_present: boolean }>(
      `/codebase/repos/${repoId}/cbmignore`)
    .then((r) => r.data);
}
