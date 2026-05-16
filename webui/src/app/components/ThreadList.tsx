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
import { Loader2, MessageSquare, X, Trash2 } from "lucide-react";
import { useQueryState } from "nuqs";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { ThreadItem } from "@/app/hooks/useThreads";
import { useThreads } from "@/app/hooks/useThreads";
import { useClient } from "@/providers/ClientProvider";

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
      <p className="text-sm text-red-600">加载对话列表失败</p>
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
    <div className="space-y-2 p-4">
      {Array.from({ length: 5 }).map((_, i) => (
        <Skeleton key={i} className="h-16 w-full" />
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center p-8 text-center">
      <MessageSquare className="mb-2 h-12 w-12 text-gray-300" />
      <p className="text-sm text-muted-foreground">暂无对话</p>
    </div>
  );
}

interface ThreadListProps {
  onThreadSelect: (id: string) => void;
  onMutateReady?: (mutate: () => void) => void;
  onClose?: () => void;
}

export function ThreadList({
  onThreadSelect,
  onMutateReady,
  onClose,
}: ThreadListProps) {
  const [currentThreadId] = useQueryState("threadId");
  const [, setCurrentThreadId] = useQueryState("threadId");
  const [deletingThreadId, setDeletingThreadId] = useState<string | null>(null);
  const client = useClient();

  const threads = useThreads(client, {
    limit: 20,
  });

  const flattened = useMemo(() => {
    return threads.data?.flat() ?? [];
  }, [threads.data]);

  const isLoadingMore =
    threads.size > 0 && threads.data?.[threads.size - 1] == null;
  const isEmpty = threads.data?.at(0)?.length === 0;
  const isReachingEnd = isEmpty || (threads.data?.at(-1)?.length ?? 0) < 20;

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
    // Only run once on mount to avoid infinite loops
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
        await client.threads.delete(threadId);

        if (currentThreadId === threadId) {
          setCurrentThreadId(null);
        }

        mutateFn();
      } catch (error) {
        console.error("Failed to delete thread:", error);
        alert("删除失败，请重试。");
      } finally {
        setDeletingThreadId(null);
      }
    },
    [client, currentThreadId, setCurrentThreadId, mutateFn],
  );

  return (
    <div className="absolute inset-0 flex flex-col">
      {/* Header */}
      <div className="flex flex-shrink-0 items-center justify-between gap-3 border-b border-border p-4">
        <h2 className="text-lg font-semibold tracking-tight">对话列表</h2>
        <div className="flex items-center gap-2">
          {onClose && (
            <Button
              variant="ghost"
              size="icon"
              onClick={onClose}
              className="h-8 w-8"
              aria-label="关闭对话列表侧边栏"
            >
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>

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
                  <div key={group} className="mb-4">
                    <h4 className="m-0 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      {GROUP_LABELS[group]}
                    </h4>
                    <div className="flex flex-col gap-1">
                      {groupThreads.map((thread) => (
                        <div key={thread.id} className="group relative">
                          <button
                            type="button"
                            onClick={(e) => handleDeleteThread(thread.id, e)}
                            disabled={deletingThreadId === thread.id}
                            className={cn(
                              "absolute left-0 bottom-3 z-10 flex-shrink-0 rounded p-0.5 text-muted-foreground opacity-0 transition-opacity hover:bg-destructive hover:text-destructive-foreground group-hover:opacity-100",
                              deletingThreadId === thread.id && "opacity-100",
                            )}
                            title="删除对话"
                          >
                            {deletingThreadId === thread.id ? (
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            ) : (
                              <Trash2 className="h-3.5 w-3.5" />
                            )}
                          </button>

                          <button
                            type="button"
                            onClick={() => onThreadSelect(thread.id)}
                            className={cn(
                              "grid w-full cursor-pointer items-center gap-3 rounded-lg px-3 py-3 text-left transition-colors duration-200",
                              "hover:bg-accent",
                              currentThreadId === thread.id
                                ? "border border-primary bg-accent hover:bg-accent"
                                : "border border-transparent bg-transparent",
                            )}
                            aria-current={currentThreadId === thread.id}
                          >
                            <div className="min-w-0 flex-1">
                              <div className="mb-1 flex items-center justify-between">
                                <h3 className="truncate text-sm font-semibold">
                                  {thread.title}
                                </h3>
                                <span className="ml-2 flex-shrink-0 text-xs text-muted-foreground">
                                  {formatTime(thread.updatedAt)}
                                </span>
                              </div>
                              <p className="flex-1 truncate text-sm text-muted-foreground">
                                {thread.description}
                              </p>
                            </div>
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              },
            )}

            {!isReachingEnd && (
              <div className="flex justify-center py-4">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => threads.setSize(threads.size + 1)}
                  disabled={isLoadingMore}
                >
                  {isLoadingMore ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      加载中...
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
