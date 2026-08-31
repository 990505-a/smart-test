"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  X,
  Wrench,
  Bot,
  Loader2,
  CircleCheckBig,
  AlertCircle,
  MessageSquare,
  ChevronRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { MarkdownContent } from "@/app/components/MarkdownContent";
import { extractSubAgentContent } from "@/app/types/types";
import type { SubAgent } from "@/app/types/types";
import type { SubAgentEvent } from "@/app/hooks/subagentActivity";

interface SubAgentPanelProps {
  subAgent: SubAgent | null;
  feed: SubAgentEvent[];
  onClose: () => void;
}

const STATUS_TEXT: Record<SubAgent["status"], string> = {
  pending: "等待中",
  active: "运行中",
  completed: "已完成",
  error: "出错",
};

const STATUS_PILL: Record<SubAgent["status"], string> = {
  pending: "bg-muted text-muted-foreground",
  active: "bg-brand/12 text-brand",
  completed: "bg-success/12 text-success",
  error: "bg-destructive/12 text-destructive",
};

function formatElapsed(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m${String(s % 60).padStart(2, "0")}s`;
}

function FeedRow({ event, isLast }: { event: SubAgentEvent; isLast: boolean }) {
  const isTool = event.kind === "tool";
  const isRunning = isTool && event.status === "running";
  const isError = event.status === "error";
  return (
    <div className="relative flex gap-3 pb-3 pl-0.5 last:pb-0">
      {/* 左侧时间线轨道 */}
      <div className="flex w-4 shrink-0 flex-col items-center">
        {isTool ? (
          isRunning ? (
            <Loader2 size={14} className="mt-0.5 shrink-0 animate-spin text-brand" />
          ) : isError ? (
            <AlertCircle size={14} className="mt-0.5 shrink-0 text-destructive" />
          ) : (
            <CircleCheckBig size={14} className="mt-0.5 shrink-0 text-success" />
          )
        ) : (
          <MessageSquare size={13} className="mt-0.5 shrink-0 text-muted-foreground/70" />
        )}
        {/* 连接线（最后一行不画） */}
        {!isLast && <span className="mt-1 w-px flex-1 bg-border/60" />}
      </div>

      <div className="min-w-0 flex-1 space-y-0.5">
        {isTool && event.name && (
          <div className="flex items-baseline gap-2">
            <span className="rounded bg-muted px-1.5 py-px font-mono text-[11px] font-medium text-foreground/90">
              {event.name}
            </span>
          </div>
        )}
        {event.preview && (
          <p
            className={cn(
              "break-all font-mono text-[11px] leading-[18px] text-muted-foreground",
              isError && "text-destructive/90",
              isRunning && "text-foreground/75",
            )}
          >
            {event.preview}
          </p>
        )}
      </div>

      <span className="shrink-0 pt-px text-[10px] tabular-nums text-muted-foreground/50">
        {new Date(event.ts).toLocaleTimeString("zh-CN", {
          hour12: false,
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        })}
      </span>
    </div>
  );
}

/**
 * 右侧抽屉：子智能体实时操作面板。
 * feed 是会话内存数据（刷新后仅保留最终输出），父会话流不受影响。
 */
export const SubAgentPanel = React.memo<SubAgentPanelProps>(
  ({ subAgent, feed, onClose }) => {
    const scrollRef = useRef<HTMLDivElement | null>(null);
    const nearBottomRef = useRef(true);
    const [now, setNow] = useState(Date.now());
    const [outputExpanded, setOutputExpanded] = useState(true);
    const [taskOpen, setTaskOpen] = useState(false);

    const isActive = subAgent?.status === "active";
    useEffect(() => {
      if (!isActive) return;
      const timer = window.setInterval(() => setNow(Date.now()), 1000);
      return () => window.clearInterval(timer);
    }, [isActive]);

    // 自动跟随：仅当用户本来就在底部附近时
    useEffect(() => {
      const el = scrollRef.current;
      if (!el || !nearBottomRef.current) return;
      el.scrollTop = el.scrollHeight;
    }, [feed]);

    // 直接计算，不走 useMemo：feed 是 store 里原地变更的稳定引用，
    // useMemo([feed]) 永远命中缓存，统计会冻结在首帧的 0
    // 时间线只展示工具调用；文本输出由输出区渲染，不再在时间线里重复一遍
    const toolEvents = feed.filter((e) => e.kind === "tool");
    const stats = {
      tools: toolEvents.length,
      errors: feed.filter((e) => e.status === "error").length,
    };
    // 最近一个工具调用名（只取工具事件，不把 markdown 文本平铺进摘要）
    const lastToolName = [...toolEvents].reverse().find((e) => e.kind === "tool")?.name;

    if (!subAgent) return null;

    const startTs = feed.length > 0 ? feed[0].ts : null;
    const elapsed = isActive && startTs ? formatElapsed(now - startTs) : null;
    const finalText = subAgent.output
      ? extractSubAgentContent(subAgent.output)
      : "";
    // 流式期间实时渲染的完整输出（与主对话一致的 markdown 渲染）
    const liveText = [...feed].reverse().find((e) => e.kind === "text")?.fullText ?? "";
    const outputText = isActive ? liveText : finalText || liveText;
    // 任务描述（原内联卡片的「输入」）：deepagents task args 的 description
    const taskDesc = extractSubAgentContent(subAgent.input);

    return (
      <div
        className={cn(
          // 小屏：覆盖在聊天区右侧；大屏(lg+)：static 并排成一列，
          // 压缩主列宽度而不是遮挡输入框
          "absolute inset-y-0 right-0 z-50 flex w-[min(480px,92vw)] flex-col",
          "border-l border-border bg-background shadow-2xl",
          "lg:static lg:z-auto lg:w-[min(440px,36vw)] lg:shrink-0 lg:shadow-none",
          "animate-in slide-in-from-right duration-200 ease-out",
        )}
        role="dialog"
        aria-label={`子智能体 ${subAgent.subAgentName} 实时操作`}
      >
        {/* Header */}
        <div className="flex h-14 shrink-0 items-start justify-between gap-3 border-b px-4 pt-3">
          <div className="flex min-w-0 flex-col gap-1">
            <div className="flex min-w-0 items-center gap-2">
              <span
                className={cn(
                  "flex h-6 w-6 shrink-0 items-center justify-center rounded-md",
                  isActive ? "bg-brand/12 text-brand" : "bg-muted text-muted-foreground",
                )}
              >
                <Bot size={14} className={isActive ? "animate-pulse" : ""} />
              </span>
              <span className="truncate text-[13px] font-semibold text-foreground">
                {subAgent.subAgentName}
              </span>
              <span
                className={cn(
                  "shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium",
                  STATUS_PILL[subAgent.status],
                )}
              >
                {STATUS_TEXT[subAgent.status]}
                {elapsed ? ` · ${elapsed}` : ""}
              </span>
            </div>
            {/* 摘要行：只在有工具活动时有意义；纯文本任务不显示「0 次工具调用」噪音 */}
            <p className="truncate text-[11px] leading-4 text-muted-foreground/80">
              {toolEvents.length === 0
                ? isActive
                  ? "正在启动…"
                  : outputText
                    ? "直接输出，未调用工具"
                    : "暂无活动记录"
                : [
                    `${stats.tools} 次工具调用`,
                    stats.errors > 0 ? `${stats.errors} 个错误` : null,
                    lastToolName ? `最近: ${lastToolName}` : null,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
            </p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            className="h-7 w-7 shrink-0"
            aria-label="关闭子智能体面板"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* 任务描述：智能体派发给子智能体的指令。长文本默认 2 行截断，
            点击展开全文（不塞进固定高度的头部——那会溢出错位且没法读） */}
        {taskDesc && (
          <div className="shrink-0 border-b border-border/60 bg-muted/10">
            <button
              type="button"
              onClick={() => setTaskOpen((v) => !v)}
              className="flex w-full items-start gap-1.5 px-4 py-2 text-left"
              aria-expanded={taskOpen}
            >
              <ChevronRight
                size={13}
                className={cn(
                  "mt-0.5 shrink-0 text-muted-foreground transition-transform",
                  taskOpen && "rotate-90",
                )}
              />
              <div className="min-w-0 flex-1">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  任务
                </span>
                {!taskOpen && (
                  <p className="line-clamp-2 whitespace-pre-wrap break-words text-xs leading-5 text-muted-foreground">
                    {taskDesc}
                  </p>
                )}
              </div>
            </button>
            {taskOpen && (
              <div className="max-h-40 overflow-y-auto px-4 pb-3 pl-[30px]">
                <p className="whitespace-pre-wrap break-words text-xs leading-5 text-foreground/80">
                  {taskDesc}
                </p>
              </div>
            )}
          </div>
        )}

        {/* 工具调用时间线：只放工具事件（文本输出在输出区渲染，避免同内容
            一遍纯文本 preview、一遍富文本的重复展示） */}
        {toolEvents.length > 0 && (
          <div
            ref={scrollRef}
            onScroll={(e) => {
              const el = e.currentTarget;
              nearBottomRef.current =
                el.scrollHeight - el.scrollTop - el.clientHeight < 80;
            }}
            className="min-h-0 flex-1 overflow-y-auto px-4 py-3"
          >
            {toolEvents.map((event, i) => (
              <FeedRow
                key={`${event.id}-${event.ts}`}
                event={event}
                isLast={i === toolEvents.length - 1}
              />
            ))}
          </div>
        )}

        {/* 两者皆空（刚派发/刷新后无记录也无输出）的兜底空态 */}
        {toolEvents.length === 0 && !outputText && (
          <div className="flex min-h-0 flex-1 flex-col items-center justify-center px-4 text-center">
            <Wrench className="mb-2 h-7 w-7 text-muted-foreground/40" />
            <p className="text-[13px] text-muted-foreground">
              {isActive ? "正在启动…" : "暂无活动记录"}
            </p>
          </div>
        )}

        {/* 输出区：有工具记录时是下半区（带折叠头，压缩至 45%）；
            无工具记录时占满整个面板，直接像主对话一样渲染，不再套
            「最终输出」小框 */}
        {outputText && (
          toolEvents.length > 0 ? (
            <div className="flex max-h-[45%] shrink-0 flex-col overflow-hidden border-t bg-muted/20">
              <button
                type="button"
                onClick={() => setOutputExpanded((v) => !v)}
                className="flex w-full shrink-0 items-center gap-1.5 px-4 py-2 text-left"
                aria-expanded={outputExpanded}
              >
                <ChevronRight
                  size={13}
                  className={cn(
                    "shrink-0 text-muted-foreground transition-transform",
                    outputExpanded && "rotate-90",
                  )}
                />
                <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  {isActive ? "正在输出…" : "最终输出"}
                </span>
              </button>
              {outputExpanded && (
                <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-3">
                  <div className="text-sm leading-relaxed">
                    <MarkdownContent
                      content={outputText}
                      streaming={isActive}
                      className="[&_p:last-child]:inline [&_p:not(:last-child)]:inline-block"
                    />
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
              <div className="text-sm leading-relaxed">
                <MarkdownContent
                  content={outputText}
                  streaming={isActive}
                  className="[&_p:last-child]:inline [&_p:not(:last-child)]:inline-block"
                />
              </div>
            </div>
          )
        )}
      </div>
    );
  },
);

SubAgentPanel.displayName = "SubAgentPanel";
