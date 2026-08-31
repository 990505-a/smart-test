"use client";

import {
  startTransition,
  useEffect,
  useMemo,
  useState,
  useRef,
  useCallback,
} from "react";
import { format } from "date-fns";
import { Loader2, MessageSquare, Trash2 } from "lucide-react";
import { useQueryState } from "nuqs";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { cn } from "@/lib/utils";
import type { ThreadItem } from "@/app/hooks/useThreads";
import { useThreads } from "@/app/hooks/useThreads";
import { getFastapiUrl } from "@/lib/config";

const GROUP_LABELS = {
  today: "今天",
  yesterday: "昨天",
  week: "本周",
  older: "更早",
} as const;

function formatTime(date: Date, now = new Date()): string {
  const diff = now.getTime() - date.getTime();
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));

  if (days === 0) return format(date, "HH:mm");
  if (days === 1) return "昨天";
  if (days < 7) return format(date, "EEEE");
  return format(date, "MM/dd");
}

function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center p-8 text-center">
      <p className="text-sm text-destructive">加载对话列表失败</p>
      <p className="mt-1 max-w-[200px] break-words text-xs text-muted-foreground">{message}</p>
      {onRetry && (
        <Button variant="outline" size="sm" className="mt-3" onClick={onRetry}>
          重试
        </Button>
      )}
    </div>
  );
}

function LoadingState() {
  return (
    <div className="space-y-2 p-3">
      {Array.from({ length: 8 }).map((_, i) => (
        <Skeleton key={i} className="h-8 w-full" />
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center p-8 text-center">
      <MessageSquare className="mb-2 h-8 w-8 text-muted-foreground/40" />
      <p className="text-[13px] text-muted-foreground">暂无对话</p>
    </div>
  );
}

interface ThreadListProps {
  onThreadSelect: (id: string) => void;
  onMutateReady?: (mutate: () => void) => void;
}

export function ThreadList({
  onThreadSelect,
  onMutateReady,
}: ThreadListProps) {
  const [currentThreadId] = useQueryState("threadId");
  const [, setCurrentThreadId] = useQueryState("threadId");
  const [deletingThreadId, setDeletingThreadId] = useState<string | null>(null);
  const [deleteAllOpen, setDeleteAllOpen] = useState(false);
  const [deletingAll, setDeletingAll] = useState(false);

  const threads = useThreads();

  // Flatten pages into a single list
  const flattened = useMemo(() => {
    if (!threads.data) return [];
    const all: ThreadItem[] = [];
    for (const page of threads.data) {
      all.push(...page.threads);
    }
    return all;
  }, [threads.data]);

  const isLoadingMore =
    threads.size > 0 && threads.data?.[threads.size - 1] == null;
  const isEmpty = threads.data?.at(0)?.threads.length === 0;
  const lastPageThreads = threads.data?.at(-1)?.threads.length ?? 0;
  const isReachingEnd = isEmpty || lastPageThreads < 20;

  // Group threads by time
  const grouped = useMemo(() => {
    const now = new Date();
    const groups: Record<keyof typeof GROUP_LABELS, ThreadItem[]> = {
      today: [],
      yesterday: [],
      week: [],
      older: [],
    };

    flattened.forEach((thread) => {
      const diff = now.getTime() - thread.updatedAt.getTime();
      const days = Math.floor(diff / (1000 * 60 * 60 * 24));

      if (days === 0) {
        groups.today.push(thread);
      } else if (days === 1) {
        groups.yesterday.push(thread);
      } else if (days < 7) {
        groups.week.push(thread);
      } else {
        groups.older.push(thread);
      }
    });

    return groups;
  }, [flattened]);

  // Expose thread list revalidation to parent component
  const onMutateReadyRef = useRef(onMutateReady);
  const mutateRef = useRef(threads.mutate);
  const mutateTimerRef = useRef<number | null>(null);

  useEffect(() => {
    onMutateReadyRef.current = onMutateReady;
  }, [onMutateReady]);

  useEffect(() => {
    mutateRef.current = threads.mutate;
  }, [threads.mutate]);

  useEffect(() => {
    return () => {
      if (mutateTimerRef.current !== null) {
        window.clearTimeout(mutateTimerRef.current);
      }
    };
  }, []);

  const mutateFn = useCallback(() => {
    if (typeof window === "undefined") {
      startTransition(() => {
        mutateRef.current();
      });
      return;
    }

    if (mutateTimerRef.current !== null) {
      window.clearTimeout(mutateTimerRef.current);
    }

    mutateTimerRef.current = window.setTimeout(() => {
      startTransition(() => {
        mutateRef.current();
      });
      mutateTimerRef.current = null;
    }, 80);
  }, []);

  useEffect(() => {
    onMutateReadyRef.current?.(mutateFn);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleDeleteThread = useCallback(
    async (threadId: string, e: React.MouseEvent) => {
      e.stopPropagation();

      if (!confirm("确定要删除这条对话吗？此操作无法撤销。")) {
        return;
      }

      setDeletingThreadId(threadId);
      try {
        const apiBase = getFastapiUrl();
        const response = await fetch(`${apiBase}/api/v2/threads/${threadId}`, { method: "DELETE" });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        if (currentThreadId === threadId) {
          setCurrentThreadId(null);
        }

        mutateFn();
      } catch (error) {
        console.error("Failed to delete thread:", error);
        toast.error("删除失败，请重试");
      } finally {
        setDeletingThreadId(null);
      }
    },
    [currentThreadId, setCurrentThreadId, mutateFn],
  );

  const totalThreads = flattened.length;

  /** 全部删除：后端批量清理本地记录 + LangGraph 线程本体（防复活） */
  const handleDeleteAll = useCallback(async () => {
    setDeletingAll(true);
    try {
      const apiBase = getFastapiUrl();
      const res = await fetch(`${apiBase}/api/v2/threads`, { method: "DELETE" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      toast.success(`已删除 ${data.deleted ?? 0} 条对话`);
      setDeleteAllOpen(false);
      // 当前会话也在删除范围内，回到新对话
      setCurrentThreadId(null);
      mutateFn();
    } catch (error) {
      console.error("Failed to delete all threads:", error);
      toast.error("全部删除失败，请重试");
    } finally {
      setDeletingAll(false);
    }
  }, [setCurrentThreadId, mutateFn]);

  return (
    <div className="absolute inset-0 flex flex-col">
      {/* Header */}
      <div className="flex h-12 flex-shrink-0 items-center justify-between gap-2 border-b px-4">
        <h2 className="text-[13px] font-semibold tracking-wide text-muted-foreground">对话</h2>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setDeleteAllOpen(true)}
          disabled={deletingAll || totalThreads === 0}
          className="h-7 w-7 text-muted-foreground hover:text-destructive"
          aria-label="删除全部对话"
          title="删除全部对话"
        >
          {deletingAll ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Trash2 className="h-3.5 w-3.5" />
          )}
        </Button>
      </div>

      {/* 全部删除确认 */}
      <AlertDialog open={deleteAllOpen} onOpenChange={setDeleteAllOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除全部对话？</AlertDialogTitle>
            <AlertDialogDescription>
              将删除全部 {totalThreads} 条对话及其消息记录，此操作无法撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deletingAll}>取消</AlertDialogCancel>
            <AlertDialogAction
              disabled={deletingAll}
              onClick={(e) => {
                e.preventDefault(); // 保持弹窗开着直到删除完成
                handleDeleteAll();
              }}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deletingAll ? "删除中…" : "全部删除"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <ScrollArea className="h-0 flex-1">
        {threads.error && <ErrorState message={threads.error.message} onRetry={() => threads.mutate()} />}

        {!threads.error && !threads.data && threads.isLoading && (
          <LoadingState />
        )}

        {!threads.error && !threads.isLoading && isEmpty && <EmptyState />}

        {!threads.error && !isEmpty && (
          <div className="box-border w-full max-w-full overflow-hidden p-2">
            {(Object.keys(GROUP_LABELS) as Array<keyof typeof GROUP_LABELS>).map(
              (group) => {
                const groupThreads = grouped[group];
                if (groupThreads.length === 0) return null;

                return (
                  <div key={group} className="mb-3">
                    <h4 className="m-0 px-2.5 pb-1 text-[11px] leading-4 text-muted-foreground/80">
                      {GROUP_LABELS[group]}
                    </h4>
                    <div className="flex flex-col gap-0.5">
                      {groupThreads.map((thread) => {
                        const isActive = currentThreadId === thread.id;
                        const isDeleting = deletingThreadId === thread.id;
                        return (
                          <div
                            key={thread.id}
                            className={cn(
                              "group relative flex h-8 items-center gap-1.5 rounded-lg pl-2.5 pr-1.5 transition-colors duration-150",
                              isActive
                                ? "bg-accent"
                                : "hover:bg-accent",
                            )}
                          >
                            <button
                              type="button"
                              onClick={() => onThreadSelect(thread.id)}
                              className="flex min-w-0 flex-1 items-center gap-2 text-left"
                            >
                              <span
                                className={cn(
                                  "truncate text-[13px] leading-8",
                                  isActive ? "font-medium text-foreground" : "text-foreground/90",
                                )}
                              >
                                {thread.title}
                              </span>
                            </button>
                            {/* Hover swap: timestamp fades out, delete action fades in */}
                            <span
                              className={cn(
                                "flex h-6 w-8 shrink-0 items-center justify-end text-[11px] leading-none text-muted-foreground/80",
                                "transition-opacity duration-100 group-hover:opacity-0",
                                isDeleting && "opacity-0",
                              )}
                            >
                              {formatTime(thread.updatedAt)}
                            </span>
                            <button
                              type="button"
                              onClick={(e) => handleDeleteThread(thread.id, e)}
                              disabled={isDeleting}
                              title="删除对话"
                              className={cn(
                                "absolute right-1 flex h-6 w-8 items-center justify-end rounded-md px-1",
                                "text-muted-foreground opacity-0 transition-opacity duration-100",
                                "hover:text-destructive group-hover:opacity-100",
                                isDeleting && "opacity-100",
                              )}
                            >
                              {isDeleting ? (
                                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              ) : (
                                <Trash2 className="h-3.5 w-3.5" />
                              )}
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              },
            )}

            {!isReachingEnd && (
              <div className="flex justify-center py-3">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => threads.setSize(threads.size + 1)}
                  disabled={isLoadingMore}
                  className="text-xs text-muted-foreground"
                >
                  {isLoadingMore ? (
                    <>
                      <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                      加载中…
                    </>
                  ) : (
                    "加载更多"
                  )}
                </Button>
              </div>
            )}
          </div>
        )}
      </ScrollArea>
    </div>
  );
}
