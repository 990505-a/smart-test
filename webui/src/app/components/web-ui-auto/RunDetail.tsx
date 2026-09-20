"use client";

/**
 * 一次执行的详情：用例明细 + 失败定位 + 截图存证 + 产物 + 官方报告入口。
 *
 * 设计取向：**先给结论，再给证据**。默认只列用例与状态，点开某条才展开错误、
 * errorLocation（失败在 spec 第几行）、该条用例自己的 console 输出和失败截图——
 * 因为一次 10 条用例的执行里，用户 90% 的时间只关心挂掉那一两条。
 */

import React, { useMemo, useState } from "react";
import {
  AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Copy, ExternalLink,
  FileWarning, MinusCircle, Terminal,
} from "lucide-react";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/app/components/ui-patterns";
import {
  webUiArtifactUrl, webUiReportUrl, type WebUiScriptRun, type WebUiTestRow,
} from "@/lib/api/useNewModules";
import {
  ArtifactGallery, ArtifactsPrunedNotice, ArtifactThumb, ImageViewer, artifactKind,
} from "./ArtifactGallery";
import { RunProgressPanel } from "./RunProgressPanel";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

const STATUS_ICON: Record<string, React.ReactNode> = {
  passed: <CheckCircle2 className="h-4 w-4 text-emerald-600" />,
  failed: <AlertTriangle className="h-4 w-4 text-red-600" />,
  timedOut: <AlertTriangle className="h-4 w-4 text-red-600" />,
  interrupted: <FileWarning className="h-4 w-4 text-amber-600" />,
  skipped: <MinusCircle className="h-4 w-4 text-muted-foreground" />,
};

function Stat({ label, value, tone }: { label: string; value: React.ReactNode; tone?: string }) {
  return (
    <div className="rounded-md border px-2.5 py-1.5">
      <div className="text-[10px] text-muted-foreground">{label}</div>
      <div className={cn("text-sm font-medium", tone)}>{value}</div>
    </div>
  );
}

function TestRow({ run, test }: { run: WebUiScriptRun; test: WebUiTestRow }) {
  const [open, setOpen] = useState(test.status === "failed");
  const [lightbox, setLightbox] = useState<number | null>(null);
  const attachments = (test.attachments ?? []).filter((a) => a.path);
  const images = attachments.filter((a) => artifactKind(a.path!) === "image");
  const others = attachments.filter((a) => artifactKind(a.path!) !== "image");
  const location = test.errorLocation;

  return (
    <>
      <div className={cn("border-b last:border-b-0", open && "bg-muted/30")}>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex w-full items-start gap-2 px-3 py-2 text-left hover:bg-muted/40"
        >
          <span className="mt-0.5 shrink-0">
            {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
          </span>
          <span className="mt-0.5 shrink-0">{STATUS_ICON[test.status] ?? STATUS_ICON.skipped}</span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm">{test.fullTitle || test.title}</span>
            <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-muted-foreground">
              <span>{test.status}</span>
              <span>· {test.duration}ms</span>
              {test.projectName && <Badge variant="outline" className="px-1 py-0 text-[10px]">{test.projectName}</Badge>}
              {test.retry ? <span>· 第 {test.retry + 1} 次尝试</span> : null}
              {location?.file && (
                <span className="font-mono text-amber-700 dark:text-amber-500">
                  {location.file}:{location.line}
                </span>
              )}
              {test.tags?.map((tag) => (
                <Badge key={tag} variant="secondary" className="px-1 py-0 text-[10px]">{tag}</Badge>
              ))}
            </span>
          </span>
        </button>

        {open && (
          <div className="flex flex-col gap-2 px-3 pb-3 pl-9">
            {test.error && (
              <div>
                <div className="mb-1 text-[11px] font-medium text-red-600">失败原因</div>
                <pre className="max-h-56 overflow-y-auto whitespace-pre-wrap break-words rounded bg-destructive/10 p-2 text-[11px] text-destructive">
                  {test.error}
                </pre>
              </div>
            )}
            {!test.error && test.status === "passed" && (
              <p className="text-[11px] text-muted-foreground">该用例通过，无错误输出。</p>
            )}
            {test.stdout && (
              <details className="text-[11px]">
                <summary className="cursor-pointer text-muted-foreground">
                  spec 的控制台输出（console.log）
                </summary>
                <pre className="mt-1 max-h-48 overflow-y-auto whitespace-pre-wrap break-words rounded bg-muted p-2 text-[11px]">{test.stdout}</pre>
              </details>
            )}
            {images.length > 0 && (
              <div>
                <div className="mb-1 text-[11px] font-medium text-muted-foreground">
                  该用例的截图 {images.length} 张
                </div>
                <div className="flex flex-wrap gap-2">
                  {images.map((a, index) => (
                    <ArtifactThumb
                      key={a.path}
                      run={run}
                      path={a.path!}
                      onOpen={() => setLightbox(index)}
                    />
                  ))}
                </div>
              </div>
            )}
            {others.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {others.map((a) => (
                  <a key={a.path} href={webUiArtifactUrl(run, a.path!)} target="_blank" rel="noreferrer"
                     className="rounded border px-2 py-1 text-[11px] hover:bg-muted">
                    {a.name}（下载）
                  </a>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <ImageViewer
        run={run}
        paths={images.map((a) => a.path!)}
        index={lightbox}
        onIndex={setLightbox}
        onClose={() => setLightbox(null)}
      />
    </>
  );
}

export function RunDetailDialog({
  run, onClose, onFinished,
}: {
  run: WebUiScriptRun;
  onClose: () => void;
  /** 执行跑完那一刻通知外层刷新列表 */
  onFinished?: () => void;
}) {
  const [view, setView] = useState<"tests" | "artifacts" | "raw">("tests");
  const stats = run.report?.stats ?? {};
  const tests = useMemo(() => run.report?.tests ?? [], [run.report]);
  const failed = tests.filter((t) => t.status === "failed").length;

  const copyShare = async () => {
    try {
      await navigator.clipboard.writeText(webUiReportUrl(run));
      toast.success("报告分享链接已复制（浏览器直接打开即可，无需登录）");
    } catch {
      toast.error("复制失败，请手动复制浏览器地址栏链接");
    }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-5xl overflow-hidden p-0 sm:max-w-5xl">
        {/* min-w-0 是必须的：DialogContent 是 grid，grid item 默认 min-width:auto ——
            输出里那些超长的绝对路径会把卡片顶宽、正文画到卡片外面。 */}
        <div className="flex max-h-[88vh] w-full min-w-0 flex-col">
          {/* 头部：结论 */}
          <div className="flex flex-wrap items-center gap-2 border-b px-4 py-3">
            <StatusBadge status={run.status} fallbackLabel={run.status} />
            <span className="text-sm font-medium">{run.script_name ?? "执行详情"}</span>
            <span className="text-xs text-muted-foreground">
              {run.created_at ? new Date(run.created_at).toLocaleString("zh-CN") : "-"}
            </span>
            {run.triggered_by === "self_repair" && (
              <Badge variant="secondary" className="font-normal">
                AI 自修复第 {run.repair_attempt} 轮
              </Badge>
            )}
            <div className="ml-auto flex items-center gap-2">
              {run.report_ready && (
                <Button size="sm" variant="outline"
                        onClick={() => window.open(webUiReportUrl(run), "_blank")}>
                  <ExternalLink className="mr-1.5 h-3.5 w-3.5" />官方报告 / trace 回放
                </Button>
              )}
              <Button size="sm" variant="ghost" onClick={copyShare}>
                <Copy className="mr-1.5 h-3.5 w-3.5" />分享链接
              </Button>
            </div>
          </div>

          {/* 统计条 */}
          <div className="flex flex-wrap gap-2 border-b px-4 py-3">
            <Stat label="用例总数" value={tests.length} />
            <Stat label="通过" value={stats.expected ?? 0} tone="text-emerald-600" />
            <Stat label="失败" value={stats.unexpected ?? 0}
                  tone={stats.unexpected ? "text-red-600" : undefined} />
            {Boolean(stats.flaky) && <Stat label="不稳定" value={stats.flaky} tone="text-amber-600" />}
            {Boolean(stats.skipped) && <Stat label="跳过" value={stats.skipped} />}
            <Stat label="耗时"
                  value={run.duration_ms != null ? `${(run.duration_ms / 1000).toFixed(1)}s` : "-"} />
            <Stat label="退出码" value={run.exit_code ?? "-"} />
            {run.runner_run_id && (
              <Stat label="产物目录" value={
                <span className="font-mono text-[10px]">{run.runner_run_id.slice(-13)}</span>
              } />
            )}
          </div>

          {/* 视图切换（不用 Tabs 组件：这里只需要三个按钮） */}
          <div className="flex gap-1 border-b px-4 py-2">
            {([
              ["tests", `用例结果（${tests.length}）`],
              ["artifacts", `产物存证（${run.artifacts?.length ?? 0}）`],
              ["raw", "原始输出"],
            ] as const).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setView(key)}
                className={cn(
                  "rounded-md px-2.5 py-1 text-xs transition",
                  view === key ? "bg-muted font-medium" : "text-muted-foreground hover:bg-muted/60",
                )}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="min-w-0 flex-1 overflow-y-auto px-4 py-3">
            {/* 还在跑：先给实时进度，而不是"空表格 + 等刷新" */}
            {run.status === "running" && (
              <div className="mb-3">
                <RunProgressPanel run={run} onFinished={onFinished} />
              </div>
            )}
            <ArtifactsPrunedNotice run={run} />
            {view === "tests" && (
              tests.length === 0 ? (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  {run.status === "running"
                    ? "执行中的实时进度见上方；跑完后每条用例的结果、截图与 trace 都会出现在这里。"
                    : "没有用例明细（CLI 未匹配到 spec，或执行在收集阶段就失败了）"}
                </p>
              ) : (
                <>
                  {failed > 0 && (
                    <p className="mb-2 text-[11px] text-muted-foreground">
                      失败用例已自动展开；点用例行可收起/展开。
                    </p>
                  )}
                  <div className="rounded-md border">
                    {tests.map((test, index) => (
                      <TestRow key={test.id ?? `${test.fullTitle}-${index}`} run={run} test={test} />
                    ))}
                  </div>
                </>
              )
            )}

            {view === "artifacts" && (
              <ArtifactGallery run={run} artifacts={run.artifacts ?? []} />
            )}

            {view === "raw" && (
              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Terminal className="h-3.5 w-3.5" />
                  playwright CLI 的人读输出（含失败堆栈与 stderr）
                </div>
                <pre className="max-h-[60vh] overflow-y-auto whitespace-pre-wrap break-words rounded bg-muted p-3 text-[11px]">
                  {run.output || "（无输出）"}
                </pre>
              </div>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
