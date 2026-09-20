"use client";

/**
 * Web-UI 自动化（Playwright CLI）
 *
 * 页面组织原则：**执行结果先于用例清单**。用户打开这一页通常是为了回答
 * 「现在质量怎么样 / 刚才那次为什么挂」，所以顶部是概览与趋势，中部是用例库，
 * 底部是跨脚本的最近执行；每条执行都能下钻到用例明细与截图/trace 存证。
 */

import React, { useMemo, useState } from "react";
import Link from "next/link";
import { PageHeader, StatusBadge, EmptyState } from "@/app/components/ui-patterns";
import {
  useWebUiScripts, useWebUiScriptRuns, useWebUiRuns, useWebUiLatestRuns,
  useWebUiStats, usePlaywrightStatus,
  batchRunWebUiScripts, deleteWebUiScript, runWebUiScript,
  type WebUiScript, type WebUiScriptRun,
} from "@/lib/api/useNewModules";
import { apiClient } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Camera, Loader2, Pencil, Play, PlayCircle, Plus, RefreshCw, Trash2,
} from "lucide-react";
import { toast } from "sonner";
import { RunOverview } from "@/app/components/web-ui-auto/RunTrend";
import { RunDetailDialog } from "@/app/components/web-ui-auto/RunDetail";
import { ScriptEditorDialog } from "@/app/components/web-ui-auto/ScriptEditor";

const DEFAULT_TARGET = "https://m.douban.com/movie/";

const TRIGGER_LABEL: Record<string, string> = {
  manual: "手动",
  batch: "批量",
  self_repair: "自修复",
  schedule: "定时",
};

/** options JSON 里的设备/浏览器，列表需要显示「这条跑在什么环境上」。 */
function scriptOptions(script: WebUiScript): { device: string; browsers: string[] } {
  const raw = (script as { options?: unknown }).options;
  let parsed: Record<string, unknown> = {};
  if (raw && typeof raw === "object") parsed = raw as Record<string, unknown>;
  else if (typeof raw === "string") {
    try { parsed = JSON.parse(raw) as Record<string, unknown>; } catch { parsed = {}; }
  }
  return {
    device: typeof parsed.device === "string" && parsed.device ? parsed.device : "桌面",
    browsers: Array.isArray(parsed.browsers) ? parsed.browsers.map(String) : [],
  };
}

/** 每条用例最近一次执行的结果（列表里直接给结论，不用点进去）。 */
function latestRunOf(runs: WebUiScriptRun[] | undefined): WebUiScriptRun | null {
  if (!runs || runs.length === 0) return null;
  return runs.reduce((latest, run) =>
    (run.created_at ?? "") > (latest.created_at ?? "") ? run : latest);
}

function runSummary(run: WebUiScriptRun): string {
  const stats = run.report?.stats ?? {};
  const passed = stats.expected ?? 0;
  const failed = stats.unexpected ?? 0;
  if (passed + failed === 0) return "—";
  return `${passed}/${passed + failed}`;
}

function ScriptRunsDialog({ script, onClose, onOpenRun }: {
  script: WebUiScript;
  onClose: () => void;
  onOpenRun: (run: WebUiScriptRun) => void;
}) {
  const runs = useWebUiScriptRuns(script.id, 5000);
  const rows = runs.data ?? [];
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base">
            {script.name} · 执行历史
            <Button size="sm" variant="ghost" className="ml-auto"
                    onClick={() => runs.mutate()}>
              <RefreshCw className="h-3.5 w-3.5" />
            </Button>
          </DialogTitle>
        </DialogHeader>
        {rows.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">暂无执行记录</p>
        ) : (
          <div className="max-h-[60vh] overflow-y-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>结果</TableHead>
                  <TableHead>时间</TableHead>
                  <TableHead>用例</TableHead>
                  <TableHead>耗时</TableHead>
                  <TableHead>触发</TableHead>
                  <TableHead className="text-right">证据</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((run) => (
                  <TableRow key={run.id} className="cursor-pointer"
                            onClick={() => onOpenRun(run)}>
                    <TableCell><StatusBadge status={run.status} fallbackLabel={run.status} /></TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {run.created_at ? new Date(run.created_at).toLocaleString("zh-CN") : "-"}
                    </TableCell>
                    <TableCell className="tabular-nums">
                      {run.status === "running" ? <span className="text-primary">进行中…</span> : runSummary(run)}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {run.duration_ms != null ? `${(run.duration_ms / 1000).toFixed(1)}s` : "-"}
                    </TableCell>
                    <TableCell>
                      {run.triggered_by === "self_repair" ? (
                        <Badge variant="secondary" className="font-normal">
                          自修复 #{run.repair_attempt}
                        </Badge>
                      ) : (
                        <span className="text-xs text-muted-foreground">
                          {TRIGGER_LABEL[run.triggered_by] ?? run.triggered_by}
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <span className="text-xs text-primary">查看 →</span>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default function WebUiAutoPage() {
  const runner = usePlaywrightStatus();
  const scripts = useWebUiScripts();
  const stats = useWebUiStats(14, 30000);
  // 有执行在跑时快轮询（用户正盯着进度看），空闲时慢下来
  const globalRuns = useWebUiRuns(
    { limit: 20 },
    (latest) => (latest?.some((run) => run.status === "running") ? 2500 : 10000),
  );
  // 「最近结果」列必须用后端聚合出来的"每个脚本最近一次"：
  // 拿最近 N 条执行在前端去重，某个脚本最近没跑就会显示成"未执行过"
  const latestRunsQuery = useWebUiLatestRuns(
    (latest) => (latest?.some((run) => run.status === "running") ? 2500 : 15000),
  );

  const [editor, setEditor] = useState<{ open: boolean; scriptId: string | null }>({
    open: false, scriptId: null,
  });
  const [runsFor, setRunsFor] = useState<WebUiScript | null>(null);
  const [detailRun, setDetailRun] = useState<WebUiScriptRun | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [batching, setBatching] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [pendingDelete, setPendingDelete] = useState<WebUiScript | null>(null);
  const [query, setQuery] = useState("");
  const [moduleFilter, setModuleFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [sortBy, setSortBy] = useState<"updated" | "name" | "worst">("updated");
  const [shotUrl, setShotUrl] = useState(DEFAULT_TARGET);
  const [shooting, setShooting] = useState(false);

  // 每条用例最近一次执行：列表里直接显示结论，省掉「点进去才知道挂没挂」
  const latestRuns = useMemo(() => {
    const map = new Map<string, WebUiScriptRun>();
    for (const run of latestRunsQuery.data ?? []) {
      if (!map.has(run.script_id)) map.set(run.script_id, run);
    }
    return map;
  }, [latestRunsQuery.data]);

  const modules = useMemo(() => {
    const set = new Set<string>();
    for (const script of scripts.data ?? []) if (script.module) set.add(script.module);
    return [...set].sort();
  }, [scripts.data]);

  const visibleScripts = useMemo(() => {
    let rows = scripts.data ?? [];
    const keyword = query.trim().toLowerCase();
    if (keyword) {
      rows = rows.filter((s) =>
        s.name.toLowerCase().includes(keyword)
        || (s.module ?? "").toLowerCase().includes(keyword)
        || (s.target_url ?? "").toLowerCase().includes(keyword));
    }
    if (moduleFilter) rows = rows.filter((s) => s.module === moduleFilter);
    if (statusFilter) rows = rows.filter((s) => s.status === statusFilter);
    const sorted = [...rows];
    if (sortBy === "name") {
      sorted.sort((a, b) => a.name.localeCompare(b.name, "zh-CN"));
    } else if (sortBy === "worst") {
      // 先看最近失败的，再按更新时间
      sorted.sort((a, b) => {
        const sa = latestRuns.get(a.id)?.status === "passed" ? 1 : 0;
        const sb = latestRuns.get(b.id)?.status === "passed" ? 1 : 0;
        if (sa !== sb) return sa - sb;
        return (b.updated_at ?? "").localeCompare(a.updated_at ?? "");
      });
    } else {
      sorted.sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? ""));
    }
    return sorted;
  }, [scripts.data, query, moduleFilter, statusFilter, sortBy, latestRuns]);

  // 加载中不能直接摆「未就绪」——首屏那一秒会把用户吓一跳，也让"到底坏没坏"看不出来
  const statusBadge = runner.data === undefined ? (
    <Badge variant="secondary" className="font-normal">检测执行器…</Badge>
  ) : runner.data.available ? (
    <Badge className="bg-success/12 font-normal text-success">
      Playwright 就绪 · {runner.data.version ?? "CLI"}
    </Badge>
  ) : (
    <Badge variant="destructive">Playwright 未就绪</Badge>
  );

  const screenshot = async () => {
    if (!shotUrl.trim()) return;
    setShooting(true);
    try {
      // 执行器返回的是驼峰 dataUri（tools/playwright-runner/server.mjs）。
      // 这里曾读 data_uri，导致"截图后自动开新标签"从来没触发过，且不报错。
      const res = await apiClient.post<{ path: string; dataUri?: string }>(
        "/web-ui-auto/screenshot", { url: shotUrl.trim(), full_page: true });
      toast.success(`截图已保存：${res.data.path}`);
      if (res.data.dataUri) window.open(res.data.dataUri, "_blank");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "截图失败");
    } finally {
      setShooting(false);
    }
  };

  const runScript = async (id: string) => {
    setBusyId(id);
    try {
      await runWebUiScript(id);
      // 执行记录是先落 running 再开跑的，所以很快就能在列表里看到「运行中」并可点进进度
      toast.success("已开始执行，可在列表的「最近结果」或下方「最近执行」里实时看进度");
      setTimeout(() => {
        scripts.mutate(); globalRuns.mutate(); latestRunsQuery.mutate(); setBusyId(null);
      }, 1200);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "启动失败");
      setBusyId(null);
    }
  };

  const runSelected = async () => {
    const ids = [...selected];
    if (ids.length === 0) { toast.error("先勾选要执行的用例"); return; }
    setBatching(true);
    try {
      const result = await batchRunWebUiScripts({ script_ids: ids });
      toast.success(`已排队 ${result.queued} 条用例，将按顺序依次执行`);
      setTimeout(() => { scripts.mutate(); globalRuns.mutate(); stats.mutate(); setBatching(false); }, 5000);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "批量执行失败");
      setBatching(false);
    }
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    try {
      await deleteWebUiScript(pendingDelete.id);
      toast.success("已删除");
      setPendingDelete(null);
      setSelected(new Set());
      scripts.mutate();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "删除失败");
    }
  };

  const toggleAll = (checked: boolean) => {
    setSelected(checked ? new Set(visibleScripts.map((s) => s.id)) : new Set());
  };

  const allChecked = visibleScripts.length > 0
    && visibleScripts.every((s) => selected.has(s.id));

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-6xl px-6 py-8 lg:px-8">
        <div className="flex flex-col gap-5">
          <PageHeader
            title="Web-UI 自动化（Playwright CLI）"
            description={
              <>
                浏览器端 UI 用例：定位 → 操作 → 断言 → 截图/trace 存证，执行引擎为官方 Playwright CLI。
                也可以去<Link href="/chat" className="text-primary hover:underline">聊天页</Link>
                让通用测试助手帮你对话式设计与调试用例（它会自己分诊到 Web-UI 能力）。
              </>
            }
            actions={<div className="flex items-center gap-2">{statusBadge}</div>}
          />

          {!runner.data?.available && runner.data && (
            <Card className="border-warning/40 bg-warning/10 p-3 text-sm text-warning">
              {runner.data.error ?? "Playwright 执行器不可用"}
              {runner.data.hint && <div className="mt-1 text-xs opacity-80">{runner.data.hint}</div>}
            </Card>
          )}

          <RunOverview stats={stats.data} days={14} />

          {/* 快捷截图（直接调 playwright screenshot CLI） */}
          <Card className="p-4">
            <div className="mb-2 flex items-center gap-1.5 text-sm font-medium">
              <Camera className="h-4 w-4" />网页截图核验
            </div>
            <div className="flex gap-2">
              <Input value={shotUrl} onChange={(e) => setShotUrl(e.target.value)}
                     placeholder={DEFAULT_TARGET}
                     onKeyDown={(e) => e.key === "Enter" && screenshot()} />
              <Button variant="outline" onClick={screenshot} disabled={shooting} className="shrink-0">
                {shooting ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                  : <Camera className="mr-1.5 h-4 w-4" />}
                截图
              </Button>
            </div>
          </Card>

          {/* 用例库 */}
          <Card className="p-0">
            <div className="flex flex-wrap items-center gap-2 border-b px-4 py-2.5">
              <span className="text-sm font-medium">Playwright 用例</span>
              <Badge variant="secondary" className="font-normal">
                {visibleScripts.length}/{scripts.data?.length ?? 0}
              </Badge>
              <div className="ml-auto flex flex-wrap items-center gap-2">
                <Input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="搜索名称 / 模块 / 站点"
                  className="h-8 w-[190px] text-xs"
                />
                <select
                  value={moduleFilter}
                  onChange={(e) => setModuleFilter(e.target.value)}
                  className="h-8 rounded-md border bg-transparent px-2 text-xs"
                >
                  <option value="">全部模块</option>
                  {modules.map((m) => <option key={m} value={m}>{m}</option>)}
                </select>
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="h-8 rounded-md border bg-transparent px-2 text-xs"
                >
                  <option value="">全部状态</option>
                  <option value="active">启用</option>
                  <option value="draft">草稿</option>
                  <option value="broken">异常</option>
                  <option value="archived">归档</option>
                </select>
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
                  className="h-8 rounded-md border bg-transparent px-2 text-xs"
                >
                  <option value="updated">按更新时间</option>
                  <option value="worst">按最近失败优先</option>
                  <option value="name">按名称</option>
                </select>
                <Button size="sm" variant="outline" onClick={() => scripts.mutate()}>
                  <RefreshCw className="mr-1.5 h-3.5 w-3.5" />刷新
                </Button>
                <Button size="sm" onClick={() => setEditor({ open: true, scriptId: null })}>
                  <Plus className="mr-1.5 h-4 w-4" />新建 / AI 生成
                </Button>
              </div>
            </div>

            {selected.size > 0 && (
              <div className="flex items-center gap-2 border-b bg-muted/40 px-4 py-2 text-xs">
                已选 {selected.size} 条
                <Button size="sm" variant="outline" onClick={runSelected} disabled={batching}>
                  {batching ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                    : <PlayCircle className="mr-1.5 h-3.5 w-3.5" />}
                  批量执行
                </Button>
                <button type="button" className="text-muted-foreground hover:underline"
                        onClick={() => setSelected(new Set())}>
                  取消选择
                </button>
              </div>
            )}

            {scripts.isLoading ? (
              <div className="flex items-center justify-center py-16 text-sm text-muted-foreground">
                加载中…
              </div>
            ) : visibleScripts.length === 0 ? (
              <EmptyState
                title={scripts.data?.length ? "没有匹配的用例" : "暂无用例"}
                description={scripts.data?.length
                  ? "换个关键词或清空筛选条件"
                  : "点「新建 / AI 生成」手写或用一句话生成，也可以到聊天页让智能体设计用例"}
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-8">
                      <input type="checkbox" checked={allChecked}
                             onChange={(e) => toggleAll(e.target.checked)} />
                    </TableHead>
                    <TableHead>用例</TableHead>
                    <TableHead>模块</TableHead>
                    <TableHead>运行环境</TableHead>
                    <TableHead>最近结果</TableHead>
                    <TableHead>状态</TableHead>
                    <TableHead>更新时间</TableHead>
                    <TableHead className="text-right">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {visibleScripts.map((script) => {
                    const latest = latestRuns.get(script.id);
                    const isRunning = latest?.status === "running" && !latest.stale_running;
                    const { device, browsers } = scriptOptions(script);
                    return (
                      <TableRow key={script.id}>
                        <TableCell>
                          <input
                            type="checkbox"
                            checked={selected.has(script.id)}
                            onChange={(e) => setSelected((prev) => {
                              const next = new Set(prev);
                              if (e.target.checked) next.add(script.id);
                              else next.delete(script.id);
                              return next;
                            })}
                          />
                        </TableCell>
                        <TableCell className="max-w-[280px]">
                          <button type="button" className="text-left"
                                  onClick={() => setEditor({ open: true, scriptId: script.id })}>
                            <span className="block truncate font-medium hover:underline">
                              {script.name}
                            </span>
                            <span className="block truncate text-[11px] text-muted-foreground">
                              v{script.version} · {script.spec_file}
                            </span>
                          </button>
                        </TableCell>
                        <TableCell className="text-xs">{script.module ?? "-"}</TableCell>
                        <TableCell className="text-xs">
                          <div className="flex flex-wrap items-center gap-1">
                            <span>{device}</span>
                            {browsers.length > 0 && (
                              <Badge variant="outline" className="px-1 py-0 text-[10px]">
                                {browsers.join("+")}
                              </Badge>
                            )}
                          </div>
                        </TableCell>
                        <TableCell>
                          {latest ? (
                            <button type="button" className="flex items-center gap-1.5"
                                    aria-label="查看最近一次执行"
                                    onClick={() => setDetailRun(latest)}>
                              {isRunning
                                ? <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
                                : null}
                              <StatusBadge
                                status={latest.stale_running ? "error" : latest.status}
                                fallbackLabel={latest.status} />
                              <span className="text-[11px] text-muted-foreground">
                                {isRunning
                                  ? "看进度 →"
                                  : latest.stale_running
                                    ? "疑似中断"
                                    : runSummary(latest)}
                                {!isRunning && latest.created_at
                                  ? ` · ${new Date(latest.created_at).toLocaleString("zh-CN", {
                                    month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit",
                                  })}`
                                  : ""}
                              </span>
                            </button>
                          ) : (
                            <span className="text-xs text-muted-foreground">未执行过</span>
                          )}
                        </TableCell>
                        <TableCell>
                          <StatusBadge status={script.status} fallbackLabel={script.status} />
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {script.updated_at
                            ? new Date(script.updated_at).toLocaleString("zh-CN")
                            : "-"}
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-1">
                            <Button size="sm" variant="outline" onClick={() => runScript(script.id)}
                                    disabled={busyId === script.id || isRunning}>
                              {busyId === script.id || isRunning
                                ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                                : <Play className="mr-1 h-3.5 w-3.5" />}
                              {isRunning ? "运行中" : "执行"}
                            </Button>
                            <Button size="sm" variant="ghost"
                                    onClick={() => setEditor({ open: true, scriptId: script.id })}>
                              <Pencil className="h-3.5 w-3.5" />
                            </Button>
                            <Button size="sm" variant="ghost" onClick={() => setRunsFor(script)}>
                              历史
                            </Button>
                            <Button size="sm" variant="ghost" onClick={() => setPendingDelete(script)}>
                              <Trash2 className="h-3.5 w-3.5 text-destructive" />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            )}
          </Card>

          {/* 跨脚本的最近执行 */}
          <Card className="p-0">
            <div className="flex items-center justify-between border-b px-4 py-2.5">
              <span className="text-sm font-medium">最近执行</span>
              <Button size="sm" variant="ghost" onClick={() => globalRuns.mutate()}>
                <RefreshCw className="mr-1.5 h-3.5 w-3.5" />刷新
              </Button>
            </div>
            {(globalRuns.data ?? []).length === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-muted-foreground">
                还没有执行记录
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>结果</TableHead>
                    <TableHead>用例脚本</TableHead>
                    <TableHead>用例</TableHead>
                    <TableHead>耗时</TableHead>
                    <TableHead>触发</TableHead>
                    <TableHead>时间</TableHead>
                    <TableHead className="text-right">证据</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(globalRuns.data ?? []).map((run) => (
                    <TableRow key={run.id}>
                      <TableCell><StatusBadge status={run.status} fallbackLabel={run.status} /></TableCell>
                      <TableCell className="max-w-[240px] truncate text-sm">
                        {run.script_name ?? "-"}
                      </TableCell>
                      <TableCell className="tabular-nums text-sm">{runSummary(run)}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {run.status === "running"
                          ? <span className="text-primary">进行中…</span>
                          : run.duration_ms != null
                            ? `${(run.duration_ms / 1000).toFixed(1)}s`
                            : "-"}
                      </TableCell>
                      <TableCell className="text-xs">
                        <span className="text-muted-foreground">{TRIGGER_LABEL[run.triggered_by] ?? run.triggered_by}</span>
                        {run.triggered_by === "self_repair" && (
                          <Badge variant="secondary" className="ml-1 font-normal">#{run.repair_attempt}</Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {run.created_at ? new Date(run.created_at).toLocaleString("zh-CN") : "-"}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button size="sm" variant="ghost" onClick={() => setDetailRun(run)}>
                          {run.status === "running" ? "查看进度" : `详情 / 截图${traceOrReport(run)}`}
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Card>
        </div>
      </div>

      {runsFor && (
        <ScriptRunsDialog
          script={runsFor}
          onClose={() => setRunsFor(null)}
          onOpenRun={(run) => { setRunsFor(null); setDetailRun(run); }}
        />
      )}

      {detailRun && (
        <RunDetailDialog
          run={detailRun}
          onClose={() => setDetailRun(null)}
          onFinished={() => {
            scripts.mutate();
            globalRuns.mutate();
            stats.mutate();
          }}
        />
      )}

      <ScriptEditorDialog
        open={editor.open}
        scriptId={editor.scriptId}
        onOpenChange={(open) => setEditor((prev) => ({ ...prev, open }))}
        onSaved={() => { scripts.mutate(); globalRuns.mutate(); stats.mutate(); }}
      />

      <AlertDialog open={pendingDelete !== null}
                   onOpenChange={(open) => !open && setPendingDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除「{pendingDelete?.name}」？</AlertDialogTitle>
            <AlertDialogDescription>
              会连同它的执行历史一起删除，且不可恢复。如果需要留档，先到执行历史里导出存证。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete}>删除</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function traceOrReport(run: WebUiScriptRun): string {
  // 产物已被清理的执行别再宣传"截图 / trace"，点开只会是空的
  if (run.artifacts_pruned) return "（存证已清理）";
  const parts: string[] = [];
  if (run.report_ready) parts.push("报告");
  if ((run.artifacts ?? []).some((a) => a.path.endsWith(".zip"))) parts.push("trace");
  return parts.length > 0 ? ` / ${parts.join(" + ")}` : "";
}
