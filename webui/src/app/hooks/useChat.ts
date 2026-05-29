"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Message } from "@langchain/langgraph-sdk";
import { v4 as uuidv4 } from "uuid";
import { useClient } from "@/providers/ClientProvider";
import { useQueryState } from "nuqs";
import { revalidateTestCases } from "@/lib/api/useTestCases";
import { revalidateProjects } from "@/lib/api/useProjects";
import { usePaginatedMessages } from "@/lib/api/messages";
import type { ContentBlock, TodoItem } from "@/app/types/types";
import { getConfig } from "@/lib/config";

/** How many stream events between incremental saves to SQLite. */
const INCREMENTAL_SAVE_INTERVAL = 15;
/** Minimum milliseconds between incremental saves. */
const INCREMENTAL_SAVE_MIN_INTERVAL_MS = 2000;

/**
 * Chat hook with per-thread background streaming.
 *
 * Architecture:
 * - Each thread's stream runs independently in the background
 * - Switching threads does NOT abort the old stream
 * - Stream messages are stored per-thread in a Map (ref)
 * - Messages are incrementally persisted to SQLite during streaming
 * - Merged messages show the current thread's streaming + paginated data
 * - When a stream completes, final messages are saved to local SQLite
 *   and SWR cache is invalidated
 *
 * Data flow for surviving page refresh:
 * 1. During streaming: messages accumulate in streamDataRef AND are
 *    periodically saved to SQLite (incremental persistence).
 * 2. On page refresh: streamDataRef is lost, but paginated API fetches
 *    from SQLite which has the incrementally saved messages.
 * 3. After refresh: the paginated messages show whatever was saved so far.
 *    If the LangGraph run is still going, the thread state will eventually
 *    have the full response, and the next page visit will show it via
 *    LangGraph fallback or a subsequent save.
 */

/** Sync an incomplete thread from LangGraph: checks if last local msg is human, backfills if so. */
async function _syncIncompleteThread(
  threadId: string,
  paginated: { messages: any[]; mutate: () => void },
  scheduleRevalidate: () => void,
) {
  const msgs = paginated.messages;
  if (!msgs.length) return;
  const last = msgs[msgs.length - 1];
  // Only sync if the conversation appears incomplete (last message is human, no AI response)
  if (last?.type !== "human") return;

  try {
    const config = getConfig();
    const apiBase = config?.fastapiUrl || "http://localhost:8000";
    const res = await fetch(`${apiBase}/api/v2/threads/${threadId}/messages/sync`, {
      method: "POST",
    });
    if (!res.ok) return;
    const data = await res.json();
    if (data.synced > 0) {
      console.log("[useChat] Synced %d messages from LangGraph", data.synced);
      paginated.mutate();
      scheduleRevalidate();
    }
  } catch {
    // Non-critical: local data is still shown
  }
}

export function useChat({
  assistantId,
  workspaceId = "default",
  onHistoryRevalidate,
}: {
  assistantId: string;
  workspaceId?: string;
  onHistoryRevalidate?: () => void;
}) {
  const [threadId, setThreadId] = useQueryState("threadId");
  const client = useClient();

  // Per-thread streaming state
  // Ref holds the actual data (synchronous access in finally), state triggers re-renders
  const streamDataRef = useRef<Map<string, Message[]>>(new Map());
  const [streamVersion, setStreamVersion] = useState(0);
  const loadingThreadsRef = useRef<Map<string, boolean>>(new Map());
  const [loadingVersion, setLoadingVersion] = useState(0);
  const abortMapRef = useRef<Map<string, AbortController>>(new Map());

  // Track threads whose stream completed but SWR hasn't confirmed refresh yet.
  // This prevents a gap where neither ref nor paginated data has messages.
  const completedButUnconfirmedRef = useRef<Set<string>>(new Set());

  // Paginated message loading (always active for existing threads)
  const paginated = usePaginatedMessages(threadId);

  const revalidateHistoryRef = useRef(onHistoryRevalidate);
  useEffect(() => {
    revalidateHistoryRef.current = onHistoryRevalidate;
  }, [onHistoryRevalidate]);

  const revalidateManagementCache = useCallback(() => {
    revalidateTestCases();
    revalidateProjects();
  }, []);

  const scheduleHistoryRevalidate = useCallback(() => {
    if (typeof window === "undefined") {
      revalidateHistoryRef.current?.();
      revalidateManagementCache();
      return;
    }
    window.setTimeout(() => {
      revalidateHistoryRef.current?.();
      revalidateManagementCache();
    }, 0);
  }, [revalidateManagementCache]);

  // When switching to a thread, if that thread's stream completed in the
  // background, the ref data was already deleted but SWR might have stale
  // data. Force a revalidation when the threadId changes.
  const prevThreadIdRef = useRef<string | null>(threadId);
  useEffect(() => {
    if (threadId !== prevThreadIdRef.current) {
      const oldThreadId = prevThreadIdRef.current;
      prevThreadIdRef.current = threadId;
      // Clean up streaming data for the old thread (no longer viewing it)
      if (oldThreadId) {
        streamDataRef.current.delete(oldThreadId);
      }
      if (threadId) {
        paginated.mutate();
        completedButUnconfirmedRef.current.delete(threadId);
      }
    }
  }, [threadId, paginated]);

  // Get streaming messages and loading state for the currently viewed thread
  const activeStreamMessages = streamDataRef.current.get(threadId ?? "") ?? [];
  const isCurrentThreadLoading = loadingThreadsRef.current.get(threadId ?? "") ?? false;

  // Dual-source merge: paginated history + streaming messages for current thread
  const mergedMessages = useMemo(() => {
    void streamVersion;
    void loadingVersion;

    if (activeStreamMessages.length === 0) {
      return paginated.messages as unknown as Message[];
    }

    const orderedIds: string[] = [];
    const merged = new Map<string, Message>();

    for (const msg of paginated.messages) {
      if (msg.id) {
        merged.set(msg.id, msg as unknown as Message);
        orderedIds.push(msg.id);
      }
    }

    for (const msg of activeStreamMessages) {
      if (!msg.id) continue;
      if (merged.has(msg.id)) {
        merged.set(msg.id, msg);
      } else {
        merged.set(msg.id, msg);
        orderedIds.push(msg.id);
      }
    }

    return orderedIds.map((id) => merged.get(id)!).filter(Boolean);
  }, [paginated.messages, activeStreamMessages, streamVersion, loadingVersion]);

  const saveMessagesToLocalStore = useCallback(
    async (tid: string, msgs: Message[]) => {
      if (!tid || msgs.length === 0) return;
      try {
        const config = getConfig();
        const apiBase = config?.fastapiUrl || "http://localhost:8000";
        const payload = {
          messages: msgs
            .filter((m) => m.id && m.type)
            .map((m) => ({
              id: m.id,
              type: m.type,
              content: m.content,
              additional_kwargs: (m as any).additional_kwargs ?? null,
              tool_calls: (m as any).tool_calls ?? null,
              name: (m as any).name ?? null,
            })),
        };
        await fetch(`${apiBase}/api/v2/threads/${tid}/messages/save`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      } catch (err) {
        console.warn("[useChat] Failed to save messages to local store:", err);
      }
    },
    [],
  );

  // === Reconnection logic: detect and reconnect to active runs after page refresh ===
  // When threadId changes (or on mount), check if the thread has an active run
  // and reconnect to it via runs.joinStream(). This handles the case where the
  // user refreshes the page while AI is streaming.
  const reconnectAbortRef = useRef<AbortController | null>(null);
  const reconnectDepsRef = useRef({ saveMessagesToLocalStore, scheduleHistoryRevalidate, paginated, client });
  reconnectDepsRef.current = { saveMessagesToLocalStore, scheduleHistoryRevalidate, paginated, client };

  useEffect(() => {
    if (!threadId || !assistantId) return;

    if (reconnectAbortRef.current) {
      reconnectAbortRef.current.abort();
    }

    const abortController = new AbortController();
    reconnectAbortRef.current = abortController;
    const { saveMessagesToLocalStore: saveMsgs, scheduleHistoryRevalidate: scheduleRevalidate, paginated: pag, client: cli } = reconnectDepsRef.current;

    const attemptReconnect = async () => {
      try {
        if (abortMapRef.current.has(threadId)) return;

        // Check if thread exists in LangGraph (may not after inmem restart)
        try {
          await cli.threads.get(threadId);
        } catch {
          // Thread not in LangGraph — skip reconnect, messages are in SQLite
          return;
        }

        // List all runs and filter client-side (server-side status filter is unreliable)
        const runs = await cli.runs.list(threadId, { limit: 10 });

        const activeRun = (Array.isArray(runs) ? runs : []).find(
          (r: any) => r.status === "running" || r.status === "pending"
        );

        if (!activeRun || abortController.signal.aborted) {
          // No active run — check if conversation is incomplete and sync from LangGraph
          const completedRun = (Array.isArray(runs) ? runs : []).find(
            (r: any) => r.status === "success"
          );
          if (completedRun && !abortController.signal.aborted) {
            await _syncIncompleteThread(threadId, pag, scheduleRevalidate);
          }
          return;
        }

        console.log("[useChat] Reconnect: joining run %s (status=%s)", activeRun.run_id?.substring(0, 8), activeRun.status);

        // Step 2: Found an active run - reconnect to its stream
        // Mark this thread as loading
        loadingThreadsRef.current.set(threadId, true);
        setLoadingVersion((v) => v + 1);

        // Incremental save state
        let eventCount = 0;
        let lastSaveTime = 0;

        try {
          const stream = cli.runs.joinStream(threadId, activeRun.run_id, {
            streamMode: "messages",
            signal: abortController.signal,
          });

          for await (const event of stream) {
            if (abortController.signal.aborted) break;

            const eventType = event.event;
            const eventData = event.data;
            if (!eventData) continue;

            try {
              if (
                (eventType === "messages/partial" ||
                  eventType === "messages/complete") &&
                Array.isArray(eventData)
              ) {
                for (const msg of eventData) {
                  if (msg && msg.id && msg.type) {
                    const current = streamDataRef.current.get(threadId) ?? [];
                    const existing = new Map(current.map((m) => [m.id, m]));
                    existing.set(msg.id, msg as Message);
                    streamDataRef.current.set(threadId, Array.from(existing.values()));
                    setStreamVersion((v) => v + 1);

                    eventCount++;
                    const now = Date.now();
                    if (
                      eventCount >= INCREMENTAL_SAVE_INTERVAL &&
                      now - lastSaveTime >= INCREMENTAL_SAVE_MIN_INTERVAL_MS
                    ) {
                      eventCount = 0;
                      lastSaveTime = now;
                      const currentMsgs = streamDataRef.current.get(threadId) ?? [];
                      saveMsgs(threadId, currentMsgs).catch(() => {});
                    }
                  }
                }
              } else if (eventType === "error" && eventData) {
                console.error("[useChat] Reconnect stream error event:", eventData);
              }
            } catch {
              // Skip malformed events
            }
          }
        } finally {
          loadingThreadsRef.current.set(threadId, false);
          setLoadingVersion((v) => v + 1);

          const finalMsgs = streamDataRef.current.get(threadId) ?? [];
          if (finalMsgs.length > 0) {
            await saveMsgs(threadId, finalMsgs);
          }

          // Trigger SWR revalidation (non-blocking)
          try {
            const { mutate: swrMutate } = await import("swr");
            swrMutate(
              (key: unknown) =>
                typeof key === "string" && key.includes(`/threads/${threadId}/messages`),
            );
          } catch {
            pag.mutate();
          }

          completedButUnconfirmedRef.current.delete(threadId);
          scheduleRevalidate();
        }
      } catch (err: unknown) {
        if (err instanceof Error && err.name === "AbortError") {
          // Aborted, not an error
        } else {
          console.warn("[useChat] Reconnection attempt ended:", err instanceof Error ? err.message : err);
        }
      }
    };

    attemptReconnect();

    return () => {
      abortController.abort();
    };
  }, [threadId, assistantId]);

  /**
   * Send a message using LangGraph Client runs.stream() directly.
   * The stream runs in the background and is keyed by thread ID,
   * so switching to a different thread won't interrupt it.
   *
   * Incremental persistence: messages are saved to SQLite periodically
   * during streaming (every INCREMENTAL_SAVE_INTERVAL events, with a
   * minimum time gap of INCREMENTAL_SAVE_MIN_INTERVAL_MS). This ensures
   * that even if the user refreshes mid-stream, partial messages survive.
   */
  const sendMessage = useCallback(
    async (content: string, contentBlocks?: ContentBlock[], context?: { repoPath?: string; taskId?: string }) => {
      const imageBlocks =
        contentBlocks?.filter((b) => b.type === "image") ?? [];
      const fileBlocks =
        contentBlocks?.filter((b) => b.type !== "image") ?? [];

      const imageUrlBlocks = imageBlocks.map((b) => ({
        type: "image_url" as const,
        image_url: {
          url: `data:${b.mimeType};base64,${b.data}`,
        },
      }));

      const fileTextParts: string[] = [];
      for (const fb of fileBlocks) {
        const filename = fb.metadata?.filename || fb.metadata?.name || "document";
        const extractedText = fb.metadata?.extractedText;

        if (extractedText) {
          fileTextParts.push(`### File: ${filename}\n\n${extractedText}`);
        } else {
          fileTextParts.push(`### File: ${filename}\n\n[Text extraction failed or unavailable.]`);
        }
      }

      const fileText = fileTextParts.length > 0
        ? `\n\n[Uploaded ${fileTextParts.length} file(s)]\n\n${fileTextParts.join("\n\n---\n\n")}`
        : "";

      const hasBlocks = imageUrlBlocks.length > 0 || fileText.length > 0;
      const messageContent =
        hasBlocks
          ? ([
              ...(content.trim().length > 0
                ? [{ type: "text" as const, text: content + fileText }]
                : [{ type: "text" as const, text: fileText.trim() }]),
              ...imageUrlBlocks,
            ] as Message["content"])
          : content;

      const newMessage: Message = {
        id: uuidv4(),
        type: "human",
        content: messageContent,
      };

      // Abort any existing stream on the SAME thread only
      let currentThreadId = threadId;
      if (currentThreadId) {
        const oldAbort = abortMapRef.current.get(currentThreadId);
        if (oldAbort) oldAbort.abort();
      }

      const abortController = new AbortController();

      // Mark this thread as loading
      loadingThreadsRef.current.set(currentThreadId ?? "", true);
      setLoadingVersion((v) => v + 1);

      // Add user message to this thread's stream data
      const tid = currentThreadId ?? "";
      const prev = streamDataRef.current.get(tid) ?? [];
      streamDataRef.current.set(tid, [...prev, newMessage]);
      setStreamVersion((v) => v + 1);

      // Incremental save state (local variables for this invocation)
      let eventCount = 0;
      let lastSaveTime = 0;
      let lastSavedMsgIds: Set<string> = new Set();

      try {
        // Get or create thread
        if (!currentThreadId) {
          const newThread = await client.threads.create();
          currentThreadId = newThread.thread_id;
          setThreadId(currentThreadId);

          // Persist thread metadata to FastAPI (survives LangGraph restart)
          const config = getConfig();
          const apiBase = config?.fastapiUrl || "http://localhost:8000";
          const displayTitle = typeof content === "string"
            ? content.slice(0, 50) + (content.length > 50 ? "..." : "")
            : "新对话";
          fetch(`${apiBase}/api/v2/threads`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ thread_id: currentThreadId, title: displayTitle }),
          }).catch(() => {});

          // Migrate data from empty key to real thread ID
          const pending = streamDataRef.current.get("") ?? [];
          streamDataRef.current.delete("");
          streamDataRef.current.set(currentThreadId, pending);
          abortMapRef.current.delete("");
          abortMapRef.current.set(currentThreadId, abortController);
          loadingThreadsRef.current.delete("");
          loadingThreadsRef.current.set(currentThreadId, true);
        } else {
          abortMapRef.current.set(currentThreadId, abortController);
          // Ensure thread exists in LangGraph (may have been lost after inmem restart)
          try {
            await client.threads.get(currentThreadId);
          } catch {
            // Thread lost from LangGraph — recreate it
            const recreated = await client.threads.create();
            // If the new thread has a different ID, we need to update
            // But LangGraph allows creating with specific metadata, so just use the same ID approach
            // Actually we can't force a thread_id with LangGraph SDK, so update our tracking
            if (recreated.thread_id !== currentThreadId) {
              // Migrate data to new thread ID
              const pending = streamDataRef.current.get(currentThreadId) ?? [];
              streamDataRef.current.delete(currentThreadId);
              streamDataRef.current.set(recreated.thread_id, pending);
              abortMapRef.current.delete(currentThreadId);
              abortMapRef.current.set(recreated.thread_id, abortController);
              loadingThreadsRef.current.delete(currentThreadId);
              loadingThreadsRef.current.set(recreated.thread_id, true);
              currentThreadId = recreated.thread_id;
              setThreadId(currentThreadId);

              // Update ThreadInfo in FastAPI to point to new thread
              const config = getConfig();
              const apiBase = config?.fastapiUrl || "http://localhost:8000";
              const displayTitle = typeof content === "string"
                ? content.slice(0, 50) + (content.length > 50 ? "..." : "")
                : "新对话";
              fetch(`${apiBase}/api/v2/threads`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ thread_id: currentThreadId, title: displayTitle }),
              }).catch(() => {});
            }
          }
        }

        const streamingThreadId = currentThreadId;

        // Immediately persist the user message to SQLite so it survives page refresh
        // even if no incremental save triggers before the user refreshes.
        saveMessagesToLocalStore(streamingThreadId, [newMessage]).catch(() => {});

        const stream = client.runs.stream(
          streamingThreadId,
          assistantId,
          {
            input: { messages: [newMessage] },
            config: {
              recursion_limit: 1000,
              configurable: {
                space_id: workspaceId || "default",
                repo_path: context?.repoPath || "",
                task_id: context?.taskId || "",
              },
            },
            streamMode: "messages",
          },
        );

        // Process SSE events - updates streamDataRef for this specific thread
        for await (const event of stream) {
          if (abortController.signal.aborted) break;

          const eventType = event.event;
          const eventData = event.data;
          if (!eventData) continue;

          try {
            if (
              (eventType === "messages/partial" ||
                eventType === "messages/complete") &&
              Array.isArray(eventData)
            ) {
              for (const msg of eventData) {
                if (msg && msg.id && msg.type) {
                  const current = streamDataRef.current.get(streamingThreadId) ?? [];
                  const existing = new Map(current.map((m) => [m.id, m]));
                  existing.set(msg.id, msg as Message);
                  streamDataRef.current.set(streamingThreadId, Array.from(existing.values()));
                  setStreamVersion((v) => v + 1);

                  // Incremental persistence: save to SQLite periodically
                  eventCount++;
                  const now = Date.now();
                  if (
                    eventCount >= INCREMENTAL_SAVE_INTERVAL &&
                    now - lastSaveTime >= INCREMENTAL_SAVE_MIN_INTERVAL_MS
                  ) {
                    eventCount = 0;
                    lastSaveTime = now;
                    const currentMsgs = streamDataRef.current.get(streamingThreadId) ?? [];
                    lastSavedMsgIds = new Set(currentMsgs.map((m) => m.id).filter((id): id is string => !!id));
                    // Fire-and-forget incremental save (don't block the stream)
                    saveMessagesToLocalStore(streamingThreadId, currentMsgs).catch(() => {});
                  }
                }
              }
            } else if (eventType === "metadata" && eventData) {
              const meta = eventData as { run_id?: string; thread_id?: string };
              if (meta.thread_id) {
                setThreadId(meta.thread_id);
              }
            } else if (eventType === "error" && eventData) {
              console.error("[useChat] Stream error event:", eventData);
            }
          } catch {
            // Skip malformed events
          }
        }
      } catch (err: unknown) {
        if (err instanceof Error && err.name === "AbortError") {
          // User aborted, not an error
        } else {
          console.error("[useChat] Stream error:", err);
        }
      } finally {
        const finalThreadId = currentThreadId;

        // Clear loading and abort for this thread
        loadingThreadsRef.current.set(finalThreadId ?? "", false);
        setLoadingVersion((v) => v + 1);
        abortMapRef.current.delete(finalThreadId ?? "");

        // Save completed messages to local store (await to ensure SQLite has data)
        const finalMsgs = streamDataRef.current.get(finalThreadId ?? "") ?? [];
        if (finalThreadId && finalMsgs.length > 0) {
          await saveMessagesToLocalStore(finalThreadId, finalMsgs);
        }

        // Trigger SWR revalidation (paginated data will refresh in background)
        try {
          const { mutate: swrMutate } = await import("swr");
          swrMutate(
            (key: unknown) =>
              typeof key === "string" && key.includes(`/threads/${finalThreadId}/messages`),
          );
        } catch {
          if (threadId === finalThreadId) {
            paginated.mutate();
          }
        }

        completedButUnconfirmedRef.current.delete(finalThreadId ?? "");

        // Refresh thread list and management data
        scheduleHistoryRevalidate();
      }

      onHistoryRevalidate?.();
    },
    [threadId, assistantId, client, workspaceId, setThreadId, scheduleHistoryRevalidate, onHistoryRevalidate, paginated, saveMessagesToLocalStore],
  );

  const stopStream = useCallback(() => {
    const tid = threadId ?? "";
    const abort = abortMapRef.current.get(tid);
    if (abort) {
      abort.abort();
      abortMapRef.current.delete(tid);
    }
    loadingThreadsRef.current.set(tid, false);
    setLoadingVersion((v) => v + 1);
  }, [threadId]);

  return {
    stream: null,
    messages: mergedMessages,
    isLoading: isCurrentThreadLoading,
    sendMessage,
    stopStream,
    resumeInterrupt: async () => {},
    todos: [] as TodoItem[],
    files: {} as Record<string, unknown>,
    ui: undefined as unknown[] | undefined,
    interrupt: undefined,
    threadId,
    setThreadId,
    streamLoadFailed: !!paginated.error,
    historyError: paginated.error ? String(paginated.error) : null,
    isLoadingHistory: paginated.isLoading || paginated.isValidating,
    hasOlderMessages: paginated.hasMore,
    loadOlderMessages: paginated.loadMore,
  };
}
