"use client";

import React, { useState, useRef, useCallback, useEffect, useMemo, Fragment, FormEvent } from "react";
import { Virtuoso } from "react-virtuoso";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ArrowUp, Square, Plus, CheckCircle, Clock, Circle, FileIcon, FolderGit2, Settings, ChevronUp, FlaskConical, Brain, ShieldAlert } from "lucide-react";
import { ChatMessage } from "@/app/components/ChatMessage";
import { useChatContext } from "@/providers/ChatProvider";
import { cn } from "@/lib/utils";
import { useQueryState } from "nuqs";
import { toast } from "sonner";
import { apiClient } from "@/lib/api-client";

import { useFileUpload } from "@/app/hooks/useFileUpload";
import { ContentBlocksPreview } from "@/app/components/ContentBlocksPreview";
import { UploadProgressList } from "@/app/components/UploadProgress";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import type { ToolCall, TodoItem, SubAgent } from "@/app/types/types";
import type { Message } from "@langchain/langgraph-sdk";
import { SubAgentPanel } from "@/app/components/SubAgentPanel";

interface ChatInterfaceProps {
  assistantId: string;
}

/** Stable empty tool-call array shared by all human messages (memo safety). */
const EMPTY_TOOLCALLS: ToolCall[] = [];

const getStatusIcon = (status: TodoItem["status"], className?: string) => {
  switch (status) {
    case "completed":
      return <CheckCircle size={16} className={cn("text-green-500", className)} />;
    case "in_progress":
      return <Clock size={16} className={cn("text-yellow-500", className)} />;
    default:
      return <Circle size={16} className={cn("text-muted-foreground/70", className)} />;
  }
};

export const ChatInterface = React.memo<ChatInterfaceProps>(({ assistantId }) => {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const [input, setInput] = useState("");
  const [metaOpen, setMetaOpen] = useState<"tasks" | "files" | null>(null);
  const [repoList, setRepoList] = useState<string[]>([]);
  const [selectedRepo, setSelectedRepo] = useState("");
  const [repoDialogOpen, setRepoDialogOpen] = useState(false);
  const [newRepoPath, setNewRepoPath] = useState("");

  // Scroll container ref for auto-scroll
  const scrollContainerRef = useRef<HTMLElement | null>(null);

  // Read threadId from URL — 线程懒创建：首条消息/首次文件上传时才有 id
  const [currentThreadId] = useQueryState("threadId");
  // Reasoning effort chip state (?effort=off|low|medium|high); defaults to high
  const [reasoningEffort, setReasoningEffort] = useQueryState("effort", {
    defaultValue: "high",
  });
  // execute 审批档位（?permission=workspace_write|full_access）。
  // read_only 已移除：用例工作流必须落盘，只读档等于关闭流程；旧链接回落工作区档。
  const [permissionMode, setPermissionMode] = useQueryState("permission", {
    defaultValue: "workspace_write",
  });
  useEffect(() => {
    if (permissionMode === "read_only") setPermissionMode("workspace_write");
  }, [permissionMode, setPermissionMode]);
  // 切到完全访问需要二次确认（dsh: RiskConfirmation）
  const [fullAccessConfirmOpen, setFullAccessConfirmOpen] = useState(false);

  // 需在 useFileUpload 之前解构：ensureThreadId 传给上传 hook 按需建线程
  const {
    messages,
    isLoading,
    sendMessage,
    stopStream,
    interrupt,
    resumeInterrupt,
    ensureThreadId,
    todos,
    files,
    ui,
    isLoadingHistory,
    hasOlderMessages,
    loadOlderMessages,
    historyError,
    threadId,
    getSubAgentFeed,
    isSubAgentTaskClosed,
    subagentVersion,
  } = useChatContext();

  const {
    contentBlocks,
    uploads,
    isUploading,
    handleFileUpload,
    dropRef,
    removeContentBlock,
    clearContentBlocks,
    isDragging,
    handlePaste,
  } = useFileUpload(undefined, currentThreadId ?? undefined, ensureThreadId);

  const REPO_STORAGE_KEY = "smart-test-platform-repos";

  // Load repos: localStorage 手动添加的 + 平台「代码图谱」页保存的受管仓库,合并去重
  useEffect(() => {
    let local: string[] = [];
    try {
      const saved = localStorage.getItem(REPO_STORAGE_KEY);
      if (saved) local = JSON.parse(saved);
    } catch {}
    apiClient
      .get<{ repos: { repo_path: string }[] }>("/codebase/repos")
      .then((res) => {
        const platform: string[] = (res.data?.repos ?? []).map(
          (r) => r.repo_path,
        );
        const merged = [...new Set([...local, ...platform])];
        setRepoList(merged);
        setSelectedRepo((prev) => prev || merged[0] || "");
      })
      .catch(() => {
        // 平台接口不可达时退回 localStorage
        setRepoList(local);
        if (local.length > 0) setSelectedRepo(local[0]);
      });
  }, []);

  // Save repos to localStorage
  const saveRepoList = useCallback((repos: string[]) => {
    setRepoList(repos);
    localStorage.setItem(REPO_STORAGE_KEY, JSON.stringify(repos));
  }, []);

  const handleAddRepo = useCallback(() => {
    const path = newRepoPath.trim();
    if (!path || repoList.includes(path)) return;
    const newList = [...repoList, path];
    saveRepoList(newList);
    setSelectedRepo(path);
    setNewRepoPath("");
    setRepoDialogOpen(false);
  }, [newRepoPath, repoList, saveRepoList]);

  const handleRemoveRepo = useCallback((path: string) => {
    const newList = repoList.filter((r) => r !== path);
    saveRepoList(newList);
    if (selectedRepo === path) {
      setSelectedRepo(newList[0] || "");
    }
  }, [repoList, selectedRepo, saveRepoList]);

  // 子智能体实时操作面板（右侧抽屉）
  const [activitySubAgent, setActivitySubAgent] = useState<SubAgent | null>(null);
  const handleSubAgentActivity = useCallback((sa: SubAgent) => {
    setActivitySubAgent(sa);
  }, []);

  useEffect(() => {
    setActivitySubAgent(null);
  }, [currentThreadId, assistantId]);

  const submitDisabled = isLoading || !assistantId;
  // 审批等待期间不允许并发发消息（dsh：审批接管输入区）
  const approvalPending = !!interrupt;

  const handleSubmit = useCallback(
    (e?: FormEvent) => {
      if (e) {
        e.preventDefault();
      }
      const messageText = input.trim();
      if (
        (!messageText && contentBlocks.length === 0) ||
        isLoading ||
        submitDisabled ||
        approvalPending
      )
        return;
      // Files still converting/uploading — sending now would drop them.
      if (isUploading) {
        toast.error("文件还在上传中，请等待上传完成后再发送");
        return;
      }
      // 每次对话必须挂载代码仓库：未选择时阻断发送并引导选择
      if (!selectedRepo) {
        toast.error("请先选择要分析的代码仓库（会话将挂载该仓库供智能体检索）");
        setRepoDialogOpen(true);
        return;
      }
      // Inject code analysis context into message so agent can see it
      const contextPrefix = `[代码分析上下文 - 可在任何阶段使用此信息辅助分析] 仓库路径: ${selectedRepo}\n\n`;
      // 用户主动发消息 → 强制恢复底部跟随
      isNearBottomRef.current = true;
      sendMessage(contextPrefix + messageText, contentBlocks, {
        repoPath: selectedRepo,
      });
      setInput("");
      clearContentBlocks();
    },
    [input, contentBlocks, isLoading, isUploading, approvalPending, sendMessage, submitDisabled, clearContentBlocks, selectedRepo],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (submitDisabled) return;
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit, submitDisabled],
  );

  // Extract tool calls from messages
  const processedMessages = useMemo(() => {
    if (!messages) return [];
    const messageMap = new Map<
      string,
      { message: Message; toolCalls: ToolCall[] }
    >();

    messages.forEach((message: Message) => {
      if (!message) return;
      if (message.type === "ai") {
        const toolCallsInMessage: Array<{
          id?: string;
          function?: { name?: string; arguments?: unknown };
          name?: string;
          type?: string;
          args?: unknown;
          input?: unknown;
        }> = [];

        if (
          message.additional_kwargs?.tool_calls &&
          Array.isArray(message.additional_kwargs.tool_calls)
        ) {
          toolCallsInMessage.push(...message.additional_kwargs.tool_calls);
        } else if (message.tool_calls && Array.isArray(message.tool_calls)) {
          toolCallsInMessage.push(
            ...message.tool_calls.filter(
              (tc: { name?: string }) => tc.name !== "",
            ),
          );
        } else if (Array.isArray(message.content)) {
          const toolUseBlocks = (message.content as Array<{ type?: string }>).filter(
            (block) => block.type === "tool_use",
          );
          toolCallsInMessage.push(...(toolUseBlocks as typeof toolCallsInMessage));
        }

        const toolCallsWithStatus = toolCallsInMessage.map(
          (tc, i): ToolCall => {
            const name =
              tc.function?.name || tc.name || tc.type || "unknown";
            const args =
              tc.function?.arguments || tc.args || tc.input || {};
            return {
              // Deterministic fallback id: random ids remount tool cards on
              // every recompute and break React reconciliation.
              id: tc.id || `tool-${name}-${i}`,
              name,
              args: typeof args === "object" && args !== null ? args as Record<string, unknown> : {},
              status: "pending" as const,
            };
          },
        );

        messageMap.set(message.id!, { message, toolCalls: toolCallsWithStatus });
      } else if (message.type === "tool") {
        // 历史消息从 SQLite 加载时 tool_call_id 曾并入 additional_kwargs 返回，两处都读
        const toolMsg = message as Message & { tool_call_id?: string };
        const toolCallId =
          toolMsg.tool_call_id ??
          (message.additional_kwargs as { tool_call_id?: string } | undefined)
            ?.tool_call_id;
        if (!toolCallId) return;
        for (const [, data] of Array.from(messageMap.entries())) {
          const idx = data.toolCalls.findIndex((tc) => tc.id === toolCallId);
          if (idx === -1) continue;
          const content =
            typeof message.content === "string"
              ? message.content
              : Array.isArray(message.content)
                ? message.content
                    .map((b) =>
                      typeof b === "string" ? b : (b as { text?: string }).text ?? "",
                    )
                    .join("")
                : "";
          data.toolCalls[idx] = {
            ...data.toolCalls[idx],
            status: "completed" as const,
            result: content,
          };
          break;
        }
      } else if (message.type === "human") {
        // Shared constant: a fresh [] literal per message would defeat
        // React.memo on ChatMessage for every historical message.
        messageMap.set(message.id!, { message, toolCalls: EMPTY_TOOLCALLS });
      }
    });

    // 流已结束（或纯历史查看）时，仍未等到结果的工具调用按已完成渲染：
    // 旧数据缺少 tool_call_id 时结果永远匹配不上，子智能体会一直转「执行中」
    if (!isLoading) {
      for (const [, data] of Array.from(messageMap.entries())) {
        // 跳过空数组：human 消息共享 EMPTY_TOOLCALLS，重新 map 会破坏 memo
        if (data.toolCalls.length === 0) continue;
        data.toolCalls = data.toolCalls.map((tc) =>
          tc.status === "pending" ? { ...tc, status: "completed" as const } : tc,
        );
      }
    }

    return Array.from(messageMap.values());
  }, [messages, isLoading, subagentVersion]);

  // 面板显示的子智能体实时化：点击传入的是当时的快照（status/output 停在
  // 点击那一刻），这里从当前消息流重建，状态与最终输出随流更新
  const liveSubAgent = useMemo(() => {
    if (!activitySubAgent) return null;
    for (const { toolCalls } of processedMessages) {
      const tc = toolCalls.find((t) => t.id === activitySubAgent.id && t.name === "task");
      if (tc) {
        return {
          id: tc.id,
          name: tc.name,
          subAgentName: String(tc.args?.subagent_type ?? ""),
          input: tc.args,
          output: tc.result ? { result: tc.result } : undefined,
          status:
            tc.status === "completed" || isSubAgentTaskClosed(tc.id)
              ? ("completed" as const)
              : tc.status === "error"
                ? ("error" as const)
                : ("active" as const),
        };
      }
    }
    return activitySubAgent;
  }, [activitySubAgent, processedMessages, isSubAgentTaskClosed, subagentVersion]);

  // Grouped todos for display
  const groupedTodos = useMemo(() => ({
    in_progress: todos.filter((t) => t.status === "in_progress"),
    pending: todos.filter((t) => t.status === "pending"),
    completed: todos.filter((t) => t.status === "completed"),
  }), [todos]);

  const hasTasks = todos.length > 0;
  const hasFiles = typeof files === "object" && files !== null && Object.keys(files).length > 0;

  // Filter UI components per message
  const uiMap = useMemo(() => {
    if (!ui || !Array.isArray(ui)) return new Map<string, unknown[]>();
    const map = new Map<string, unknown[]>();
    for (const u of ui) {
      const meta = (u as Record<string, unknown>)?.metadata as Record<string, unknown> | undefined;
      const msgId = meta?.message_id as string | undefined;
      if (msgId) {
        const arr = map.get(msgId) ?? [];
        arr.push(u);
        map.set(msgId, arr);
      }
    }
    return map;
  }, [ui]);

  // Auto-scroll to bottom on new messages — ONLY when the user is already
  // near the bottom. Streaming in background (subagent/tool results) must
  // never yank the viewport while the user is reading older messages.
  const lastMessageId = messages?.at(-1)?.id;
  const isNearBottomRef = useRef(true);

  useEffect(() => {
    const el = scrollContainerRef.current;
    // 新会话从底部开始跟随（Virtuoso initialTopMostItemIndex 已定位到底部）
    isNearBottomRef.current = true;
    if (!el) return;
    const onScroll = () => {
      isNearBottomRef.current =
        el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
    // Re-attach when the Virtuoso scroller mounts/unmounts (list empty ↔ non-empty)
  }, [processedMessages.length > 0, currentThreadId]);

  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el || !isNearBottomRef.current) return;
    const frameId = window.requestAnimationFrame(() => {
      el.scrollTo({
        top: el.scrollHeight,
        behavior: "auto",
      });
    });
    return () => window.cancelAnimationFrame(frameId);
  }, [lastMessageId, messages?.length]);

  // Virtualization: when older pages are prepended (loading history), tell
  // Virtuoso via firstItemIndex so it keeps the viewport anchored instead of
  // jumping. Detected by the oldest message id changing with a length gain.
  const [firstItemIndex, setFirstItemIndex] = useState(1_000_000);
  const prevListRef = useRef<{ oldest?: string; len: number }>({ len: 0 });
  useEffect(() => {
    const oldest = processedMessages[0]?.message.id;
    const prev = prevListRef.current;
    if (
      prev.oldest &&
      oldest &&
      oldest !== prev.oldest &&
      processedMessages.length > prev.len
    ) {
      setFirstItemIndex((v) => Math.max(1, v - (processedMessages.length - prev.len)));
    }
    prevListRef.current = { oldest, len: processedMessages.length };
  }, [processedMessages]);

  const renderItem = useCallback(
    (index: number, data: { message: Message; toolCalls: ToolCall[] }) => {
      const isLastMessage = index === processedMessages.length - 1;
      const messageUi = uiMap.get(data.message.id ?? "");
      // min-h: an empty streaming placeholder (no content/tool_calls yet)
      // otherwise measures 0px, which react-virtuoso warns about.
      return (
        <div className="mx-auto min-h-[1px] w-full max-w-[1024px] px-6">
          <ChatMessage
            message={data.message}
            toolCalls={data.toolCalls}
            isStreaming={isLastMessage && isLoading}
            ui={messageUi}
            stream={undefined}
            graphId={isLastMessage ? assistantId : undefined}
            onSubAgentActivity={handleSubAgentActivity}
            isSubAgentClosed={isSubAgentTaskClosed}
          />
        </div>
      );
    },
    [processedMessages.length, uiMap, isLoading, assistantId, handleSubAgentActivity, isSubAgentTaskClosed],
  );

  const ListHeader = useMemo(
    () =>
      function VirtuosoListHeader() {
        return hasOlderMessages ? (
          <div className="mb-4 flex justify-center pt-4">
            <Button
              variant="ghost"
              size="sm"
              onClick={loadOlderMessages}
              disabled={isLoadingHistory}
              className="text-xs text-muted-foreground"
            >
              {isLoadingHistory ? "加载中..." : "加载更早的消息"}
              {!isLoadingHistory && <ChevronUp size={14} className="ml-1" />}
            </Button>
          </div>
        ) : (
          <div className="pt-4" />
        );
      },
    [hasOlderMessages, loadOlderMessages, isLoadingHistory],
  );

  const virtuosoComponents = useMemo(() => ({ Header: ListHeader }), [ListHeader]);

  return (
    // 行布局：主列（消息+输入）+ 右侧子智能体面板并排，互不遮挡；
    // 面板未打开时主列占满
    <div className="relative flex min-h-0 flex-1 overflow-hidden">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      {/* Message list area (virtualized: long threads render only the
          visible window instead of keeping every message in the DOM) */}
      {processedMessages.length > 0 ? (
        <Virtuoso
          data={processedMessages}
          scrollerRef={(ref) => {
            scrollContainerRef.current =
              ref instanceof HTMLElement ? ref : null;
          }}
          computeItemKey={(_, item) => item.message.id ?? `item-${_}`}
          firstItemIndex={firstItemIndex}
          initialTopMostItemIndex={Math.max(0, processedMessages.length - 1)}
          itemContent={renderItem}
          components={virtuosoComponents}
          className="flex-1 overflow-y-auto overflow-x-hidden overscroll-contain"
        />
      ) : historyError && threadId ? (
        <div className="flex-1 flex flex-col items-center justify-center p-8">
          <p className="text-lg font-medium text-destructive">
            无法加载会话消息
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            该会话状态过大，暂时无法加载。请尝试新建对话。
          </p>
        </div>
      ) : (
        <div className="flex flex-1 flex-col items-center justify-center p-8">
          <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-[14px] bg-primary text-primary-foreground">
            <FlaskConical className="h-5 w-5" />
          </div>
          <p className="text-lg font-medium leading-8">
            开始你的测试任务
          </p>
          <p className="mt-1.5 max-w-md text-center text-[13px] leading-6 text-muted-foreground">
            上传需求文档生成测试用例、分析代码仓库，或直接描述你的测试问题
          </p>
        </div>
      )}

      {/* Input area */}
      <div className="flex-shrink-0 bg-background">
        <div
          ref={dropRef}
          className={cn(
            "mx-4 mb-6 flex flex-shrink-0 flex-col overflow-hidden rounded-[22px] border border-border bg-background",
            "mx-auto w-[calc(100%-32px)] max-w-[1024px] transition-colors duration-200 ease-[cubic-bezier(0.4,0,0.2,1)]",
            "surface-float",
            isDragging && "border-2 border-dotted border-brand",
          )}
        >
          {/* Task progress + files bar */}
          {(hasTasks || hasFiles) && (
            <div className="flex max-h-72 flex-col overflow-y-auto border-b border-border bg-muted empty:hidden">
              {!metaOpen && (
                <div className="grid grid-cols-[1fr_auto_auto] items-center">
                  {hasTasks && (() => {
                    const activeTask = todos.find((t) => t.status === "in_progress");
                    const totalTasks = todos.length;
                    const completedCount = groupedTodos.completed.length + groupedTodos.in_progress.length;
                    const isCompleted = totalTasks === completedCount;

                    return (
                      <button
                        type="button"
                        onClick={() => setMetaOpen((prev) => prev === "tasks" ? null : "tasks")}
                        className="grid w-full cursor-pointer grid-cols-[auto_auto_1fr] items-center gap-3 px-[18px] py-3 text-left"
                        aria-expanded={metaOpen === "tasks"}
                      >
                        {isCompleted ? (
                          <>
                            <CheckCircle size={16} className="text-green-500" />
                            <span className="ml-[1px] min-w-0 truncate text-sm">所有任务已完成</span>
                          </>
                        ) : activeTask ? (
                          <>
                            {getStatusIcon(activeTask.status)}
                            <span className="ml-[1px] min-w-0 truncate text-sm">
                              任务 {completedCount} / {totalTasks}
                            </span>
                            <span className="min-w-0 gap-2 truncate text-sm text-muted-foreground">
                              {activeTask.content}
                            </span>
                          </>
                        ) : (
                          <>
                            <Circle size={16} className="text-muted-foreground/70" />
                            <span className="ml-[1px] min-w-0 truncate text-sm">
                              任务 {completedCount} / {totalTasks}
                            </span>
                          </>
                        )}
                      </button>
                    );
                  })()}
                  {hasFiles && (
                    <button
                      type="button"
                      onClick={() => setMetaOpen((prev) => prev === "files" ? null : "files")}
                      className="flex flex-shrink-0 cursor-pointer items-center gap-2 px-[18px] py-3 text-left text-sm"
                      aria-expanded={metaOpen === "files"}
                    >
                      <FileIcon size={16} />
                      文件
                      <span className="h-4 min-w-4 rounded-full bg-[#2F6868] px-0.5 text-center text-[10px] leading-[16px] text-white">
                        {Object.keys(files!).length}
                      </span>
                    </button>
                  )}
                </div>
              )}

              {metaOpen && (
                <div className="px-[18px] pb-3">
                  {metaOpen === "tasks" && (
                    Object.entries(groupedTodos)
                      .filter(([, items]) => items.length > 0)
                      .map(([status, items]) => (
                        <div key={status} className="mb-3">
                          <h3 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                            {{ pending: "待处理", in_progress: "进行中", completed: "已完成" }[status]}
                          </h3>
                          <div className="grid grid-cols-[auto_1fr] gap-3 rounded-sm p-1 pl-0 text-sm">
                            {items.map((todo, idx) => (
                              <Fragment key={`${status}_${todo.id}_${idx}`}>
                                {getStatusIcon(todo.status, "mt-0.5")}
                                <span className="break-words">{todo.content}</span>
                              </Fragment>
                            ))}
                          </div>
                        </div>
                      ))
                  )}
                  {metaOpen === "files" && (
                    <div className="space-y-1">
                      {Object.keys(files!).map((path) => (
                        <div key={path} className="flex items-center gap-2 rounded border border-border bg-muted/30 px-3 py-1.5 text-xs">
                          <FileIcon size={14} className="text-muted-foreground" />
                          <span className="font-mono">{path}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  <button
                    type="button"
                    className="mt-2 text-xs text-muted-foreground hover:text-foreground"
                    onClick={() => setMetaOpen(null)}
                  >
                    收起
                  </button>
                </div>
              )}
            </div>
          )}

          <form onSubmit={handleSubmit} className="flex flex-col">
            {/* 审批卡片：越权操作等待用户决策（dsh 式接管输入区） */}
            {interrupt && (
              <div className="mx-3 mt-3 rounded-lg border border-amber-500/40 bg-amber-500/5 px-4 py-3">
                <div className="flex items-center gap-2 text-sm font-medium text-amber-600">
                  <ShieldAlert className="h-4 w-4 shrink-0" />
                  <span>
                    {interrupt.toolName === "execute"
                      ? "命令执行需要审批"
                      : "文件写入需要审批（只读模式）"}
                  </span>
                  <span className="text-xs font-normal text-muted-foreground">
                    （{interrupt.toolName}）
                  </span>
                </div>
                <pre className="mt-2 max-h-32 overflow-auto rounded bg-muted px-3 py-2 text-xs whitespace-pre-wrap break-all">
                  {interrupt.command ||
                    String(interrupt.args?.file_path ?? interrupt.args?.path ?? "") ||
                    JSON.stringify(interrupt.args, null, 2)}
                </pre>
                <div className="mt-3 flex justify-end gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => resumeInterrupt("reject")}
                  >
                    拒绝
                  </Button>
                  <Button type="button" size="sm" onClick={() => resumeInterrupt("approve")}>
                    允许一次
                  </Button>
                </div>
              </div>
            )}
            <UploadProgressList uploads={uploads} />
            <ContentBlocksPreview
              blocks={contentBlocks}
              onRemove={removeContentBlock}
            />
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              onPaste={handlePaste}
              placeholder={isLoading ? "运行中..." : "输入您的消息..."}
              className="flex-1 resize-none border-0 bg-transparent px-[18px] pb-[13px] pt-[14px] text-sm leading-7 text-foreground outline-none placeholder:text-muted-foreground"
              rows={1}
            />
            <div className="flex justify-between gap-2 p-3">
              <div className="flex items-center gap-4">
                <label
                  htmlFor="file-input"
                  className="flex cursor-pointer items-center gap-2 text-muted-foreground hover:text-foreground"
                >
                  <Plus className="size-5" />
                  <span className="text-sm">上传 PDF 或图片</span>
                </label>
                <input
                  id="file-input"
                  type="file"
                  onChange={handleFileUpload}
                  multiple
                  accept="image/jpeg,image/png,image/gif,image/webp,application/pdf,text/markdown"
                  className="hidden"
                />
                <div className="flex items-center gap-2 border-l border-border pl-4">
                  {/* Repo selector */}
                  <div className="flex items-center gap-1">
                    <FolderGit2 size={14} className="text-muted-foreground" />
                    <select
                      value={selectedRepo}
                      onChange={(e) => setSelectedRepo(e.target.value)}
                      className="h-7 max-w-48 rounded border border-border bg-transparent px-1.5 text-xs text-foreground outline-none focus:border-primary"
                    >
                      <option value="">选择仓库</option>
                      {repoList.map((r) => (
                        <option key={r} value={r}>{r}</option>
                      ))}
                    </select>
                    <button
                      type="button"
                      onClick={() => setRepoDialogOpen(true)}
                      className="flex h-7 w-7 items-center justify-center rounded border border-border text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                      title="管理仓库"
                    >
                      <Settings size={12} />
                    </button>
                  </div>
                  {/* Reasoning effort chip (per conversation, ?effort=) */}
                  <div className="flex items-center gap-1">
                    <Brain size={14} className="text-muted-foreground" />
                    <Select
                      value={reasoningEffort === "" ? null : reasoningEffort}
                      onValueChange={(v) => setReasoningEffort(v ?? "")}
                    >
                      <SelectTrigger
                        size="sm"
                        className="h-7 gap-1 border border-border bg-transparent px-1.5 text-xs text-foreground"
                        title="思考强度（需要模型支持 reasoning_effort）"
                      >
                        <SelectValue placeholder="思考：关" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="">思考：关</SelectItem>
                        <SelectItem value="low">思考：低</SelectItem>
                        <SelectItem value="medium">思考：中</SelectItem>
                        <SelectItem value="high">思考：高</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  {/* 权限档位（per conversation, ?permission=）—— 工作区/完全访问 */}
                  <div className="flex items-center gap-1 border-l border-border pl-4">
                    <ShieldAlert
                      size={14}
                      className={cn(
                        "text-muted-foreground",
                        permissionMode === "full_access" && "text-destructive",
                      )}
                    />
                    <Select
                      value={permissionMode}
                      onValueChange={(v) => {
                        if (v === "full_access" && permissionMode !== "full_access") {
                          setFullAccessConfirmOpen(true);
                          return;
                        }
                        setPermissionMode(v ?? "workspace_write");
                      }}
                    >
                      <SelectTrigger
                        size="sm"
                        className="h-7 gap-1 border border-border bg-transparent px-1.5 text-xs text-foreground"
                        title="权限档位：工作区=文件限工作区、只读命令白名单自动放行、其余命令审批；完全访问=全部放行"
                      >
                        <SelectValue placeholder="工作区" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="workspace_write">工作区</SelectItem>
                        <SelectItem value="full_access">完全访问</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </div>
              <div className="flex justify-end gap-2">
                {isLoading ? (
                  <Button
                    type="button"
                    onClick={stopStream}
                    className="h-9 w-9 rounded-full bg-destructive p-0 text-destructive-foreground hover:bg-destructive/90"
                    title="停止生成"
                  >
                    <Square className="h-3.5 w-3.5" />
                  </Button>
                ) : (
                  <Button
                    type="submit"
                    onClick={handleSubmit}
                    disabled={
                      submitDisabled ||
                      approvalPending ||
                      isUploading ||
                      (!input.trim() && contentBlocks.length === 0)
                    }
                    className="h-9 w-9 rounded-full bg-brand p-0 text-white hover:bg-brand-600 disabled:opacity-40"
                    title={approvalPending ? "等待命令审批" : isUploading ? "文件上传中…" : "发送"}
                  >
                    <ArrowUp className="h-4.5 w-4.5" />
                  </Button>
                )}
              </div>
            </div>
          </form>
        </div>
      </div>

      {/* Full Access Risk Confirmation (dsh: RiskConfirmation) */}
      <Dialog open={fullAccessConfirmOpen} onOpenChange={setFullAccessConfirmOpen}>
        <DialogContent className="sm:max-w-[400px]">
          <DialogHeader>
            <DialogTitle>开启完全访问？</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            完全访问模式下，智能体执行任何命令（含白名单外的 shell 命令）都不再需要你的确认。
            仅在自己完全信任当前任务时使用。
          </p>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" size="sm" onClick={() => setFullAccessConfirmOpen(false)}>
              取消
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => {
                setPermissionMode("full_access");
                setFullAccessConfirmOpen(false);
              }}
            >
              确认开启
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Add Repo Dialog */}
      <Dialog open={repoDialogOpen} onOpenChange={setRepoDialogOpen}>
        <DialogContent className="sm:max-w-[450px]">
          <DialogHeader>
            <DialogTitle>管理代码仓库</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 py-2">
            {repoList.length > 0 && (
              <div className="space-y-1.5">
                {repoList.map((repo) => (
                  <div key={repo} className="flex items-center justify-between rounded border border-border px-3 py-1.5">
                    <span className="truncate text-xs font-mono">{repo}</span>
                    <button
                      type="button"
                      onClick={() => handleRemoveRepo(repo)}
                      className="ml-2 text-xs text-muted-foreground hover:text-destructive"
                    >
                      删除
                    </button>
                  </div>
                ))}
              </div>
            )}
            <div className="flex items-center gap-2">
              <Input
                placeholder="输入仓库路径，如 D:/projects/my-app"
                value={newRepoPath}
                onChange={(e) => setNewRepoPath(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleAddRepo()}
                className="text-xs"
              />
              <Button size="sm" onClick={handleAddRepo} disabled={!newRepoPath.trim()}>
                添加
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
      </div>{/* 主列结束 */}

      {/* 子智能体实时操作面板：与主列并排（大屏）/覆盖（小屏）。
          feed 拷贝成新数组——store 原地变更同一引用，React.memo 会认为
          props 没变而跳过重渲染，面板就永远停在打开那一刻（「正在启动…」） */}
      <SubAgentPanel
        subAgent={liveSubAgent}
        feed={
          liveSubAgent ? [...getSubAgentFeed(liveSubAgent.id)] : []
        }
        onClose={() => setActivitySubAgent(null)}
      />
    </div>
  );
});

ChatInterface.displayName = "ChatInterface";
