"use client";

/**
 * 测评批次执行中的实时面板。
 *
 * 为什么需要它：一条用例要跑完整个 agent run（含多次浏览器工具调用），几十秒
 * 到几分钟；一个 6 条的批次串行就是好几分钟。此前结果**整轮跑完才入库**，页面
 * 上只有"用例 0/6"和一个转圈图标——分不清在跑、卡住了、还是执行进程跟着容器
 * 重启一起没了。
 *
 * 数据链路：执行侧边跑边写 `eval-runs/<batchId>/live.ndjson`（结构化事件）与
 * `live.log`（人读日志），后端直接读磁盘，前端每 2 秒轮询。心跳决定 `stale`：
 * 心跳停了就说明执行进程不在了，界面必须说出来而不是永远转圈。
 */

import React, { useEffect, useMemo, useRef } from "react";
import { AlertTriangle, CheckCircle2, Loader2, PlayCircle, Wrench, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { useEvalBatchProgress, type EvalBatch } from "@/lib/api/useNewModules";
import { cn } from "@/lib/utils";

function formatElapsed(ms: number): string {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

function scoreChips(scores: Array<{ name: string; value: unknown }>): string {
  return scores
    .map((s) => {
      if (typeof s.value === "boolean") return `${s.name}=${s.value ? "✓" : "✗"}`;
      if (typeof s.value === "number") return `${s.name}=${s.value.toFixed(2)}`;
      return `${s.name}=${String(s.value)}`;
    })
    .join("  ");
}

export function BatchLivePanel({ batch, onFinished }: {
  batch: EvalBatch;
  /** 跑完那一刻回调一次，让外层刷新批次列表 */
  onFinished?: () => void;
}) {
  const progress = useEvalBatchProgress(batch.id, true, 2000);
  const data = progress.data;
  const logRef = useRef<HTMLPreElement>(null);
  const finishedRef = useRef(false);

  // 日志尾自动跟随（用户往上翻时不打扰——只在接近底部时才跟）
  useEffect(() => {
    const node = logRef.current;
    if (!node) return;
    const nearBottom = node.scrollHeight - node.scrollTop - node.clientHeight < 60;
    if (nearBottom) node.scrollTop = node.scrollHeight;
  }, [data?.log_tail]);

  const running = data?.running ?? batch.status === "running";
  const stale = data?.stale ?? batch.stale;

  useEffect(() => {
    if (data && !data.running && !finishedRef.current) {
      finishedRef.current = true;
      onFinished?.();
    }
  }, [data, onFinished]);

  const total = data?.total ?? batch.total_cases;
  const done = data?.done ?? batch.done_cases;
  const percent = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : null;
  // 活动流倒序：最新的一步在最上面，不用滚到底
  const activity = useMemo(() => [...(data?.activity ?? [])].reverse(), [data?.activity]);
  const active = data?.active ?? [];

  return (
    <div className="flex flex-col gap-3 rounded-md border p-3">
      <div className="flex flex-wrap items-center gap-2">
        {running && !stale && <Loader2 className="h-4 w-4 animate-spin text-primary" />}
        <Badge variant={running && !stale ? "secondary" : stale ? "destructive" : "outline"}
               className="font-normal">
          {stale ? "疑似中断" : running ? "正在执行" : "已结束"}
        </Badge>
        <span className="text-xs text-muted-foreground">
          已跑 {formatElapsed(data?.elapsed_ms ?? 0)} · 完成 {done}
          {total ? `/${total}` : ""}
        </span>
        {data && (data.passed > 0 || data.failed > 0) && (
          <span className="flex items-center gap-2 text-xs">
            <span className="text-emerald-600">正常 {data.passed}</span>
            {data.failed > 0 && <span className="text-red-600">异常 {data.failed}</span>}
          </span>
        )}
        {!data?.started && running && !stale && (
          <span className="text-xs text-muted-foreground">
            执行进程尚未写下第一行（正在准备评测集与打分器…）
          </span>
        )}
        {data?.heartbeat_age_s != null && running && !stale && (
          <span className="text-[11px] text-muted-foreground">
            心跳 {Math.round(data.heartbeat_age_s)}s 前
          </span>
        )}
      </div>

      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={cn("h-full rounded-full bg-primary transition-all",
                        percent === null && "animate-pulse bg-primary/50")}
          style={{ width: percent === null ? "100%" : `${Math.max(2, percent)}%` }}
        />
      </div>

      {stale && (
        <p className="rounded bg-destructive/10 px-2 py-1 text-[11px] text-destructive">
          记录仍是「运行中」，但执行进程已经停止心跳（服务重启或被 kill？）。
          已经跑完的用例结果保留在下面，未跑的不再继续——需要重新启动一次批次。
        </p>
      )}

      {active.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]">
          <span className="text-muted-foreground">正在跑：</span>
          {active.map((item) => (
            <span key={item.item_id} className="font-mono">
              {item.item_id}
              <span className="ml-1 text-muted-foreground">{formatElapsed(item.elapsed_ms)}</span>
            </span>
          ))}
        </div>
      )}

      <div className="grid gap-3 lg:grid-cols-2">
        <div>
          <div className="mb-1 text-[11px] font-medium text-muted-foreground">
            agent 在做什么（实时）
          </div>
          {activity.length === 0 ? (
            <p className="py-3 text-[11px] text-muted-foreground">
              还没有事件。首条用例要先起 agent、再调工具，通常十几秒后才有动静。
            </p>
          ) : (
            <ol className="flex max-h-56 flex-col gap-1 overflow-y-auto">
              {activity.map((event, index) => (
                <li key={`${event.ts}-${index}`}
                    className="flex items-start gap-1.5 text-[11px] leading-4">
                  {event.event === "item_start" && (
                    <PlayCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
                  )}
                  {event.event === "note" && (
                    <Wrench className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  )}
                  {event.event === "item" && (event.status === "ok"
                    ? <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-600" />
                    : <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-red-600" />)}
                  <span className="shrink-0 font-mono text-muted-foreground">
                    {new Date(event.ts * 1000).toLocaleTimeString("zh-CN", { hour12: false })}
                  </span>
                  <span className="min-w-0 flex-1 break-words">
                    {event.event === "note"
                      ? event.text
                      : event.event === "item_start"
                        ? `${event.item_id} 开始`
                        : `${event.item_id} ${event.status === "ok" ? "完成" : "失败"}`
                          + (event.duration_ms != null
                            ? ` · ${(event.duration_ms / 1000).toFixed(1)}s` : "")
                          + (event.scores?.length ? ` · ${scoreChips(event.scores)}` : "")
                          + (event.error ? ` · ${event.error.slice(0, 120)}` : "")}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </div>

        <div>
          <div className="mb-1 text-[11px] font-medium text-muted-foreground">
            执行日志（实时尾部）
          </div>
          <pre ref={logRef}
               className="max-h-56 overflow-auto rounded bg-muted p-2 text-[10px] leading-4">
            {data?.log_tail?.trim() || "（等待执行进程输出…）"}
          </pre>
        </div>
      </div>

      {stale && (
        <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <AlertTriangle className="h-3.5 w-3.5" />
          这条记录不会自动收敛，也不会自动重跑。
        </p>
      )}
    </div>
  );
}
