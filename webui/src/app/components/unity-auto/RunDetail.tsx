"use client";

/**
 * 一次 Unity 执行的详情：**步骤轨迹 + 产物存证 + 原始输出**。
 *
 * 为什么要有它：Unity 这边的存证原来是"截图落盘了就完事"——前端只能看见一串
 * 文件名，失败时更是连文件都没有（用例没走到自己那行 screenshot 就挂了）。
 * 现在执行侧统一产出四样东西：步骤轨迹（走进了哪一步、哪一步挂的）、截图、
 * 录像、失败现场文本；这里按"先给结论，再给证据"的次序把它们摊开。
 *
 * 与 Web-UI 的执行详情同构（那边是 Playwright 的用例明细 + trace + 失败截图），
 * 产物渲染直接复用同一套 ArtifactGallery，只是取文件的 URL 由这里注入。
 */

import React, { useMemo, useState } from "react";
import {
  AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, ListTree, Terminal,
} from "lucide-react";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { StatusBadge } from "@/app/components/ui-patterns";
import {
  unityArtifactUrl, useUnityRun, type UnityArtifact, type UnityStep,
} from "@/lib/api/useNewModules";
import {
  ArtifactGallery, ArtifactThumb, ArtifactsPrunedNotice, ImageViewer,
} from "@/app/components/web-ui-auto/ArtifactGallery";
import { cn } from "@/lib/utils";

function Stat({ label, value, tone }: { label: string; value: React.ReactNode; tone?: string }) {
  return (
    <div className="rounded-md border px-2.5 py-1.5">
      <div className="text-[10px] text-muted-foreground">{label}</div>
      <div className={cn("text-sm font-medium", tone)}>{value}</div>
    </div>
  );
}

function StepRow({ step }: { step: UnityStep }) {
  const [open, setOpen] = useState(!step.ok && Boolean(step.error));
  const label = step.target ? `${step.action} ${step.target}` : step.action;
  return (
    <div className={cn("border-b last:border-b-0", !step.ok && "bg-destructive/5")}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-muted/40"
      >
        <span className="w-8 shrink-0 text-right font-mono text-[10px] text-muted-foreground">
          #{step.i}
        </span>
        <span className="shrink-0">
          {step.ok
            ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
            : <AlertTriangle className="h-3.5 w-3.5 text-red-600" />}
        </span>
        <span className="min-w-0 flex-1 truncate font-mono text-[11px]">{label}</span>
        <span className="shrink-0 text-[10px] text-muted-foreground">
          {step.t}s · {step.ms}ms
        </span>
        {step.error && (open
          ? <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          : <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />)}
      </button>
      {open && step.error && (
        <pre className="mx-3 mb-2 max-h-40 overflow-y-auto whitespace-pre-wrap break-words rounded bg-destructive/10 p-2 text-[11px] text-destructive">
          {step.error}
        </pre>
      )}
    </div>
  );
}

export function UnityRunDetailDialog({
  runId, scriptName, onClose,
}: {
  runId: string;
  scriptName?: string;
  onClose: () => void;
}) {
  const { data: run } = useUnityRun(runId);
  const [view, setView] = useState<"steps" | "artifacts" | "raw">("steps");
  const [lightbox, setLightbox] = useState<number | null>(null);

  const artifacts: UnityArtifact[] = useMemo(() => run?.artifacts ?? [], [run?.artifacts]);
  const steps = run?.steps ?? [];
  const failedStep = useMemo(() => [...steps].reverse().find((s) => !s.ok), [steps]);
  const images = useMemo(() => artifacts.filter((a) => a.kind === "image"), [artifacts]);
  const video = useMemo(() => artifacts.find((a) => a.kind === "video"), [artifacts]);
  // 存证文件按名字对齐 URL（后端的产物清单里已经带了带签名的直链）。
  const urlFor = useMemo(() => {
    const map = new Map(artifacts.map((a) => [a.path, unityArtifactUrl(a)]));
    return (path: string) => map.get(path) ?? "";
  }, [artifacts]);
  const failureShot = images.find((a) => a.name.startsWith("failure."));

  if (!run) {
    return (
      <Dialog open onOpenChange={onClose}>
        <DialogContent className="sm:max-w-3xl">
          <p className="py-10 text-center text-sm text-muted-foreground">加载执行记录…</p>
        </DialogContent>
      </Dialog>
    );
  }

  const running = run.status === "running" && !run.stale_running;

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-5xl overflow-hidden p-0 sm:max-w-5xl">
        {/* min-w-0 是必须的：DialogContent 是 grid，grid item 默认 min-width:auto ——
            原始输出里那些超长的绝对路径会把整块卡片顶宽，文字直接画到卡片外面
            （实测截图：正文跑到屏幕右边、盖住页面背景）。 */}
        <div className="flex max-h-[88vh] w-full min-w-0 flex-col">
          {/* 头部：结论 */}
          <div className="flex flex-wrap items-center gap-2 border-b px-4 py-3">
            <StatusBadge status={run.status} fallbackLabel={run.status} />
            <span className="text-sm font-medium">{scriptName ?? "执行详情"}</span>
            <span className="text-xs text-muted-foreground">
              {run.created_at ? new Date(run.created_at).toLocaleString("zh-CN") : "-"}
            </span>
            {running && (
              <span className="text-xs text-muted-foreground">执行中…（轨迹实时刷新）</span>
            )}
          </div>

          {/* 统计条 */}
          <div className="flex flex-wrap gap-2 border-b px-4 py-3">
            <Stat label="步骤" value={steps.length} />
            <Stat label="失败步骤" value={steps.filter((s) => !s.ok).length}
                  tone={steps.some((s) => !s.ok) ? "text-red-600" : undefined} />
            <Stat label="截图" value={images.length} />
            <Stat label="录像" value={video ? "有" : "无"} />
            <Stat label={running ? "已进行" : "耗时"}
                  value={running
                    ? (run.elapsed_ms != null ? `${Math.round(run.elapsed_ms / 1000)}s` : "…")
                    : (run.duration_ms != null ? `${(run.duration_ms / 1000).toFixed(1)}s` : "-")} />
            <Stat label="退出码" value={run.exit_code ?? "-"} />
          </div>

          {/* 视图切换 */}
          <div className="flex gap-1 border-b px-4 py-2">
            {([
              ["steps", `步骤轨迹（${steps.length}）`],
              ["artifacts", `产物存证（${artifacts.length}）`],
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
            <ArtifactsPrunedNotice pruned={run.artifacts_pruned} />

            {view === "steps" && (
              steps.length === 0 ? (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  {running
                    ? "还没有动作被执行（脚本可能正在等第一个对象出现）。"
                    : "没有步骤轨迹：脚本在连上 Unity 之前就退出了，或这次执行是环境问题（不是用例失败）。"}
                </p>
              ) : (
                <div className="flex flex-col gap-3">
                  {/* 失败结论 + 失败现场：一眼看完"挂在哪、现场长什么样" */}
                  {failedStep && (
                    <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3">
                      <div className="flex items-start gap-2">
                        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" />
                        <div className="min-w-0 flex-1">
                          <div className="text-xs font-medium text-red-600">
                            第 {failedStep.i} 步失败：{failedStep.action}
                            {failedStep.target ? ` ${failedStep.target}` : ""}
                          </div>
                          <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap text-[11px] text-destructive">
                            {failedStep.error ?? "（无错误信息）"}
                          </pre>
                        </div>
                        {failureShot && (
                          <ArtifactThumb
                            run={run} path={failureShot.path} urlFor={urlFor}
                            onOpen={() => setLightbox(images.indexOf(failureShot))}
                          />
                        )}
                      </div>
                    </div>
                  )}
                  <div className="rounded-md border">
                    {steps.map((step) => <StepRow key={step.i} step={step} />)}
                  </div>
                </div>
              )
            )}

            {view === "artifacts" && (
              <ArtifactGallery
                run={run}
                artifacts={artifacts}
                urlFor={urlFor}
                videoHint="没有录像：录制被关掉了（UNITY_RECORD=0），或这次执行在开录之前就退出了。"
              />
            )}

            {view === "raw" && (
              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Terminal className="h-3.5 w-3.5" />
                  脚本的人读输出（prelude 的存证摘要 + 用例自己的 print + 异常堆栈）
                </div>
                <pre className="max-h-[60vh] overflow-y-auto whitespace-pre-wrap break-words rounded bg-muted p-3 text-[11px]">
                  {run.output || "（无输出）"}
                </pre>
              </div>
            )}
          </div>
        </div>
      </DialogContent>

      <ImageViewer
        run={run}
        paths={images.map((a) => a.path)}
        index={lightbox}
        onIndex={setLightbox}
        onClose={() => setLightbox(null)}
        urlFor={urlFor}
      />
    </Dialog>
  );
}

/** 列表里用的一行小提示：这次执行留下了哪些证据（不打开详情也能扫一眼）。 */
export function EvidenceHint({ run }: {
  run: { artifacts?: UnityArtifact[] | null; steps?: UnityStep[] | null };
}) {
  const artifacts = run.artifacts ?? [];
  const counts = {
    image: artifacts.filter((a) => a.kind === "image").length,
    video: artifacts.filter((a) => a.kind === "video").length,
    text: artifacts.filter((a) => a.kind === "text").length,
  };
  const parts: string[] = [];
  if ((run.steps ?? []).length) parts.push(`${run.steps!.length} 步`);
  if (counts.image) parts.push(`${counts.image} 图`);
  if (counts.video) parts.push("录像");
  if (counts.text) parts.push(`${counts.text} 文本`);
  return (
    <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
      <ListTree className="h-3 w-3" />
      {parts.length ? parts.join(" · ") : "无存证"}
    </span>
  );
}
