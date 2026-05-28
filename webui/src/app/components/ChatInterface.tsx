"use client";

import React, { useState, useRef, useCallback, useEffect, useMemo, Fragment, FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { ArrowUp, Square, Plus, CheckCircle, Clock, Circle, FileIcon, FolderGit2, Hash, Settings, BookOpen } from "lucide-react";
import { ChatMessage } from "@/app/components/ChatMessage";
import { useChatContext } from "@/providers/ChatProvider";
import { cn } from "@/lib/utils";
import { useQueryState } from "nuqs";
import { Virtuoso, type VirtuosoHandle } from "react-virtuoso";

/** Extract task IDs like M72-177558 from text */
function extractTaskIds(text: string): string[] {
  const matches = text.match(/\b[A-Za-z][A-Za-z0-9]*-\d{3,8}\b/g);
  if (!matches) return [];
  return [...new Set(matches)];
}
import { useFileUpload } from "@/app/hooks/useFileUpload";
import { ContentBlocksPreview } from "@/app/components/ContentBlocksPreview";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import type { ToolCall, TodoItem } from "@/app/types/types";
import type { Message } from "@langchain/langgraph-sdk";
import { useWikis, useCreateWiki, useDeleteWiki } from "@/lib/api/useWikis";

interface ChatInterfaceProps {
  assistantId: string;
}

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
  const [taskId, setTaskId] = useState("");
  const [repoDialogOpen, setRepoDialogOpen] = useState(false);
  const [taskDialogOpen, setTaskDialogOpen] = useState(false);
  const [newRepoPath, setNewRepoPath] = useState("");

  // Virtuoso virtual scroll refs and state
  const virtuosoRef = useRef<VirtuosoHandle>(null);
  const [isAtBottom, setIsAtBottom] = useState(true);

  // Wiki selector state
  const WIKI_STORAGE_KEY = "smart-test-platform-wiki";
  const [selectedWiki, setSelectedWiki] = useState("");
  const [wikiDialogOpen, setWikiDialogOpen] = useState(false);
  const [newWikiName, setNewWikiName] = useState("");
  const [newWikiPath, setNewWikiPath] = useState("");
  const { data: wikiData } = useWikis();
  const { trigger: createWiki } = useCreateWiki();
  const { trigger: deleteWiki } = useDeleteWiki();
  const wikiList = wikiData?.data ?? [];

  // Load selected wiki from localStorage
  useEffect(() => {
    try {
      const saved = localStorage.getItem(WIKI_STORAGE_KEY);
      if (saved) setSelectedWiki(saved);
    } catch {}
  }, []);

  const {
    contentBlocks,
    handleFileUpload,
    dropRef,
    removeContentBlock,
    clearContentBlocks,
    isDragging,
    handlePaste,
  } = useFileUpload();

  const REPO_STORAGE_KEY = "smart-test-platform-repos";
  const TASK_MAP_STORAGE_KEY = "smart-test-platform-task-map";

  // Read threadId from URL to persist taskId per thread
  const [currentThreadId] = useQueryState("threadId");

  // Load repos from localStorage (repo is global, task is per-conversation)
  useEffect(() => {
    try {
      const saved = localStorage.getItem(REPO_STORAGE_KEY);
      if (saved) {
        const repos: string[] = JSON.parse(saved);
        setRepoList(repos);
        if (repos.length > 0) setSelectedRepo(repos[0]);
      }
    } catch {}
  }, []);

  // Load/clear taskId when switching threads
  useEffect(() => {
    if (!currentThreadId) {
      // No thread (new chat) — clear task
      setTaskId("");
      return;
    }
    // Existing thread — restore its task from localStorage (if saved)
    try {
      const mapRaw = localStorage.getItem(TASK_MAP_STORAGE_KEY);
      const map: Record<string, string> = mapRaw ? JSON.parse(mapRaw) : {};
      if (map[currentThreadId] !== undefined) {
        setTaskId(map[currentThreadId]);
      }
      // If not saved yet (new thread after first message), don't overwrite
    } catch {}
  }, [currentThreadId]);

  // Save taskId for current thread whenever it changes (debounced via dialog close)
  const persistTaskForThread = useCallback((threadId: string | null, task: string) => {
    if (!threadId) return;
    try {
      const mapRaw = localStorage.getItem(TASK_MAP_STORAGE_KEY);
      const map: Record<string, string> = mapRaw ? JSON.parse(mapRaw) : {};
      if (task) {
        map[threadId] = task;
      } else {
        delete map[threadId];
      }
      localStorage.setItem(TASK_MAP_STORAGE_KEY, JSON.stringify(map));
    } catch {}
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

  // Close task dialog and persist for current thread
  const handleCloseTaskDialog = useCallback(() => {
    persistTaskForThread(currentThreadId, taskId);
    setTaskDialogOpen(false);
  }, [currentThreadId, taskId, persistTaskForThread]);

  const {
    stream,
    messages,
    isLoading,
    sendMessage,
    stopStream,
    todos,
    files,
    ui,
    isLoadingHistory,
    hasOlderMessages,
    loadOlderMessages,
  } = useChatContext();

  const submitDisabled = isLoading || !assistantId;

  const handleSubmit = useCallback(
    (e?: FormEvent) => {
      if (e) {
        e.preventDefault();
      }
      const messageText = input.trim();
      if (
        (!messageText && contentBlocks.length === 0) ||
        isLoading ||
        submitDisabled
      )
        return;
      // Inject code analysis context into message so agent can see it
      const ids = taskId ? extractTaskIds(taskId) : [];
      const wikiContext = selectedWiki
        ? `\n[Wiki 知识库] 当前查询目标: ${selectedWiki}`
        : "";
      const contextPrefix = (selectedRepo || ids.length > 0 || selectedWiki)
        ? `[代码分析上下文 - 可在任何阶段使用此信息辅助分析]${selectedRepo ? ` 仓库路径: ${selectedRepo}` : ""}${ids.length > 0 ? ` 任务单号: ${ids.join(", ")}` : ""}${wikiContext}\n\n`
        : "";
      sendMessage(contextPrefix + messageText, contentBlocks, {
        repoPath: selectedRepo || undefined,
        taskId: taskId || undefined,
      });
      // Persist taskId so it survives thread creation
      if (taskId && currentThreadId) {
        persistTaskForThread(currentThreadId, taskId);
      }
      setInput("");
      clearContentBlocks();
    },
    [input, contentBlocks, isLoading, sendMessage, submitDisabled, clearContentBlocks],
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
          toolCallsInMessage.push(...(toolUseBlocks as any[]));
        }

        const toolCallsWithStatus = toolCallsInMessage.map(
          (tc): ToolCall => {
            const name =
              tc.function?.name || tc.name || tc.type || "unknown";
            const args =
              tc.function?.arguments || tc.args || tc.input || {};
            return {
              id: tc.id || `tool-${Math.random()}`,
              name,
              args: typeof args === "object" && args !== null ? args as Record<string, unknown> : {},
              status: "pending" as const,
            };
          },
        );

        messageMap.set(message.id!, { message, toolCalls: toolCallsWithStatus });
      } else if (message.type === "tool") {
        const toolCallId = (message as any).tool_call_id;
        if (!toolCallId) return;
        for (const [, data] of Array.from(messageMap.entries())) {
          const idx = data.toolCalls.findIndex((tc) => tc.id === toolCallId);
          if (idx === -1) continue;
          const content =
            typeof message.content === "string"
              ? message.content
              : Array.isArray(message.content)
                ? message.content
                    .map((b: any) =>
                      typeof b === "string" ? b : b.text ?? "",
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
        messageMap.set(message.id!, { message, toolCalls: [] });
      }
    });

    return Array.from(messageMap.values());
  }, [messages]);

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

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Message list area */}
      {processedMessages.length > 0 ? (
        <Virtuoso
          ref={virtuosoRef}
          data={processedMessages}
          followOutput={isAtBottom ? "smooth" : false}
          atBottomStateChange={setIsAtBottom}
          atTopStateChange={(atTop) => {
            if (atTop && hasOlderMessages && !isLoadingHistory) {
              loadOlderMessages();
            }
          }}
          increaseViewportBy={{ top: 200, bottom: 200 }}
          defaultItemHeight={80}
          components={{
            Header: () => isLoadingHistory ? (
              <div className="flex justify-center py-4">
                <span className="text-sm text-muted-foreground">加载中...</span>
              </div>
            ) : null,
          }}
          itemContent={(index, data) => {
            const isLastMessage = index === processedMessages.length - 1;
            const messageUi = uiMap.get(data.message.id ?? "");
            return (
              <div className="mx-auto w-full max-w-[1024px] px-6">
                <ChatMessage
                  message={data.message}
                  toolCalls={data.toolCalls}
                  isStreaming={isLastMessage && isLoading}
                  ui={messageUi}
                  stream={isLastMessage ? stream : undefined}
                  graphId={isLastMessage ? assistantId : undefined}
                />
              </div>
            );
          }}
        />
      ) : (
        <div className="flex-1 flex flex-col items-center justify-center p-8">
          <p className="text-lg font-medium text-muted-foreground">
            智能测试平台
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            输入消息开始对话
          </p>
        </div>
      )}

      {/* Input area */}
      <div className="flex-shrink-0 bg-background">
        <div
          ref={dropRef}
          className={cn(
            "mx-4 mb-6 flex flex-shrink-0 flex-col overflow-hidden rounded-xl border border-border bg-background",
            "mx-auto w-[calc(100%-32px)] max-w-[1024px] transition-colors duration-200 ease-in-out",
            isDragging && "border-primary border-2 border-dotted",
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
                  {/* Task ID button */}
                  <button
                    type="button"
                    onClick={() => setTaskDialogOpen(true)}
                    className={cn(
                      "flex h-7 items-center gap-1 rounded border px-2 text-xs",
                      taskId
                        ? "border-primary bg-primary/10 text-primary"
                        : "border-border text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                    )}
                  >
                    <Hash size={12} />
                    {taskId ? `任务 (${extractTaskIds(taskId).length}个)` : "任务单号"}
                  </button>
                  {/* Wiki selector */}
                  <div className="flex items-center gap-1">
                    <BookOpen size={14} className="text-muted-foreground" />
                    <select
                      value={selectedWiki}
                      onChange={(e) => {
                        setSelectedWiki(e.target.value);
                        localStorage.setItem(WIKI_STORAGE_KEY, e.target.value);
                      }}
                      className="h-7 max-w-40 rounded border border-border bg-transparent px-1.5 text-xs text-foreground outline-none focus:border-primary"
                    >
                      <option value="">全部知识库</option>
                      {wikiList.map((w) => (
                        <option key={w.name} value={w.name}>{w.name}</option>
                      ))}
                    </select>
                    <button
                      type="button"
                      onClick={() => setWikiDialogOpen(true)}
                      className="flex h-7 w-7 items-center justify-center rounded border border-border text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                      title="管理知识库"
                    >
                      <Settings size={12} />
                    </button>
                  </div>
                </div>
              </div>
              <div className="flex justify-end gap-2">
                <Button
                  type={isLoading ? "button" : "submit"}
                  variant={isLoading ? "destructive" : "default"}
                  onClick={isLoading ? stopStream : handleSubmit}
                  disabled={
                    !isLoading &&
                    (submitDisabled ||
                      (!input.trim() && contentBlocks.length === 0))
                  }
                >
                  {isLoading ? (
                    <>
                      <Square size={14} />
                      <span>停止</span>
                    </>
                  ) : (
                    <>
                      <ArrowUp size={18} />
                      <span>发送</span>
                    </>
                  )}
                </Button>
              </div>
            </div>
          </form>
        </div>
      </div>

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

      {/* Task ID Dialog */}
      <Dialog open={taskDialogOpen} onOpenChange={(open) => { if (!open) handleCloseTaskDialog(); }}>
        <DialogContent className="sm:max-w-[450px]">
          <DialogHeader>
            <DialogTitle>任务单号</DialogTitle>
          </DialogHeader>
          <div className="grid gap-2 py-2">
            <textarea
              value={taskId}
              onChange={(e) => setTaskId(e.target.value)}
              placeholder={"输入任务单号，多个用逗号或换行分隔\n例如：\nM72-172556\nM72-172557\nM72-172558"}
              className="min-h-[120px] resize-none rounded-md border border-border bg-transparent px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus:border-primary"
            />
          </div>
          <DialogFooter>
            <Button size="sm" onClick={handleCloseTaskDialog}>确定</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Wiki Management Dialog */}
      <Dialog open={wikiDialogOpen} onOpenChange={setWikiDialogOpen}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>管理 Wiki 知识库</DialogTitle>
            <DialogDescription>
              添加或删除 wiki-mcp 知识库目录，修改后自动同步到配置文件。
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-3 py-2">
            {wikiList.length > 0 && (
              <div className="space-y-1.5">
                {wikiList.map((wiki) => (
                  <div key={wiki.name} className="flex items-center justify-between rounded border border-border px-3 py-1.5">
                    <div className="min-w-0 flex-1">
                      <span className="text-xs font-medium">{wiki.name}</span>
                      <span className="ml-2 truncate text-xs text-muted-foreground font-mono">{wiki.path}</span>
                    </div>
                    <button
                      type="button"
                      onClick={async () => {
                        await deleteWiki(wiki.name);
                        if (selectedWiki === wiki.name) {
                          setSelectedWiki("");
                          localStorage.setItem(WIKI_STORAGE_KEY, "");
                        }
                      }}
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
                placeholder="名称，如 test-knowledge"
                value={newWikiName}
                onChange={(e) => setNewWikiName(e.target.value)}
                className="text-xs"
                style={{ flex: 1 }}
              />
              <Input
                placeholder="路径，如 C:/llm_test2/test"
                value={newWikiPath}
                onChange={(e) => setNewWikiPath(e.target.value)}
                className="text-xs"
                style={{ flex: 2 }}
              />
              <Button
                size="sm"
                disabled={!newWikiName.trim() || !newWikiPath.trim()}
                onClick={async () => {
                  await createWiki({ name: newWikiName.trim(), path: newWikiPath.trim() });
                  setNewWikiName("");
                  setNewWikiPath("");
                }}
              >
                添加
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
});

ChatInterface.displayName = "ChatInterface";
