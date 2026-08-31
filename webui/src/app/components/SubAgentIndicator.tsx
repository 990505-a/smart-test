"use client";

import React, { useCallback } from "react";
import { PanelRightOpen } from "lucide-react";
import { cn } from "@/lib/utils";
import type { SubAgent } from "@/app/types/types";

interface SubAgentIndicatorProps {
  subAgent: SubAgent;
  /** 打开右侧实时操作面板（ZCode 风格抽屉） */
  onOpenActivity?: (subAgent: SubAgent) => void;
}

/**
 * 消息流内的子智能体状态条：只展示状态与入口，正文（实时操作/输入/输出）
 * 一律在右侧面板查看——内联展开与面板内容重复，已移除。
 */
export const SubAgentIndicator = React.memo<SubAgentIndicatorProps>(
  ({ subAgent, onOpenActivity }) => {
    const openActivity = useCallback(() => {
      onOpenActivity?.(subAgent);
    }, [onOpenActivity, subAgent]);

    const isActive = subAgent.status === "active";

    const content = (
      <>
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <span
            className={cn(
              "h-2 w-2 shrink-0 rounded-full",
              isActive && "animate-pulse bg-brand",
              subAgent.status === "completed" && "bg-success",
              subAgent.status === "error" && "bg-destructive",
              subAgent.status === "pending" && "bg-muted-foreground/50",
            )}
          />
          <span className="truncate text-[13px] font-medium leading-[140%] text-foreground">
            子智能体 · {subAgent.subAgentName}
          </span>
          {isActive && (
            <span className="shrink-0 text-xs text-shimmer">执行中</span>
          )}
        </div>
        {onOpenActivity && (
          <span
            className="flex h-6 shrink-0 items-center gap-1 rounded-md px-1.5 text-muted-foreground"
            aria-hidden
          >
            <PanelRightOpen className="h-3.5 w-3.5" />
          </span>
        )}
      </>
    );

    if (!onOpenActivity) {
      return (
        <div
          className={cn(
            "flex w-full items-center gap-2 rounded-lg bg-card px-3 py-2",
            isActive && "sweep-running",
          )}
        >
          {content}
        </div>
      );
    }

    return (
      <button
        type="button"
        onClick={openActivity}
        title="查看实时操作与输出"
        className={cn(
          "flex w-full cursor-pointer items-center gap-2 rounded-lg bg-card px-3 py-2 text-left",
          "transition-colors duration-150 hover:bg-accent",
          isActive && "sweep-running",
        )}
      >
        {content}
      </button>
    );
  },
);

SubAgentIndicator.displayName = "SubAgentIndicator";
