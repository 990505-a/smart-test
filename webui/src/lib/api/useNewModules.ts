"use client";

// SWR hooks for the 2026-08 transformation modules.

import useSWR from "swr";
import { apiClient, apiV2Url } from "@/lib/api-client";
import type { SuccessResponse } from "@/app/types/api";

const fetcher = <T,>(path: string) => apiClient.get<T>(path).then((r) => r.data);

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
// （用例打分/评审沉淀已随 2026-08 MD 重构移除：用户直接在用例 MD 文档上
//  标注 ✅/❌/⚠️ + 批注，见 useCaseDocs.ts 与 /cases 页）
// （自进化模块已移除 2026-08-31：记忆系统改为 harness 风格的 Markdown 模块
//  （AGENTS.md / MEMORY.md / USER.md / failures.md …），见 useMemories.ts）

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

export interface UnityScript {
  id: string;
  name: string;
  module: string | null;
  description: string | null;
  version: number;
  status: string;
  /** 起跑线（平台不复位）：跑之前游戏该处于什么状态，由用户手动复位落到这里 */
  start_line?: { scene?: string; wait_for?: string } | null;
  /** 起跑线的一行标注（"# 起跑线（人工复位）：场景=…；标志物=…"去掉井号那部分） */
  start_line_note?: string;
  content?: string;
  updated_at: string | null;
  created_at: string | null;
}

export interface UnityScriptRun {
  id: string;
  script_id: string;
  status: string;
  exit_code: number | null;
  output: string | null;
  /** 老字段：产物绝对路径的 JSON 数组（新前端读 artifacts，这里仍保留兼容） */
  screenshots: string | null;
  /** 产物清单：截图 / 录像 / 步骤轨迹 / 失败现场文本 */
  artifacts: UnityArtifact[] | null;
  /** 本次执行的步骤轨迹（每个动作一行：点了什么、成了没有、耗时） */
  steps: UnityStep[] | null;
  duration_ms: number | null;
  triggered_by: string;
  /** 取产物的只读签名（`<img>` / `<video>` 带不上自定义头） */
  share_sig?: string;
  /** 产物清单还在但文件已被清理：不能画缩略图，得说清楚 */
  artifacts_pruned?: boolean;
  /** 卡在 running 太久（进程被杀/容器重启），不该继续显示"运行中" */
  stale_running?: boolean;
  /** 还在跑：已经跑了多久（跑完才有 duration_ms，这个是给"进行中"看的） */
  elapsed_ms?: number | null;
  created_at: string | null;
}

export interface UnityArtifact {
  index: number;
  name: string;
  path: string;
  size: number | null;
  kind: "image" | "video" | "text" | "html" | "trace" | "file";
  pruned: boolean;
  /** 平台给的直链（已带签名） */
  url: string;
}

/** 删掉一条用例的结果：顺带清掉了多少执行记录与磁盘产物（给人一个交代）。 */
export interface UnityDeleteResult {
  deleted: boolean;
  runs: number;
  files: number;
  bytes: number;
  error?: string;
}

export interface UnityStep {
  i: number;
  /** 相对本次执行开始的秒数 */
  t: number;
  action: string;
  target?: string;
  ms: number;
  ok: boolean;
  error?: string;
}

export interface UnityStatus {
  available: boolean;
  error?: string;
  hint?: string;
  transport?: string;
  endpoint?: string;
  server?: { name?: string; version?: string; protocol?: string };
  flavor?: string;
  tool_count?: number;
  editor?: { isPlaying?: boolean; isPaused?: boolean; state?: string } | null;
  is_playing?: boolean | null;
  unity_connected?: boolean;
  /** 工程里有 Unity 还没导入的外部改动（桥内存里的 latch，Ctrl+R 清不掉）。 */
  external_changes_dirty?: boolean;
  /** 有实例但读不到编辑器状态：多半正在域重载 / 刚掉线。 */
  editor_stale?: boolean;
  /** 那批"桥会自己刷新+重编译"的工具现在能不能发（脏了/在 Play 都不能）。 */
  can_run_gated_tools?: boolean;
  gated_tools?: string[];
  /** 编辑器报了**显卡设备丢失**（DXGI_ERROR_DEVICE_REMOVED）：平台已停手不再发指令。 */
  gpu_device_lost?: boolean;
  /** 那条报错的原话（给用户看现场）。 */
  gpu_evidence?: string;
  /** 编辑器日志多久没写过了（只在已经熔断时给）：>60s 往往是编辑器卡死而不是掉线。 */
  editor_log_age_s?: number | null;
  /** 照着做就行的下一步（没问题时为空/缺省）。 */
  advice?: string[];
}

export interface UnityMcpTool {
  name: string;
  description: string;
  schema: Record<string, unknown>;
}

export interface UnityTools {
  success: boolean;
  count?: number;
  flavor?: string;
  server?: { name?: string; version?: string };
  tools?: UnityMcpTool[];
  error?: string;
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

export function useUnityScripts() {
  return useSWR("/unity-auto/scripts", () => fetcher<UnityScript[]>("/unity-auto/scripts"));
}

/** 删掉一条 Unity 用例：执行记录与磁盘产物（截图/录像/起跑线）由后端一起清。 */
export function deleteUnityScript(scriptId: string) {
  return apiClient
    .delete<SuccessResponse<UnityDeleteResult>>(`/unity-auto/scripts/${scriptId}`)
    .then((r) => r.data);
}

export function useUnityScriptRuns(scriptId: string | null) {
  return useSWR(scriptId ? `/unity-auto/scripts/${scriptId}/runs` : null, () =>
    fetcher<UnityScriptRun[]>(`/unity-auto/scripts/${scriptId}/runs`), {
    // 有执行在跑就轮询：历史列表里的状态也要自己变（不用手动刷新）
    refreshInterval: (data) => (data?.some((r) => r.status === "running" && !r.stale_running) ? 3000 : 0),
    refreshWhenHidden: true,
    revalidateOnFocus: true,
  });
}

/** 单条执行记录：执行是后台跑的，还在 running 时按 2s 轮询，跑完自动停。 */
export function useUnityRun(runId: string | null) {
  return useSWR(runId ? `/unity-auto/runs/${runId}` : null, () =>
    fetcher<UnityScriptRun>(`/unity-auto/runs/${runId}`), {
    refreshInterval: (data) => (data && data.status === "running" && !data.stale_running ? 2000 : 0),
    // **必须**：SWR 默认在页面不可见时暂停轮询，而这个页面常常在后台（人在聊天页看
    // 智能体、或在别的窗口等结果）—— 暂停的结果就是"跑完了还显示运行中"（实测）。
    refreshWhenHidden: true,
    revalidateOnFocus: true,
  });
}

export function useUnityStatus() {
  return useSWR("/unity-auto/status", () => fetcher<UnityStatus>("/unity-auto/status"), {
    refreshInterval: 15000,
  });
}

export function useUnityTools() {
  return useSWR("/unity-auto/tools", () => fetcher<UnityTools>("/unity-auto/tools"));
}

// --- Unity 手动录制（玩家自己点，平台录成用例）-------------------------------

export interface UnityRecording {
  id: string;
  name: string;
  /** recording = 正在录；recorded = 已停止待生成用例 */
  status: "recording" | "recorded" | string;
  events: number;
  steps: number;
  scene: string;
  created_at: string;
  duration_s: number | null;
  script_file: string | null;
  stopped_reason: string;
}

export interface UnityRecordStatus {
  active: string | null;
  on: boolean;
  events: number;
  hb_age?: number;
  reason?: string;
  rearmed?: boolean;
  rearm_error?: string;
  error?: string;
}

export interface UnityRecordingEvent {
  t?: number;
  type: string;
  path?: string;
  comp?: string;
  label?: string;
  panels?: string;
  kind?: string;
  text?: string;
  key?: string;
  from?: string;
  to?: string;
  name?: string;
  value?: boolean | string;
}

export function useUnityRecordings() {
  return useSWR("/unity-auto/recordings",
    () => fetcher<{ recordings: UnityRecording[] }>("/unity-auto/recordings")
      .then((d) => d.recordings ?? []));
}

/**
 * 录制状态轮询：只在"正在录"时刷新（2s）——它顺带做心跳自愈
 * （域重载把 Unity 侧钩子清掉后，后端会用同一个目录重挂）。
 */
export function useUnityRecordStatus(active: boolean) {
  return useSWR(
    active ? "/unity-auto/record/status" : null,
    () => fetcher<UnityRecordStatus>("/unity-auto/record/status"),
    { refreshInterval: 2000, revalidateOnFocus: false },
  );
}

/** Unity 产物直链（后端给的就是带签名的 URL，这里只补 API 前缀）。 */
export function unityArtifactUrl(artifact: Pick<UnityArtifact, "url">) {
  return apiV2Url(artifact.url);
}

// --- Web-UI automation (Web-UI 自动化模块, Playwright CLI) ------------------

export interface WebUiScript {
  id: string;
  name: string;
  module: string | null;
  description: string | null;
  spec_file: string;
  target_url: string | null;
  version: number;
  status: string;
  content?: string;
  repair_history?: unknown[];
  updated_at: string | null;
  created_at: string | null;
}

export interface WebUiArtifact {
  name: string;
  path: string;
  size: number;
}

/** 用例失败点在 spec 文件里的位置——比让用户读堆栈找行号有用得多。 */
export interface WebUiErrorLocation {
  file?: string;
  line?: number;
  column?: number;
}

export interface WebUiAttachment {
  name: string;
  contentType?: string;
  /** 相对运行目录的路径；配合 run.share_sig 即可直接取回文件 */
  path?: string;
}

export interface WebUiTestRow {
  id?: string;
  title: string;
  fullTitle: string;
  file?: string;
  line?: number;
  tags?: string[];
  projectName?: string;
  status: string;
  duration: number;
  retry?: number;
  error?: string;
  errorLocation?: WebUiErrorLocation;
  /** spec 里 console.log 的输出（侦察页面结构时用） */
  stdout?: string;
  stderr?: string;
  annotations?: { type: string; description?: string }[];
  attachments?: WebUiAttachment[];
}

export interface WebUiReportStats {
  expected?: number;
  unexpected?: number;
  flaky?: number;
  skipped?: number;
  duration?: number;
  startTime?: string;
}

export interface WebUiScriptRun {
  id: string;
  script_id: string;
  status: string;
  exit_code: number | null;
  output: string | null;
  report: { stats?: WebUiReportStats; tests?: WebUiTestRow[] } | null;
  artifacts: WebUiArtifact[] | null;
  duration_ms: number | null;
  triggered_by: string;
  repair_attempt: number;
  runner_run_id: string | null;
  /** 取产物/报告用的只读签名（浏览器自己发的请求带不上自定义头） */
  share_sig?: string;
  /** 该次执行是否生成了官方 HTML 报告 */
  report_ready?: boolean;
  /** 产物清单元数据还在，但文件已被清理（人工/磁盘回收）——此时不能画缩略图 */
  artifacts_pruned?: boolean;
  /** 卡在 running 太久（进程被杀/容器重启），不该继续显示"运行中" */
  stale_running?: boolean;
  created_at: string | null;
  script_name?: string | null;
}

export interface WebUiStats {
  window_days: number;
  scripts: number;
  runs: number;
  cases: number;
  expected: number;
  unexpected: number;
  skipped: number;
  pass_rate: number | null;
  avg_duration_ms: number;
  trend: {
    date: string;
    runs: number;
    expected: number;
    unexpected: number;
    skipped: number;
    pass_rate: number | null;
    avg_duration_ms: number;
  }[];
  top_failures: { title: string; count: number }[];
}

export interface WebUiRepairEntry {
  version: number;
  error: string;
  at: string;
  /** 自修复前的 spec 全文（用于看「AI 改了哪几行」） */
  before?: string;
  after?: string;
}

/** 执行中的实时进度：由 sidecar 边跑边写的 progress.ndjson + stdout.log 聚合而来 */
export interface WebUiRunProgress {
  run_id: string;
  running: boolean;
  stale: boolean;
  elapsed_ms: number;
  total: number | null;
  done: number;
  passed: number;
  failed: number;
  skipped: number;
  started: boolean;
  events: {
    event: string;
    title?: string;
    fullTitle?: string;
    status?: string;
    duration?: number;
    retry?: number;
    at?: number;
  }[];
  log_tail: string;
}

export interface PlaywrightRunnerStatus {
  available: boolean;
  error?: string;
  hint?: string;
  version?: string;
  browsers?: string[];
  runner_url?: string;
}

export function useWebUiScripts() {
  return useSWR("/web-ui-auto/scripts", () => fetcher<WebUiScript[]>("/web-ui-auto/scripts"));
}

export function useWebUiScriptRuns(scriptId: string | null, refreshMs = 0) {
  return useSWR(scriptId ? `/web-ui-auto/scripts/${scriptId}/runs` : null, () =>
    fetcher<WebUiScriptRun[]>(`/web-ui-auto/scripts/${scriptId}/runs`),
    refreshMs ? { refreshInterval: refreshMs } : undefined
  );
}

/** 全局执行记录（跨脚本），页面底部「最近执行」用。 */
export function useWebUiRuns(
  options: { scriptId?: string; status?: string; limit?: number } = {},
  // 允许按最新数据决定轮询间隔：有执行在跑时快轮询，空闲时慢下来。
  refreshMs: number | ((data?: WebUiScriptRun[]) => number) = 0,
) {
  const params = new URLSearchParams();
  if (options.scriptId) params.set("script_id", options.scriptId);
  if (options.status) params.set("status", options.status);
  params.set("limit", String(options.limit ?? 50));
  const key = `/web-ui-auto/runs?${params.toString()}`;
  const interval = refreshMs as number | ((data?: WebUiScriptRun[]) => number);
  return useSWR(key, () => fetcher<WebUiScriptRun[]>(key),
    refreshMs ? { refreshInterval: interval, revalidateOnFocus: false } : undefined);
}

/** 每个脚本的最近一次执行（用例库的「最近结果」列）。 */
export function useWebUiLatestRuns(refreshMs: number | ((data?: WebUiScriptRun[]) => number) = 0) {
  const key = "/web-ui-auto/runs?latest_per_script=true&limit=200";
  return useSWR(key, () => fetcher<WebUiScriptRun[]>(key),
    refreshMs ? { refreshInterval: refreshMs, revalidateOnFocus: false } : undefined);
}

export function useWebUiStats(days = 14, refreshMs = 0) {
  const key = `/web-ui-auto/stats/overview?days=${days}`;
  return useSWR(key, () => fetcher<WebUiStats>(key),
    refreshMs ? { refreshInterval: refreshMs } : undefined);
}

/** 执行中的实时进度；直到跑完前每 2 秒轮询一次。 */
export function useWebUiRunProgress(runId: string | null, enabled = true, refreshMs = 2000) {
  const key = runId && enabled ? `/web-ui-auto/runs/${runId}/progress` : null;
  return useSWR(key, () => fetcher<WebUiRunProgress>(key as string), {
    refreshInterval: refreshMs,
    revalidateOnFocus: false,
  });
}

/** 单条脚本详情（含源码与修复历史），编辑器用。 */
export function useWebUiScriptDetail(scriptId: string | null) {
  return useSWR(scriptId ? `/web-ui-auto/scripts/${scriptId}` : null, () =>
    fetcher<WebUiScript>(`/web-ui-auto/scripts/${scriptId}`)
  );
}

export function usePlaywrightStatus() {
  return useSWR("/web-ui-auto/status", () => fetcher<PlaywrightRunnerStatus>("/web-ui-auto/status"), {
    refreshInterval: 15000,
  });
}

// --- Web-UI 自动化的写操作 ---------------------------------------------------

export function createWebUiScript(payload: Record<string, unknown>) {
  return apiClient.post<WebUiScript>("/web-ui-auto/scripts", payload).then((r) => r.data);
}

export function updateWebUiScript(scriptId: string, payload: Record<string, unknown>) {
  return apiClient.put<WebUiScript>(`/web-ui-auto/scripts/${scriptId}`, payload).then((r) => r.data);
}

export function deleteWebUiScript(scriptId: string) {
  return apiClient.delete(`/web-ui-auto/scripts/${scriptId}`);
}

export function runWebUiScript(scriptId: string, autoRepair?: boolean) {
  const body = autoRepair === undefined ? {} : { auto_repair: autoRepair };
  return apiClient.post<{ started: boolean; max_repair: number }>(
    `/web-ui-auto/scripts/${scriptId}/run`, body).then((r) => r.data);
}

export function batchRunWebUiScripts(payload: {
  script_ids?: string[]; module?: string; auto_repair?: boolean;
}) {
  return apiClient.post<{ queued: number; scripts: { id: string; name: string }[] }>(
    "/web-ui-auto/scripts/batch-run", payload).then((r) => r.data);
}

export function generateWebUiSpec(payload: {
  intent: string; name: string; target_url?: string; module?: string;
  extra_requirements?: string; save?: boolean;
}) {
  return apiClient.post<{ content: string; target_url: string; script?: WebUiScript }>(
    "/web-ui-auto/generate", payload).then((r) => r.data);
}

/** 产物直链：浏览器自己发请求，所以带的是签名而不是 token。 */
export function webUiArtifactUrl(run: Pick<WebUiScriptRun, "id" | "share_sig">, path: string) {
  const encoded = path.split("/").map(encodeURIComponent).join("/");
  return `${apiV2Url(`/web-ui-auto/artifact/${run.id}/${encoded}`)}?sig=${run.share_sig ?? ""}`;
}

/** 官方 HTML 报告入口（签名放在路径里，报告内部的相对资源会自动带上）。 */
export function webUiReportUrl(run: Pick<WebUiScriptRun, "id" | "share_sig">) {
  return apiV2Url(`/web-ui-auto/report/${run.id}/${run.share_sig ?? ""}/index.html`);
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

/** Langfuse 测评追踪配置（设置页）；secret 以 ******** 掩码回显。 */
export function useLangfuseSettings() {
  return useSWR("/settings/langfuse", () =>
    fetcher<Record<string, string | null>>("/settings/langfuse")
  );
}

export interface LangfuseTestResult {
  ok: boolean;
  error?: string;
  latency_ms?: number;
  host?: string;
  project_id?: string | null;
  project_name?: string | null;
  organization?: string | null;
  projects?: number;
}

/** 按表单里的值探活（可先验后存，避免把错 key 存进去导致测评静默不上报）。 */
export function testLangfuseConnection(values: Record<string, string>) {
  return apiClient
    .post<LangfuseTestResult>("/settings/langfuse/test", { values })
    .then((r) => r.data);
}

/** Langfuse 监控配置（日常对话链路，与测评分开的组织/项目）。 */
export function useMonitorLangfuseSettings() {
  return useSWR("/settings/langfuse-monitor", () =>
    fetcher<Record<string, string | null>>("/settings/langfuse-monitor")
  );
}

export function testMonitorLangfuseConnection(values: Record<string, string>) {
  return apiClient
    .post<LangfuseTestResult>("/settings/langfuse-monitor/test", { values })
    .then((r) => r.data);
}

export function usePlatformSettings() {
  return useSWR("/settings/platform", () => fetcher<Record<string, string | null>>("/settings/platform"));
}

// ---------------------------------------------------------------------------
// LLM 裁判（测评打分用的模型）
// ---------------------------------------------------------------------------

export interface JudgeSettings {
  /** 表单值（留空 = 继承主 LLM） */
  values: Record<string, string | null>;
  /** 解析后的实际生效端点——界面必须显示它，否则"留空"会被误读成"没配" */
  effective: {
    model: string;
    base_url: string;
    source: "judge" | "llm" | "deepseek";
    configured: boolean;
  };
}

export function useJudgeSettings() {
  return useSWR("/settings/judge", () => fetcher<JudgeSettings>("/settings/judge"));
}

export interface JudgeTestResult {
  ok: boolean;
  error?: string;
  latency_ms?: number;
  model?: string;
  base_url?: string;
  source?: "judge" | "llm" | "deepseek";
  /** 自检走的是真实打分通道（JSON 模式），所以这里能拿到一份真实判定 */
  verdict?: { raw: string; score: number; rationale: string };
}

/** 按表单里的值真发一次 chat/completions（先验后存，配错会让整批用例变执行异常）。 */
export function testJudgeConnection(values: Record<string, string>) {
  return apiClient
    .post<JudgeTestResult>("/settings/judge/test", { values })
    .then((r) => r.data);
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
  ok: boolean;
  latency_ms?: number;
  error?: string;
  model?: string;
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
  /** 配置的 exe 是否真的在盘上（与 available 区分：不在盘上 = 该安装了） */
  exe_present?: boolean;
  projects: CbmProject[];
  graph_daemon: { up: boolean; port: number };
  /** 平台自管安装状态（官方 release，见 services/cbm_install.py） */
  install?: {
    managed_dir?: string;
    installed_version?: string | null;
    target_version?: string;
    asset?: string;
    supported?: boolean;
    upgradable?: boolean;
  };
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
  auto_analyze: boolean;
  last_commit: string | null;
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
  analyze_enabled: boolean;
  next_run: string | null;
}

/** 一次「增量影响分析」的产物（无头 codebase_agent 的报告）。 */
export interface CbmImpactReport {
  id: string;
  repo_id: string;
  repo_path: string;
  repo_name: string;
  index_run_id: string | null;
  trigger: string;
  status: "running" | "success" | "failed" | string;
  model: string | null;
  summary: string | null;
  counts: { added?: number; modified?: number; deleted?: number; files_total?: number };
  changes: {
    added: string[];
    modified: string[];
    deleted: string[];
    truncated: boolean;
    git: { base?: string; head?: string; name_status?: string[]; stat?: string } | null;
  };
  file_path: string | null;
  error: string | null;
  created_at: string | null;
  /** 仅详情接口返回 */
  content_md?: string;
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

/** 影响报告列表；有报告在生成中就加快轮询。 */
export function useCbmImpactReports(limit = 50, repoId?: string) {
  const key = `/codebase/impact-reports?limit=${limit}${repoId ? `&repo_id=${repoId}` : ""}`;
  return useSWR(key, () => fetcher<{ success: boolean; reports: CbmImpactReport[] }>(key), {
    refreshInterval: (latest?: { reports: CbmImpactReport[] }) =>
      latest?.reports?.some((r) => r.status === "running") ? 3000 : 15000,
  });
}

export function fetchCbmImpactReport(reportId: string) {
  return apiClient
    .get<{ success: boolean; report: CbmImpactReport }>(`/codebase/impact-reports/${reportId}`)
    .then((r) => (r.data.success ? r.data.report : null));
}

export function deleteCbmImpactReport(reportId: string) {
  return apiClient.delete(`/codebase/impact-reports/${reportId}`);
}

/** 手动对单个仓库跑一次影响分析（后台执行；即使本轮无变更也跑）。 */
export function triggerCbmAnalyze(repoId: string) {
  return apiClient
    .post<{ success: boolean; data: { started: boolean } }>(
      `/codebase/repos/${repoId}/analyze`, {})
    .then((r) => r.data);
}

// --- Eval (测评模块, Langfuse 闭环) -----------------------------------------

export interface EvalScore {
  name: string;
  value: number | string | boolean;
  data_type: string;
  comment?: string | null;
}

export interface EvalCase {
  id: string;
  item_id: string;
  instruction: string | null;
  trace_id: string | null;
  thread_id: string | null;
  status: string;
  error: string | null;
  duration_ms: number | null;
  scores: EvalScore[];
  tool_names: string[];
  evidence: Array<{ name: string; path: string; size: number }>;
}

export interface EvalBatch {
  id: string;
  dataset: string;
  run_name: string;
  agent: string;
  release: string | null;
  status: string;
  gate_expression: string | null;
  gate_passed: boolean | null;
  gate_output: string | null;
  total_cases: number;
  scored_cases: number;
  failed_cases: number;
  /** 已落库的用例数（跑一条落一条）；进度显示用它，而不是 scored_cases */
  done_cases: number;
  /** 记录写着"运行中"但执行进程已不在（容器重启/被 kill） */
  stale: boolean;
  averages: Record<string, number>;
  duration_ms: number | null;
  langfuse_host: string | null;
  created_at: string | null;
  output?: string | null;
}

/** 执行中批次的实时现场（/eval/batches/{id}/progress）。 */
export interface EvalBatchProgress {
  batch_id: string;
  status: string;
  running: boolean;
  stale: boolean;
  started: boolean;
  dataset: string | null;
  agent: string | null;
  total: number | null;
  done: number;
  passed: number;
  failed: number;
  elapsed_ms: number;
  /** 此刻正在跑的用例（并发 >1 时可能多条） */
  active: Array<{ item_id: string; elapsed_ms: number }>;
  /** 按时间排序的活动流：用例开始 / 模型与工具调用 / 用例结束 */
  activity: Array<{
    event: string;
    ts: number;
    item_id?: string;
    text?: string;
    status?: string;
    duration_ms?: number;
    scores?: Array<{ name: string; value: unknown; comment?: string }>;
    error?: string | null;
  }>;
  terminal: string | null;
  terminal_status: string | null;
  summary: string | null;
  heartbeat_age_s: number | null;
  log_tail: string;
}

export interface EvalDatasetInfo {
  file: string;
  name?: string;
  description?: string;
  agent?: string;
  items?: number;
  has_judge?: boolean;
  gate_hint?: string | null;
  error?: string;
}

/** 评测集编辑器用的结构化形状（与 datasets/*.yaml 一一对应）。 */
export interface EvalDatasetDraftItem {
  id: string;
  input: string;
  expected?: {
    contains?: string[];
    not_contains?: string[];
    tools?: { sequence: string[]; mode: "subsequence" | "exact" };
    max_tool_errors?: number | null;
    evidence?: string | null;
  } | null;
  judge?: { criteria: string; pass_threshold: number } | null;
  metadata?: Record<string, unknown>;
}

export interface EvalDatasetDetail {
  file: string;
  name: string;
  description?: string | null;
  agent: string;
  items: EvalDatasetDraftItem[];
  gate_hint?: string | null;
  /** 磁盘上的原始 YAML（只读展示，方便手改对照） */
  raw: string;
}

export interface EvalStatus {
  langfuse: {
    enabled: boolean; host: string; reachable?: boolean; organizations?: number;
    /** 界面路由前缀需要它（/project/<id>/traces/<traceId>） */
    project_id?: string | null;
  };
  judge: {
    model: string; base_url: string; configured: boolean;
    /** judge = 独立配置；llm / deepseek = 继承主 LLM（界面要说出来） */
    source?: "judge" | "llm" | "deepseek";
    explicit_model?: string;
  };
  datasets_dir: string;
}

export function useEvalStatus() {
  return useSWR("/eval/status", () => fetcher<EvalStatus>("/eval/status"), {
    refreshInterval: 30000,
  });
}

export function useEvalDatasets() {
  return useSWR("/eval/datasets", () => fetcher<EvalDatasetInfo[]>("/eval/datasets"));
}

/** 单个评测集的详情（含用例结构与原始 YAML），编辑器用。 */
export function useEvalDatasetDetail(file: string | null, enabled = true) {
  const key = file && enabled ? `/eval/datasets/${encodeURIComponent(file)}` : null;
  return useSWR(key, () => fetcher<EvalDatasetDetail>(key as string), {
    revalidateOnFocus: false,
  });
}

/** 新建（file=null）或保存评测集；页面里统一走这一个入口。 */
export async function saveEvalDataset(
  file: string | null, payload: Omit<EvalDatasetDetail, "raw" | "gate_hint">,
) {
  const body = { ...payload, file: payload.file ?? file ?? undefined };
  if (file) return apiClient.put<EvalDatasetDetail>(`/eval/datasets/${encodeURIComponent(file)}`, body);
  return apiClient.post<EvalDatasetDetail>("/eval/datasets", body);
}

export async function deleteEvalDataset(file: string) {
  return apiClient.delete(`/eval/datasets/${encodeURIComponent(file)}`);
}

// --- AI 生成测评集（数据来源：沉淀的历史对话）---------------------------------

export interface EvalSource {
  thread_id: string;
  title: string;
  agent: string;
  messages: number;
  updated_at: string | null;
}

export interface EvalGenerateResult {
  dataset: Omit<EvalDatasetDetail, "raw" | "gate_hint">;
  sources: { thread_id: string; title: string; agent: string; messages: number }[];
  model: string;
  note: string;
}

/** 可作为生成来源的历史对话（只列有消息的会话，可按 agent 过滤） */
export function useEvalSources(agent?: string) {
  const key = `/eval/sources${agent ? `?agent=${encodeURIComponent(agent)}` : ""}`;
  return useSWR(key, () => fetcher<EvalSource[]>(key));
}

/** 把历史对话交给主 LLM 提炼成评测集草稿（不落盘，回页面微调后再保存） */
export async function generateEvalDataset(body: {
  thread_ids: string[];
  agent: string;
  count: number;
  focus?: string;
  name?: string;
}) {
  const response = await apiClient.post<EvalGenerateResult>("/eval/datasets/generate", body);
  return response.data;
}

export function useEvalBatches() {
  // 有批次真在跑时快轮询（列表里的完成数、状态要跟着动），空闲时慢下来。
  // 疑似中断（stale）的行不算"在跑"——否则一条永远不会收敛的记录会让列表
  // 一直以 3 秒的节奏打接口。
  return useSWR("/eval/batches", () => fetcher<EvalBatch[]>("/eval/batches"), {
    refreshInterval: (data?: EvalBatch[]) =>
      (data ?? []).some((b) => b.status === "running" && !b.stale) ? 3000 : 15000,
    revalidateOnFocus: false,
  });
}

export function useEvalBatch(batchId: string | null) {
  // 运行中必须轮询：用例是跑一条落一条的，不刷新就看不到新落下来的行。
  // 跑完那一刻由 BatchDialog 主动 mutate 一次（这里返回 0 就停了）。
  return useSWR(batchId ? `/eval/batches/${batchId}` : null, () =>
    fetcher<EvalBatch & { cases: EvalCase[] }>(`/eval/batches/${batchId}`), {
    refreshInterval: (data?: EvalBatch) =>
      data?.status === "running" && !data.stale ? 2000 : 0,
    revalidateOnFocus: false,
  });
}

/** 批次执行中的实时进度（里程碑式事件 + 日志尾）。 */
export function useEvalBatchProgress(batchId: string | null, enabled = true, refreshMs = 2000) {
  const key = batchId && enabled ? `/eval/batches/${batchId}/progress` : null;
  return useSWR(key, () => fetcher<EvalBatchProgress>(key as string), {
    refreshInterval: refreshMs,
    revalidateOnFocus: false,
  });
}
