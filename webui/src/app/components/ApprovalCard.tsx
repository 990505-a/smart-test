"use client";

import React from "react";
import { ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { PendingApproval } from "@/app/hooks/useChat";

/**
 * 越权操作的人工审批卡片（dsh 式：等待决策时接管输入区）。
 *
 * 从 ChatInterface 里抽出来的：原先对话页与「代码图谱 → AI 分析」面板共用（后者
 * 2026-09 删除）。它只依赖 interrupt / resumeInterrupt，与具体页面无关。
 */
interface ApprovalCardProps {
  interrupt: PendingApproval;
  onDecide: (decision: "approve" | "reject" | "always") => void;
  className?: string;
}

export function ApprovalCard({ interrupt, onDecide, className }: ApprovalCardProps) {
  const multiple = interrupt.actions.length > 1;
  return (
    <div
      className={cn(
        "rounded-lg border border-amber-500/40 bg-amber-500/5 px-4 py-3",
        className,
      )}
    >
      <div className="flex items-center gap-2 text-sm font-medium text-amber-600">
        <ShieldAlert className="h-4 w-4 shrink-0" />
        <span>
          {multiple
            ? `有 ${interrupt.actions.length} 项操作需要审批`
            : interrupt.toolName === "execute"
              ? "命令执行需要审批"
              : interrupt.description || "操作需要审批"}
        </span>
        {!multiple && (
          <span className="text-xs font-normal text-muted-foreground">
            （{interrupt.toolName}）
          </span>
        )}
      </div>
      {multiple ? (
        // 并行多个受控调用：逐个列出。用户点「全部允许一次」时这几项都会放行，
        // 所以要让他看见自己批准了什么，而不是只显示第一条。
        <div className="mt-2 max-h-40 space-y-1.5 overflow-auto">
          {interrupt.actions.map((action, index) => (
            <div key={index} className="rounded bg-muted px-3 py-2 text-xs">
              <div className="mb-1 font-medium text-muted-foreground">
                {action.name}
              </div>
              <pre className="whitespace-pre-wrap break-all">
                {action.command ||
                  String(action.args?.file_path ?? action.args?.path ?? "") ||
                  JSON.stringify(action.args, null, 2)}
              </pre>
            </div>
          ))}
        </div>
      ) : (
        <pre className="mt-2 max-h-32 overflow-auto rounded bg-muted px-3 py-2 text-xs whitespace-pre-wrap break-all">
          {interrupt.command ||
            String(interrupt.args?.file_path ?? interrupt.args?.path ?? "") ||
            JSON.stringify(interrupt.args, null, 2)}
        </pre>
      )}
      <div className="mt-3 flex items-center justify-between gap-2">
        <span className="text-[11px] leading-4 text-muted-foreground">
          始终允许 = 本会话内同类操作自动放行
          （命令按程序名 / 写入按目录）
        </span>
        <div className="flex shrink-0 justify-end gap-2">
          <Button type="button" size="sm" variant="outline" onClick={() => onDecide("reject")}>
            拒绝
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => onDecide("always")}
            title="本会话内不再为同类操作弹窗：命令按程序名放行，文件写入按所在目录放行"
          >
            {multiple ? "全部始终允许" : "始终允许"}
          </Button>
          <Button type="button" size="sm" onClick={() => onDecide("approve")}>
            {multiple ? "全部允许一次" : "允许一次"}
          </Button>
        </div>
      </div>
    </div>
  );
}
