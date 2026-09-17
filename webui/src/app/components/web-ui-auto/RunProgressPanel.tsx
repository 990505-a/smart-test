"use client";

/**
 * 执行中的实时进度面板。
 *
 * 为什么需要它：一次执行要几十秒（移动站首屏就 6–10s，失败还可能触发自修复重跑），
 * 而结果只在整轮跑完才落库——此前用户点完「执行」在页面上什么都看不到，只能干等。
 *
 * 数据链路：sidecar 里的自定义 reporter 逐条用例把事件追加到 `progress.ndjson`，
 * CLI 的原样输出追加到 `stdout.log`；后端容器挂着同一个 runs 目录，直接读磁盘。
 * 前端轮询这个接口（2s），所以进度是"真的在跑"的进度，不是猜的。
 */

import React, { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2, MinusCircle, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { useWebUiRunProgress, type WebUiScriptRun } from "@/lib/api/useNewModules";
import { cn } from "@/lib/utils";

function formatElapsed(ms: number): string {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

const EVENT_ICON: Record<string, React.ReactNode> = {
  passed: <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />,
  failed: <XCircle className="h-3.5 w-3.5 text-red-600" />,
  timedOut: <AlertTriangle className="h-3.5 w-3.5 text-red-600" />,
  interrupted: <AlertTriangle className="h-3.5 w-3.5 text-amber-600" />,
  skipped: <MinusCircle className="h-3.5 w-3.5 text-muted-foreground" />,
};

export function RunProgressPanel({
  run, onFinished,
}: {
  run: WebUiScriptRun;
  /** 跑完那一刻回调一次，让外层刷新列表与统计 */
  onFinished?: () => void;
}) {
  const progress = useWebUiRunProgress(run.id, true, 2000);
  const data = progress.data;
  const [tick, setTick] = useState(0);
  const logRef = useRef<HTMLPreElement>(null);
  const finishedRef = useRef(false);

  // 秒表：接口每 2 秒才回一次，没有本地 tick 的话耗时显示会一跳一跳
  useEffect(() => {
    const timer = setInterval(() => setTick((value) => value + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  // 日志尾自动滚到底部（用户往上翻时不打扰——只在接近底部时才跟随）
  useEffect(() => {
    const node = logRef.current;
    if (!node) return;
    const nearBottom = node.scrollHeight - node.scrollTop - node.clientHeight < 60;
    if (nearBottom) node.scrollTop = node.scrollHeight;
  }, [data?.log_tail, tick]);

  const running = data?.running ?? run.status === "running";
  const stale = data?.stale ?? run.stale_running ?? false;

  useEffect(() => {
    if (data && !data.running && !finishedRef.current) {
      finishedRef.current = true;
      onFinished?.();
      progress.mutate();
    }
  }, [data, onFinished, progress]);

  const elapsed = (data?.elapsed_ms ?? 0) + tick * 0;
  const done = data?.done ?? 0;
  const total = data?.total ?? null;
  const percent = total && total > 0 ? Math.min(100, Math.round((done / total) * 100)) : null;
  const events = useMemo(() => [...(data?.events ?? [])].reverse(), [data?.events]);

  return (
    <div className="flex flex-col gap-3 rounded-md border p-3">
      <div className="flex flex-wrap items-center gap-2">
        {running && !stale && <Loader2 className="h-4 w-4 animate-spin text-primary" />}
        <Badge variant={running && !stale ? "secondary" : "destructive"} className="font-normal">
          {stale ? "疑似中断" : running ? "正在执行" : "已结束"}
        </Badge>
        <span className="text-xs text-muted-foreground">
          已跑 {formatElapsed(elapsed)}
          {total ? ` · 用例 ${done}/${total}` : data?.started ? ` · 已完成 ${done} 条` : " · 正在启动浏览器"}
        </span>
        {data && (data.passed > 0 || data.failed > 0 || data.skipped > 0) && (
          <span className="flex items-center gap-2 text-xs">
            <span className="text-emerald-600">通过 {data.passed}</span>
            {data.failed > 0 && <span className="text-red-600">失败 {data.failed}</span>}
            {data.skipped > 0 && <span className="text-muted-foreground">跳过 {data.skipped}</span>}
          </span>
        )}
      </div>

      {/* 进度条：总数还没拿到时用条纹表示"不确定" */}
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={cn(
            "h-full rounded-full bg-primary transition-all",
            percent === null && "animate-pulse bg-primary/50",
          )}
          style={{ width: percent === null ? "100%" : `${Math.max(3, percent)}%` }}
        />
      </div>

      {stale && (
        <p className="rounded bg-destructive/10 px-2 py-1 text-[11px] text-destructive">
          这条执行已经超过预期时长仍未结束（进程可能被杀或容器重启），记录不会自动收敛——
          重新执行即可。
        </p>
      )}

      <div className="grid gap-3 lg:grid-cols-2">
        <div>
          <div className="mb-1 text-[11px] font-medium text-muted-foreground">
            用例进度（实时）
          </div>
          {events.length === 0 ? (
            <p className="py-3 text-[11px] text-muted-foreground">
              还没有用例跑完。移动站首屏较慢，通常 5–10 秒后才会出现第一条。
            </p>
          ) : (
            <ol className="flex max-h-56 flex-col gap-1 overflow-y-auto">
              {events.map((event, index) => (
                <li key={`${event.fullTitle}-${index}`} className="flex items-center gap-1.5 text-[11px]">
                  {EVENT_ICON[event.status ?? ""] ?? <Loader2 className="h-3.5 w-3.5" />}
                  <span className="min-w-0 flex-1 truncate" title={event.fullTitle}>
                    {event.title ?? event.fullTitle}
                  </span>
                  <span className="shrink-0 text-muted-foreground">
                    {event.status} · {event.duration}ms
                  </span>
                </li>
              ))}
            </ol>
          )}
        </div>

        <div>
          <div className="mb-1 text-[11px] font-medium text-muted-foreground">
            CLI 输出（实时尾部）
          </div>
          <pre
            ref={logRef}
            className="max-h-56 overflow-auto rounded bg-muted p-2 text-[10px] leading-4"
          >
            {data?.log_tail?.trim() || "（等待 CLI 输出…）"}
          </pre>
        </div>
      </div>
    </div>
  );
}
