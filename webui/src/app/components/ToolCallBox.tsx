"use client";

import React, { useState, useMemo, useCallback, lazy, Suspense } from "react";
import {
  ChevronDown,
  ChevronUp,
  Terminal,
  AlertCircle,
  Loader2,
  CircleCheckBig,
  StopCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import type { ToolCall } from "@/app/types/types";
import { cn } from "@/lib/utils";

const LoadExternalComponent = lazy(() =>
  import("@langchain/langgraph-sdk/react-ui").then((m) => ({
    default: m.LoadExternalComponent,
  })),
);
type ExternalComponentProps = React.ComponentProps<typeof LoadExternalComponent>;

const TOOL_DISPLAY: Record<string, string> = {
  ls: "列出目录",
  read_file: "读取文件",
  write_file: "写入文件",
  edit_file: "编辑文件",
  glob: "搜索文件",
  grep: "搜索内容",
  execute: "执行命令",
  write_todos: "更新任务",
  task: "调用子代理",
  export_test_cases: "导出用例",
  save_test_cases_batch: "批量保存用例",
  save_test_case_to_db: "保存用例",
  list_project_test_cases: "查询用例列表",
  ensure_project: "创建项目",
  lint_case_document: "检查用例质量",
  review_case_document: "二次复核用例",
  save_requirement_package: "保存需求包",
  get_case_workflow_status: "查看用例状态",
};

interface ToolCallBoxProps {
  toolCall: ToolCall;
  uiComponent?: unknown;
  stream?: unknown;
  graphId?: string;
}

/**
 * 用户手动展开/收起的记忆（tool call id -> 展开态）。
 * 消息列表是虚拟化的：滚出视口的条目会卸载、滚回来重新挂载，组件内部
 * state 随之丢失，展开状态会被重置成看起来"随机变化"。把选择记在组件外，
 * 重挂载后恢复用户上一次的选择；未操作过的卡片默认收起。
 */
const expandedStateById = new Map<string, boolean>();

function rememberExpanded(id: string, expanded: boolean) {
  expandedStateById.set(id, expanded);
  if (expandedStateById.size > 1000) {
    // 超长会话兜底：全清（最坏情况是展开态回到默认收起）
    expandedStateById.clear();
  }
}

export const ToolCallBox = React.memo<ToolCallBoxProps>(
  ({ toolCall, uiComponent, stream, graphId }) => {
    const [isExpanded, setIsExpanded] = useState(
      () => expandedStateById.get(toolCall.id) ?? false,
    );
    const [expandedArgs, setExpandedArgs] = useState<Record<string, boolean>>({});

    const { name, args, result, status } = useMemo(() => {
      return {
        name: toolCall.name || "unknown",
        args: toolCall.args || {},
        result: toolCall.result,
        status: toolCall.status || "completed",
      };
    }, [toolCall]);

    const label = TOOL_DISPLAY[name] ?? name;

    const statusIcon = useMemo(() => {
      switch (status) {
        case "completed":
          return <CircleCheckBig size={14} className="text-success" />;
        case "error":
          return <AlertCircle size={14} className="text-destructive" />;
        case "pending":
          // calm running dot (no spinner): the row itself carries the sweep
          return (
            <span className="relative flex h-2 w-2 items-center justify-center">
              <span className="absolute h-2 w-2 rounded-full bg-brand/20" />
              <span className="h-1 w-1 rounded-full bg-brand" />
            </span>
          );
        case "interrupted":
          return <StopCircle size={14} className="text-warning" />;
        default:
          return <Terminal size={14} className="text-muted-foreground" />;
      }
    }, [status]);

    const toggleExpanded = useCallback(() => {
      setIsExpanded((prev) => {
        const next = !prev;
        rememberExpanded(toolCall.id, next);
        return next;
      });
    }, [toolCall.id]);

    const toggleArgExpanded = useCallback((argKey: string) => {
      setExpandedArgs((prev) => ({ ...prev, [argKey]: !prev[argKey] }));
    }, []);

    const hasContent = result || Object.keys(args).length > 0;
    const hasGenUI = !!uiComponent && !!stream && !!graphId;

    return (
      <div
        className={cn(
          "w-full overflow-hidden rounded-lg border-none shadow-none outline-none transition-colors duration-200 hover:bg-accent",
          isExpanded && hasContent && "bg-accent",
          status === "pending" && "sweep-running",
        )}
      >
        <Button
          variant="ghost"
          size="sm"
          onClick={toggleExpanded}
          className={cn(
            "flex w-full items-center justify-between gap-2 border-none px-2 py-2 text-left shadow-none outline-none",
            "focus-visible:ring-0 focus-visible:ring-offset-0",
            !hasContent ? "cursor-default" : "disabled:cursor-default",
          )}
          disabled={!hasContent}
        >
          <div className="flex w-full items-center gap-2">
            {statusIcon}
            <span className="text-sm font-medium text-foreground">{label}</span>
            {status === "pending" && (
              <span className="text-xs text-shimmer">执行中</span>
            )}
          </div>
          {hasContent &&
            (isExpanded ? (
              <ChevronUp size={14} className="shrink-0 text-muted-foreground" />
            ) : (
              <ChevronDown size={14} className="shrink-0 text-muted-foreground" />
            ))}
        </Button>

        {isExpanded && (hasContent || hasGenUI) && (
          <div className="px-4 pb-3">
            {hasGenUI ? (
              <div className="mt-1">
                <Suspense
                  fallback={
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Loader2 size={14} className="animate-spin" />
                      加载组件…
                    </div>
                  }
                >
                  <LoadExternalComponent
                    key={(uiComponent as { id: string }).id}
                    stream={stream as ExternalComponentProps["stream"]}
                    message={uiComponent as ExternalComponentProps["message"]}
                    namespace={graphId!}
                    meta={{ status, args, result: result ?? "暂无结果" }}
                  />
                </Suspense>
              </div>
            ) : (
              <>
                {Object.keys(args).length > 0 && (
                  <div className="mt-1">
                    <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      参数
                    </h4>
                    <div className="space-y-1">
                      {Object.entries(args).map(([key, value]) => (
                        <div key={key} className="rounded border border-border">
                          <button
                            onClick={() => toggleArgExpanded(key)}
                            className="flex w-full items-center justify-between bg-muted/30 p-2 text-left text-xs font-medium transition-colors hover:bg-muted/50"
                          >
                            <span className="font-mono">{key}</span>
                            {expandedArgs[key] ? (
                              <ChevronUp size={12} className="text-muted-foreground" />
                            ) : (
                              <ChevronDown size={12} className="text-muted-foreground" />
                            )}
                          </button>
                          {expandedArgs[key] && (
                            <div className="border-t border-border bg-muted/20 p-2">
                              <pre className="m-0 overflow-x-auto whitespace-pre-wrap break-all font-mono text-xs leading-6 text-foreground">
                                {typeof value === "string"
                                  ? value
                                  : JSON.stringify(value, null, 2)}
                              </pre>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {result && (
                  <div className="mt-2">
                    <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      结果
                    </h4>
                    <pre className="m-0 max-h-48 overflow-auto whitespace-pre-wrap break-all rounded border border-border bg-muted/40 p-2 font-mono text-xs leading-6 text-foreground">
                      {typeof result === "string"
                        ? result.length > 500
                          ? result.slice(0, 500) + "…"
                          : result
                        : JSON.stringify(result, null, 2)}
                    </pre>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    );
  },
);

ToolCallBox.displayName = "ToolCallBox";
