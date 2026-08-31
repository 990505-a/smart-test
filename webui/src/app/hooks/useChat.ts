"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Message } from "@langchain/langgraph-sdk";
import { v4 as uuidv4 } from "uuid";
import { useClient } from "@/providers/ClientProvider";
import { useQueryState, parseAsString } from "nuqs";
import { revalidateCaseDocs } from "@/lib/api/useCaseDocs";
import { usePaginatedMessages } from "@/lib/api/messages";
import type { ContentBlock, TodoItem } from "@/app/types/types";
import { getFastapiUrl, getDeploymentUrl } from "@/lib/config";
import { toast } from "sonner";
import { SubAgentActivityStore, type SubAgentEvent } from "@/app/hooks/subagentActivity";
import {
  loadCancelledRuns,
  persistCancelledRuns,
  pickActiveRun,
  pruneTombstones,
  shouldCancelAbortedRun,
} from "@/app/hooks/cancellation";

/** Extract a readable message from a LangGraph stream error event payload. */
function streamErrorMessage(data: unknown): string {
  if (data && typeof data === "object") {
    const d = data as Record<string, unknown>;
    const err = d.error ?? d.message;
    if (typeof err === "string" && err) return err;
    if (err && typeof err === "object") {
      const m = (err as Record<string, unknown>).message;
      if (typeof m === "string" && m) return m;
    }
  }
  try {
    return JSON.stringify(data);
  } catch {
    return "未知错误";
  }
}

/** How many stream events between incremental saves to SQLite. */
const INCREMENTAL_SAVE_INTERVAL = 30;
/** Minimum milliseconds between incremental saves. */
const INCREMENTAL_SAVE_MIN_INTERVAL_MS = 5000;
/** Coalesce window for stream-driven re-renders (committed-chunk semantics). */
const STREAM_RENDER_FLUSH_MS = 50;
/**
 * How many trailing messages are re-sent on every incremental save: the tail
 * is still streaming (messages/partial replaces content in place), so those
 * ids must be re-upserted even if they were saved before.
 */
const INCREMENTAL_SAVE_TAIL = 3;

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
  paginated: { messages: { type?: string }[]; mutate: () => void },
  scheduleRevalidate: () => void,
) {
  const msgs = paginated.messages;
  if (!msgs.length) return;
  const last = msgs[msgs.length - 1];
  // Only sync if the conversation appears incomplete (last message is human, no AI response)
  if (last?.type !== "human") return;

  try {
    const apiBase = getFastapiUrl();
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

/**
 * Pending human-approval request (execute 工具越权命令时 agent 暂停).
 * command comes from the real tool call args in the interrupt payload —
 * never from model-authored prose (dsh anti-spoofing principle).
 */
export interface PendingApproval {
  threadId: string;
  toolName: string;
  command: string;
  description: string;
  args: Record<string, unknown>;
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
  // Per-conversation reasoning effort ("low"|"medium"|"high"|""=off),
  // forwarded to the agent through configurable.llm_reasoning_effort.
  // Default must match ChatInterface's selector default ("high").
  const [reasoningEffort] = useQueryState("effort", parseAsString.withDefault("high"));
  // Per-conversation permission mode: workspace_write (default) / full_access
  // — forwarded as configurable.permission_mode to the agent's permission
  // gate. read_only 已移除；旧值由后端回落 workspace_write。
  const [permissionMode] = useQueryState(
    "permission",
    parseAsString.withDefault("workspace_write"),
  );
  const client = useClient();

  // Pending execute-approval interrupt (dsh-style): the agent paused on a
  // non-whitelisted shell command and waits for 允许一次/拒绝.
  const [interrupt, setInterrupt] = useState<PendingApproval | null>(null);

  // 线程懒创建（dsh：会话可见性由内容决定）。点「新对话」只清空 threadId，
  // 不再预建空壳会话；线程在首条消息发送（sendMessage）或首条消息前的
  // 文件上传（ensureThreadId）时才真正创建。会话列表条目则由后端在首次
  // 保存消息时自动注册并从首条 human 消息推导标题（_upsert_thread_info）。

  // Per-thread streaming state
  // Ref holds the actual data (synchronous access in finally), state triggers re-renders
  const streamDataRef = useRef<Map<string, Message[]>>(new Map());
  const [streamVersion, setStreamVersion] = useState(0);
  const loadingThreadsRef = useRef<Map<string, boolean>>(new Map());
  const [loadingVersion, setLoadingVersion] = useState(0);

  // Sub-agent live activity (streamSubgraphs): routed out of the main message
  // flow by checkpoint namespace; feeds the right-side activity drawer.
  const subagentStoreRef = useRef<SubAgentActivityStore>(new SubAgentActivityStore());
  const [subagentVersion, setSubagentVersion] = useState(0);
  const subagentRenderTimerRef = useRef<number | null>(null);
  const bumpSubagentVersion = useCallback(() => {
    if (subagentRenderTimerRef.current !== null) return;
    subagentRenderTimerRef.current = window.setTimeout(() => {
      subagentRenderTimerRef.current = null;
      setSubagentVersion(subagentStoreRef.current.version);
    }, 120);
  }, []);
  useEffect(() => {
    subagentStoreRef.current = new SubAgentActivityStore();
    return () => {
      if (subagentRenderTimerRef.current !== null) {
        window.clearTimeout(subagentRenderTimerRef.current);
      }
    };
  }, [assistantId]);
  const abortMapRef = useRef<Map<string, AbortController>>(new Map());
  // 用户取消的 run 墓碑（threadId → run_id 集合），重连逻辑据此过滤
  // 「已取消但服务端状态未收敛」的 run；条目随 run 离开活跃列表被清理
  const cancelledRunsRef = useRef<Map<string, Set<string>> | null>(null);
  if (cancelledRunsRef.current === null) {
    cancelledRunsRef.current = loadCancelledRuns();
  }

  // Render gating: only the currently viewed thread's events re-render the
  // chat UI. Background streams keep mutating their ref data silently, and
  // view switches flush immediately. Flushes are coalesced within
  // STREAM_RENDER_FLUSH_MS so token bursts produce one render per tick.
  const viewedThreadIdRef = useRef(threadId);
  viewedThreadIdRef.current = threadId;
  const renderTimerRef = useRef<number | null>(null);
  // null threadId (chat not yet created) is normalized to "" so the pending
  // pre-thread data bucket (key "") still renders.
  const isViewedThread = useCallback(
    (tid: string) => tid === (viewedThreadIdRef.current ?? ""),
    [],
  );
  const scheduleStreamRender = useCallback(
    (tid: string) => {
      if (!isViewedThread(tid)) return;
      if (renderTimerRef.current !== null) return;
      renderTimerRef.current = window.setTimeout(() => {
        renderTimerRef.current = null;
        setStreamVersion((v) => v + 1);
      }, STREAM_RENDER_FLUSH_MS);
    },
    [isViewedThread],
  );
  const flushStreamRender = useCallback(
    (tid: string) => {
      if (!isViewedThread(tid)) return;
      if (renderTimerRef.current !== null) {
        window.clearTimeout(renderTimerRef.current);
        renderTimerRef.current = null;
      }
      setStreamVersion((v) => v + 1);
    },
    [isViewedThread],
  );
  const bumpLoadingIfViewed = useCallback(
    (tid: string) => {
      if (!isViewedThread(tid)) return;
      setLoadingVersion((v) => v + 1);
    },
    [isViewedThread],
  );

  // In-place upsert keyed by message id — the previous implementation rebuilt
  // a Map of the whole thread per chunk (O(N) per token, O(N²) per stream).
  const upsertStreamMessage = useCallback((tid: string, msg: Message) => {
    const arr = streamDataRef.current.get(tid);
    if (!arr) {
      streamDataRef.current.set(tid, [msg]);
      return;
    }
    const idx = arr.findIndex((m) => m.id === msg.id);
    if (idx === -1) arr.push(msg);
    else arr[idx] = msg;
  }, []);

  // Track threads whose stream completed but SWR hasn't confirmed refresh yet.
  // This prevents a gap where neither ref nor paginated data has messages.
  const completedButUnconfirmedRef = useRef<Set<string>>(new Set());

  // Paginated message loading (always active for existing threads)
  const paginated = usePaginatedMessages(threadId);

  // Always-fresh handle for async flows: useSWRInfinite's bound mutate
  // early-returns when captured with a falsy infiniteKey (no thread yet).
  // A first message sent from 新对话 (threadId=null) used to finalize with
  // that stale mutate — a silent no-op, so the reply vanished after the
  // stream ended until a refresh refetched the key.
  const paginatedRef = useRef(paginated);
  paginatedRef.current = paginated;

  const revalidateHistoryRef = useRef(onHistoryRevalidate);
  useEffect(() => {
    revalidateHistoryRef.current = onHistoryRevalidate;
  }, [onHistoryRevalidate]);

  const revalidateManagementCache = useCallback(() => {
    revalidateCaseDocs();
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

  // When switching threads: keep the old thread's stream data (background
  // streams keep updating it and switching back should resume seamlessly —
  // entries are dropped in the run's finally once the paginated store has
  // been revalidated). No forced mutate: SWR revalidates the key on mount
  // and keepPreviousData keeps the DOM alive across the switch.
  const prevThreadIdRef = useRef<string | null>(threadId);
  // Latest viewed thread id: stream completion runs in a closure and must
  // compare against the CURRENT thread, not the one captured at send time.
  const threadIdRef = useRef<string | null>(threadId);
  threadIdRef.current = threadId;

  // 懒创建的并发防护：批量拖文件/快速连续操作时不重复建线程
  const ensuredThreadIdRef = useRef<string | null>(null);
  const ensureThreadIdPromiseRef = useRef<Promise<string | undefined> | null>(null);

  /**
   * 按需创建线程并返回其 id（懒创建）。供首条消息前的操作使用——目前唯一
   * 的调用方是文件上传（PDF/MD 要落到 /uploads/{threadId}/ 工作区）。
   * 只建 LangGraph thread，不注册会话列表：列表可见性由内容决定，首次
   * 保存消息时后端 _upsert_thread_info 自动建行并推导标题。
   */
  const ensureThreadId = useCallback(async (): Promise<string | undefined> => {
    if (threadIdRef.current) return threadIdRef.current;
    if (ensuredThreadIdRef.current) return ensuredThreadIdRef.current;
    if (!ensureThreadIdPromiseRef.current) {
      ensureThreadIdPromiseRef.current = (async () => {
        try {
          const newThread = await client.threads.create();
          ensuredThreadIdRef.current = newThread.thread_id;
          setThreadId(newThread.thread_id);
          return newThread.thread_id;
        } catch {
          return undefined;
        } finally {
          ensureThreadIdPromiseRef.current = null;
        }
      })();
    }
    return ensureThreadIdPromiseRef.current;
  }, [client, setThreadId]);
  useEffect(() => {
    if (threadId !== prevThreadIdRef.current) {
      prevThreadIdRef.current = threadId;
      if (threadId) {
        completedButUnconfirmedRef.current.delete(threadId);
      }
      // Paint the newly viewed thread immediately (its live stream included)
      flushStreamRender(threadId ?? "");
    }
  }, [threadId, flushStreamRender]);

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

  // Ids already persisted per thread — incremental saves post only the delta
  // instead of serializing the whole conversation every few seconds.
  const savedMsgIdsRef = useRef<Map<string, Set<string>>>(new Map());

  // Attachment metadata is kept separately from streamed messages. LangGraph may
  // re-emit the human message without additional_kwargs, and the final snapshot
  // must not overwrite the persisted attachment metadata with an empty value.
  const attachmentMetadataRef = useRef<
    Map<string, Map<string, Array<Record<string, unknown>>>>
  >(new Map());

  // Per-thread save queue: immediate, incremental, and final snapshots must
  // commit in invocation order, otherwise an older partial can overwrite the
  // final response after a refresh.
  const saveQueueRef = useRef<Map<string, Promise<void>>>(new Map());

  const saveMessagesToLocalStore = useCallback(
    async (tid: string, msgs: Message[], opts?: { final?: boolean }) => {
      if (!tid || msgs.length === 0) return;
      const previous = saveQueueRef.current.get(tid) ?? Promise.resolve();
      const current = previous.catch(() => {}).then(async () => {
        try {
          const apiBase = getFastapiUrl();
          const valid = msgs.filter((m) => m.id && m.type);

          let toSend = valid;
          if (!opts?.final) {
            const saved = savedMsgIdsRef.current.get(tid) ?? new Set<string>();
            const tailStart = Math.max(0, valid.length - INCREMENTAL_SAVE_TAIL);
            toSend = valid.filter(
              (m, i) => i >= tailStart || !saved.has(m.id as string),
            );
            if (toSend.length === 0) return;
          }

          const payload = {
            messages: toSend.map((m) => {
              const attachmentMetadataByMessage = attachmentMetadataRef.current.get(tid);
              const existingAdditional =
                (m as Message & { additional_kwargs?: Record<string, unknown> }).additional_kwargs ?? {};
              const attachments = attachmentMetadataByMessage?.get(m.id as string) ??
                existingAdditional.attachments;
              const hasAttachments = Array.isArray(attachments) && attachments.length > 0;
              return {
                id: m.id,
                type: m.type,
                content: m.content,
                additional_kwargs: hasAttachments
                  ? { ...existingAdditional, attachments }
                  : Object.keys(existingAdditional).length > 0
                    ? existingAdditional
                    : null,
                tool_calls:
                  (m as Message & { tool_calls?: unknown }).tool_calls ?? null,
                name: (m as Message & { name?: string }).name ?? null,
                tool_call_id:
                  (m as Message & { tool_call_id?: string }).tool_call_id ?? null,
              };
            }),
          };
          const response = await fetch(`${apiBase}/api/v2/threads/${tid}/messages/save`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          if (!response.ok) throw new Error(`message save failed: ${response.status}`);

          const saved = savedMsgIdsRef.current.get(tid) ?? new Set<string>();
          toSend.forEach((m) => m.id && saved.add(m.id));
          savedMsgIdsRef.current.set(tid, saved);
        } catch (err) {
          console.warn("[useChat] Failed to save messages to local store:", err);
        }
      });
      saveQueueRef.current.set(tid, current);
      try {
        await current;
      } finally {
        if (saveQueueRef.current.get(tid) === current) saveQueueRef.current.delete(tid);
      }
    },
    [],
  );

  // === 取消链路（dsh：停止 = 停止观看 + 停止计算 + 取消记忆） ===

  /** 把 run 记入墓碑并持久化（重连过滤的依据）。 */
  const tombstoneRuns = useCallback((tid: string, runIds: string[]) => {
    if (!tid || runIds.length === 0) return;
    const map = cancelledRunsRef.current;
    if (!map) return;
    const set = map.get(tid) ?? new Set<string>();
    runIds.forEach((id) => set.add(id));
    map.set(tid, set);
    persistCancelledRuns(map);
  }, []);

  /**
   * 停止计算：先把目标 run 记入墓碑，再取消服务端 run。
   * - runIds 缺省时先 runs.list 抓当前活跃 run（stop 按钮路径）
   * - cancelMany 失败仅告警——墓碑已保证重连不会误判为运行中
   */
  const cancelThreadRuns = useCallback(
    async (tid: string, runIds?: string[]) => {
      if (!tid) return;
      let ids = runIds;
      if (!ids) {
        try {
          const runs = await client.runs.list(tid, { limit: 10 });
          ids = (Array.isArray(runs) ? runs : [])
            .filter(
              (r: { status?: string; run_id?: string }) =>
                (r.status === "running" || r.status === "pending") && !!r.run_id,
            )
            .map((r: { run_id?: string }) => r.run_id as string);
        } catch {
          // runs.list 失败仍尝试整线程取消
          ids = [];
        }
      }
      if (ids.length > 0) tombstoneRuns(tid, ids);
      try {
        await client.runs.cancelMany(
          ids && ids.length > 0
            ? { threadId: tid, runIds: ids }
            : { threadId: tid, status: "all" },
        );
      } catch (err) {
        console.warn("[useChat] 服务端取消失败（本地已停止，墓碑已记录）:", err);
      }
      // wait=true 收敛等待：interrupt 取消要等下一个检查点才生效，卡死的
      // run（LLM 调用挂起、永远到不了检查点）只有带 wait 的取消会真正落
      // 地（2026-08-28 实测：不带 wait 的取消挂 11 小时不收敛）。SDK 的
      // cancelMany 不透传 wait，走 REST 直调；15s 上限防止无限等待
      try {
        await fetch(`${getDeploymentUrl()}/runs/cancel`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ thread_id: tid, status: "all", wait: true }),
          signal: AbortSignal.timeout(15000),
        });
      } catch {
        // 超时/网络失败：取消请求已发出，墓碑已保证 UI 不误判为运行中
      }
    },
    [client, tombstoneRuns],
  );

  // === Reconnection logic: detect and reconnect to active runs after page refresh ===
  // When threadId changes (or on mount), check if the thread has an active run
  // and reconnect to it via runs.joinStream(). This handles the case where the
  // user refreshes the page while AI is streaming.
  const reconnectAbortRef = useRef<AbortController | null>(null);
  const reconnectDepsRef = useRef({ saveMessagesToLocalStore, scheduleHistoryRevalidate, paginated, client });
  reconnectDepsRef.current = { saveMessagesToLocalStore, scheduleHistoryRevalidate, paginated, client };
  // 重连流复用 processStreamEvents（定义在本文件更下方，TDZ 限制不能直接
  // 进 deps/ref 初始化；渲染到定义之后再填充本 ref）。
  const reconnectStreamHandlerRef = useRef<((stream: AsyncIterable<{ event: string; data: unknown }>, tid: string, ac: AbortController) => Promise<void>) | null>(null);

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
        const runsArr = Array.isArray(runs) ? runs : [];

        // 墓碑过滤：用户取消过、但服务端状态尚未收敛（interrupt 取消等
        // 下一个检查点）的 run 不算活流，否则切回会话会误显示「输出中」。
        // 顺带清掉已离开活跃列表的墓碑项（防集合无限增长）。
        const tombMap = cancelledRunsRef.current;
        const tomb = tombMap?.get(threadId);
        if (tomb && tomb.size > 0) {
          if (pruneTombstones(tomb, runsArr) && tombMap) persistCancelledRuns(tombMap);
        }

        const activeRun = pickActiveRun(runsArr, tomb);

        if (!activeRun?.run_id || abortController.signal.aborted) {
          // No active run — check if conversation is incomplete and sync from LangGraph
          const completedRun = runsArr.find(
            (r: { status?: string }) => r.status === "success"
          );
          if (completedRun && !abortController.signal.aborted) {
            await _syncIncompleteThread(threadId, pag, scheduleRevalidate);
          }
          return;
        }

        // 僵尸 run 检测：LangGraph inmem 是单并发队列，一个卡死的 run
        // （LLM 调用挂起等）会保持 running/pending 并阻塞**所有**新会话的
        // 调度。创建超过 30 分钟仍活跃的 run 视为疑似卡死：不 join（join
        // 会永远「输出中」无输出），提示用户用停止按钮清理。
        // 例外：run 若停在审批 interrupt 上，它在等的是用户决策而不是死了
        // ——此时不弹「卡死」警告，由 checkThreadInterrupt 弹审批卡片。
        const createdAt = Date.parse((activeRun as { created_at?: string }).created_at ?? "");
        if (createdAt && Date.now() - createdAt > 30 * 60 * 1000) {
          let waitingApproval = false;
          try {
            const staleState = (await cli.threads.getState(threadId)) as unknown as {
              interrupts?: unknown[];
              tasks?: Array<{ interrupts?: unknown[] }>;
            };
            const pending =
              (staleState.interrupts?.length ?? 0) > 0 ||
              (staleState.tasks ?? []).some((t) => (t.interrupts?.length ?? 0) > 0);
            waitingApproval = pending;
          } catch {
            // state 查询失败按原逻辑处理
          }
          if (waitingApproval) {
            console.log("[useChat] Reconnect: stale run is waiting for approval, skipping zombie warning");
            return;
          }
          console.warn(
            `[useChat] Reconnect: stale run ${activeRun.run_id} (${((Date.now() - createdAt) / 60000).toFixed(1)}min old) skipped`,
          );
          toast.warning(
            "该会话存在运行超过 30 分钟的后台任务，可能已卡死（会阻塞新对话调度）。点击停止按钮可清理。",
          );
          return;
        }

        console.log("[useChat] Reconnect: joining run %s (status=%s)", activeRun.run_id?.substring(0, 8), activeRun.status);

        // Step 2: Found an active run - reconnect to its stream
        // Mark this thread as loading
        loadingThreadsRef.current.set(threadId, true);
        bumpLoadingIfViewed(threadId);

        try {
          // joinStream 不透传 subgraphs，事件不带命名空间；复用发送流的
          // processStreamEvents 做实时渲染 + 子智能体尽力分流（依赖
          // messages/metadata 的 ns 映射）+ 增量保存。即便仍有子图消息
          // 混入渲染层，流结束后的权威回填（messages/sync prune）也会用
          // LangGraph state 覆盖纠正 —— 实时性与正确性兼得。
          const stream = cli.runs.joinStream(threadId, activeRun.run_id, {
            streamMode: ["messages", "tasks"],
            signal: abortController.signal,
          });

          const handler = reconnectStreamHandlerRef.current;
          if (handler) {
            await handler(stream, threadId, abortController);
          } else {
            for await (const _event of stream) {
              if (abortController.signal.aborted) break;
            }
          }
        } finally {
          loadingThreadsRef.current.set(threadId, false);
          bumpLoadingIfViewed(threadId);
          // 重连流结束同样收敛子智能体状态
          subagentStoreRef.current.closeAllTasks();
          bumpSubagentVersion();

          // 权威回填：state 只含根图消息，能补全增量保存漏掉的消息
          // （如派发 task 的那条）；prune 清理此前可能已污染进库的
          // 子智能体内部消息
          let backfillOk = false;
          try {
            const apiBase = getFastapiUrl();
            const res = await fetch(
              `${apiBase}/api/v2/threads/${threadId}/messages/sync?prune=true`,
              { method: "POST" },
            );
            if (res.ok) {
              backfillOk = true;
              const data = await res.json();
              if (data.pruned > 0) {
                console.log("[useChat] Reconnect sync pruned %d leaked messages", data.pruned);
              }
            }
          } catch {
            // sync 失败不阻塞：本地已保存的内容仍可显示
          }

          // 回填成功才丢弃重连流的渲染缓冲（避免回填失败时丢内容）；
          // mergedMessages 按 id 合并，残留也不会产生重复。
          if (backfillOk) {
            streamDataRef.current.delete(threadId);
          }
          flushStreamRender(threadId);

          await pag.mutate();

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
  }, [threadId, assistantId, isViewedThread, scheduleStreamRender, flushStreamRender, bumpLoadingIfViewed, upsertStreamMessage]);

  /**
  /**
   * Detect a pending approval interrupt on a thread (execute 命令等待审批).
   * Called after each stream ends and on thread switches — the card also
   * re-appears after a page refresh. Command text is taken from the actual
   * tool-call args in the interrupt payload (dsh anti-spoofing principle).
   */
  const checkThreadInterrupt = useCallback(
    async (tid?: string | null) => {
      const target = tid ?? threadId;
      if (!target || !client) return;
      try {
        const snap = (await client.threads.getState(target)) as unknown as {
          // 0.13 的 ThreadState 同时有顶层 interrupts 和 tasks[].interrupts，
          // 两种形状都扫，避免审批卡片因形状差异永远不出现。
          interrupts?: Array<{
            value?: {
              action_requests?: Array<{
                name?: string;
                args?: Record<string, unknown>;
                description?: string;
              }>;
            };
          }>;
          tasks?: Array<{
            interrupts?: Array<{
              value?: {
                action_requests?: Array<{
                  name?: string;
                  args?: Record<string, unknown>;
                  description?: string;
                }>;
              };
            }>;
          }>;
        };
        const allInterrupts = [
          ...(snap.interrupts ?? []),
          ...(snap.tasks ?? []).flatMap((task) => task.interrupts ?? []),
        ];
        for (const int of allInterrupts) {
          const request = int.value?.action_requests?.[0];
          if (request?.name) {
              if (target === (viewedThreadIdRef.current ?? "")) {
                setInterrupt({
                  threadId: target,
                  toolName: request.name,
                  command: String(
                    (request.args as { command?: unknown } | undefined)?.command ?? "",
                  ),
                  description: String(request.description ?? ""),
                  args: request.args ?? {},
                });
              }
              return;
            }
        }
        setInterrupt((prev) => (prev && prev.threadId === target ? null : prev));
      } catch {
        // Thread missing or already finished — keep current state.
      }
    },
    [client, threadId],
  );

  // Re-check for a pending approval when switching threads (refresh recovery).
  useEffect(() => {
    setInterrupt(null);
    if (threadId) checkThreadInterrupt(threadId);
  }, [threadId, checkThreadInterrupt]);

  /** Configurable of the most recent run — reused by resumeInterrupt (审批续跑). */
  const lastRunConfigRef = useRef<Record<string, string>>({});

  /** Consume a runs.stream SSE feed into the per-thread stream buffer. */
  const processStreamEvents = useCallback(
    async (
      stream: AsyncIterable<{ event: string; data: unknown }>,
      streamingThreadId: string,
      abortController: AbortController,
    ) => {
      let eventCount = 0;
      let lastSaveTime = 0;
      for await (const event of stream) {
        if (abortController.signal.aborted) break;

        const eventType = event.event;
        const eventData = event.data;
        if (!eventData) continue;

        try {
          if (
            (eventType === "tasks" || eventType.startsWith("tasks|")) && eventData
          ) {
            // LangGraph prefixes nested task events with `tasks|<namespace>`.
            // The payload itself carries the original tool_call id.
            subagentStoreRef.current.noteTaskEvent(eventType, eventData);
            bumpSubagentVersion();
          } else if (
            (eventType === "messages/partial" ||
              eventType === "messages/complete") &&
            Array.isArray(eventData)
          ) {
            for (const msg of eventData) {
              if (msg && msg.id && msg.type) {
                // 子智能体内部消息（深 namespace）：收入活动 feed，不进主消息流/不入库
                if (subagentStoreRef.current.consume(msg as Record<string, unknown>)) {
                  bumpSubagentVersion();
                  continue;
                }
                upsertStreamMessage(streamingThreadId, msg as Message);
                scheduleStreamRender(streamingThreadId);

                // Incremental persistence: save the delta to SQLite periodically
                eventCount++;
                const now = Date.now();
                if (
                  eventCount >= INCREMENTAL_SAVE_INTERVAL &&
                  now - lastSaveTime >= INCREMENTAL_SAVE_MIN_INTERVAL_MS
                ) {
                  eventCount = 0;
                  lastSaveTime = now;
                  const currentMsgs = streamDataRef.current.get(streamingThreadId) ?? [];
                  // Fire-and-forget incremental save (don't block the stream)
                  saveMessagesToLocalStore(streamingThreadId, currentMsgs).catch(() => {});
                }
              }
            }
          } else if (eventType === "messages/metadata" && eventData && !Array.isArray(eventData)) {
            subagentStoreRef.current.noteMetadata(eventData);
          } else if (eventType === "metadata" && eventData) {
            const meta = eventData as { run_id?: string; thread_id?: string };
            if (meta.thread_id) {
              setThreadId(meta.thread_id);
            }
          } else if (eventType === "error" && eventData) {
            console.error("[useChat] Stream error event:", eventData);
            toast.error(`对话请求失败：${streamErrorMessage(eventData)}`);
          }
        } catch {
          // Skip malformed events
        }
      }
    },
    [upsertStreamMessage, scheduleStreamRender, saveMessagesToLocalStore, setThreadId, bumpSubagentVersion],
  );

  // processStreamEvents 定义之后才能安全引用（见 reconnectStreamHandlerRef
  // 处的 TDZ 说明）：重连流复用它做实时渲染。
  reconnectStreamHandlerRef.current = processStreamEvents;

  /** Shared stream finalization: save, drop overlay, revalidate, detect interrupts. */
  const finalizeStream = useCallback(
    async (tid: string | null | undefined) => {
      const finalThreadId = tid ?? "";

      loadingThreadsRef.current.set(finalThreadId, false);
      bumpLoadingIfViewed(finalThreadId);
      abortMapRef.current.delete(finalThreadId);
      // 流结束 = 没有子智能体还在跑；收敛所有「执行中」状态
      subagentStoreRef.current.closeAllTasks();
      bumpSubagentVersion();

      // Save completed messages to local store (await to ensure SQLite has data)
      const finalMsgs = streamDataRef.current.get(finalThreadId) ?? [];
      if (finalThreadId && finalMsgs.length > 0) {
        await saveMessagesToLocalStore(finalThreadId, finalMsgs, { final: true });
      }

      // Wait until the paginated store actually holds the final messages
      // before dropping the stream overlay — avoids a content flash.
      // Must go through paginatedRef: the paginated captured when the send
      // started (threadId=null on a brand-new chat) carries a mutate bound
      // to a falsy infiniteKey — a no-op in SWR — and the reply would
      // disappear the moment the overlay was dropped.
      if (finalThreadId && finalThreadId === threadIdRef.current) {
        await paginatedRef.current.mutate();
      }
      streamDataRef.current.delete(finalThreadId);
      flushStreamRender(finalThreadId);

      completedButUnconfirmedRef.current.delete(finalThreadId);

      // Refresh thread list and management data
      scheduleHistoryRevalidate();

      // The stream ends both on completion AND on a pending approval
      // interrupt — check for the latter so the approval card shows up.
      await checkThreadInterrupt(finalThreadId);
    },
    [saveMessagesToLocalStore, paginated, flushStreamRender, bumpLoadingIfViewed, scheduleHistoryRevalidate, checkThreadInterrupt],
  );

  /**
   * Send a message using LangGraph Client runs.stream() directly.
   * The stream runs in the background and is keyed by thread ID,
   * so switching to a different thread won't interrupt it.
   */
  const sendMessage = useCallback(
    async (content: string, contentBlocks?: ContentBlock[], context?: { repoPath?: string }) => {
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
        const workspacePath = fb.metadata?.workspacePath;

        if (workspacePath) {
          // Path reference only — embedding the full text bloats thread state.
          fileTextParts.push(
            `### File: ${filename}\n\n文件已上传到工作区：${workspacePath}\n请先用 read_file 工具读取该文件的完整内容再进行分析，不要凭空猜测内容。`,
          );
        } else {
          fileTextParts.push(
            `### File: ${filename}\n\n[文件上传到工作区失败，无法提供路径。请告知用户重新上传或直接粘贴文本内容。]`,
          );
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
      const attachmentMetadata = fileBlocks.map((block) => ({
        type: block.type,
        mimeType: block.mimeType,
        metadata: block.metadata ?? {},
      }));
      if (attachmentMetadata.length > 0) {
        const metadataByMessage = attachmentMetadataRef.current.get(threadId ?? "") ?? new Map();
        metadataByMessage.set(newMessage.id, attachmentMetadata);
        attachmentMetadataRef.current.set(threadId ?? "", metadataByMessage);
      }

      // Abort any existing stream on the SAME thread only
      let currentThreadId = threadId;
      if (currentThreadId) {
        const oldAbort = abortMapRef.current.get(currentThreadId);
        if (oldAbort) oldAbort.abort();
      }

      const abortController = new AbortController();
      // 本次发送创建的 run id（onRunCreated 回调赋值）——finally 精确取消用
      let myRunId: string | null = null;

      // Mark this thread as loading
      loadingThreadsRef.current.set(currentThreadId ?? "", true);
      bumpLoadingIfViewed(currentThreadId ?? "");

      // Add user message to this thread's stream data
      const tid = currentThreadId ?? "";
      const prev = streamDataRef.current.get(tid) ?? [];
      streamDataRef.current.set(tid, [...prev, newMessage]);
      scheduleStreamRender(tid);

      // Incremental save state lives inside processStreamEvents now.

      try {
        // Get or create thread
        if (!currentThreadId) {
          const newThread = await client.threads.create();
          currentThreadId = newThread.thread_id;
          setThreadId(currentThreadId);

          // 会话列表条目不在此注册：首条消息保存时后端 _upsert_thread_info
          // 自动建行并推导标题（原子，避免与注册并发插行撞 UNIQUE 导致
          // 保存回滚丢消息）

          // Migrate data from empty key to real thread ID
          const pending = streamDataRef.current.get("") ?? [];
          streamDataRef.current.delete("");
          streamDataRef.current.set(currentThreadId, pending);
          const pendingMetadata = attachmentMetadataRef.current.get("");
          if (pendingMetadata) {
            attachmentMetadataRef.current.delete("");
            attachmentMetadataRef.current.set(currentThreadId, pendingMetadata);
          }
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
              const pendingMetadata = attachmentMetadataRef.current.get(currentThreadId);
              if (pendingMetadata) {
                attachmentMetadataRef.current.delete(currentThreadId);
                attachmentMetadataRef.current.set(recreated.thread_id, pendingMetadata);
              }
              abortMapRef.current.delete(currentThreadId);
              abortMapRef.current.set(recreated.thread_id, abortController);
              loadingThreadsRef.current.delete(currentThreadId);
              loadingThreadsRef.current.set(recreated.thread_id, true);
              currentThreadId = recreated.thread_id;
              setThreadId(currentThreadId);

              // 列表条目同样由首条消息保存自动注册（_upsert_thread_info）
            }
          }
        }

        const streamingThreadId = currentThreadId;

        // Remember the run's configurable so a later resume (approval decision)
        // keeps the same repo mount / effort / approval switch.
        lastRunConfigRef.current = {
          space_id: workspaceId || "default",
          repo_path: context?.repoPath || "",
          permission_mode: permissionMode,
          ...(reasoningEffort
            ? { llm_reasoning_effort: reasoningEffort }
            : {}),
        };

        // 竞态预检：用户可能在 run 创建前就点了停止（发送后立即停止）。
        // 不起 run——本地已保存的用户消息由 finally 的 finalizeStream 落盘。
        if (abortController.signal.aborted) {
          return;
        }

        // 立即持久化用户消息：懒创建下这也是会话列表条目的诞生点——
        // 保存触发后端 _upsert_thread_info 建行+推导标题，成功后刷新
        // 列表让新会话在流式期间就出现在侧栏（useThreads 无轮询）
        saveMessagesToLocalStore(streamingThreadId, [newMessage])
          .then(() => scheduleHistoryRevalidate())
          .catch(() => {});

        // run 创建瞬间拿到 run id：若此刻 signal 已中止（stopStream 的
        // cancelMany 早于 run 创建执行、什么都没取消到），立即精确取消
        // 并记入墓碑，不留孤儿 run 在服务端继续跑
        const onRunCreated = ({ run_id }: { run_id: string }) => {
          if (!run_id) return;
          myRunId = run_id;
          if (abortController.signal.aborted) {
            tombstoneRuns(streamingThreadId, [run_id]);
            client.runs
              .cancelMany({ threadId: streamingThreadId, runIds: [run_id] })
              .catch(() => {});
          }
        };

        const stream = client.runs.stream(
          streamingThreadId,
          assistantId,
          {
            input: { messages: [newMessage] },
            config: {
              recursion_limit: 1000,
              configurable: lastRunConfigRef.current,
            },
            streamMode: ["messages", "tasks"],
            streamSubgraphs: true,
            onRunCreated,
            // SDK 实现层透传 signal（类型未声明，见 client/runs/index.js）：
            // 本地 abort 立即掐断 SSE 连接，而不是等下一个事件才检查标志
            ...({ signal: abortController.signal }),
          },
        );

        // Process SSE events - updates streamDataRef for this specific thread
        await processStreamEvents(stream, streamingThreadId, abortController);
      } catch (err: unknown) {
        if (err instanceof Error && err.name === "AbortError") {
          // User aborted, not an error
        } else {
          console.error("[useChat] Stream error:", err);
        }
      } finally {
        // 竞态补刀：取消可能早于 run 创建执行（发送后立即停止）。
        // 仅当本流未被同线程的新发送顶替时才取消——顶替时 abortMapRef
        // 已换成新 controller，此时取消会误杀新 run
        if (abortController.signal.aborted && currentThreadId) {
          if (
            shouldCancelAbortedRun(
              abortMapRef.current.get(currentThreadId),
              abortController,
            )
          ) {
            await cancelThreadRuns(currentThreadId, myRunId ? [myRunId] : undefined);
          }
        }
        await finalizeStream(currentThreadId);
      }

      onHistoryRevalidate?.();
    },
    [threadId, assistantId, client, workspaceId, setThreadId, scheduleHistoryRevalidate, onHistoryRevalidate, paginated, saveMessagesToLocalStore, isViewedThread, scheduleStreamRender, flushStreamRender, bumpLoadingIfViewed, upsertStreamMessage, reasoningEffort, permissionMode, processStreamEvents, finalizeStream, tombstoneRuns, cancelThreadRuns],
  );

  /**
   * 停止按钮 = 停止观看 + 停止计算（dsh 语义）。
   * 1) 本地立即收敛为空闲：abort 掐断 SSE（signal 已透传给 runs.stream），
   *    UI 即刻回到可输入态，不等服务端
   * 2) 中断前缀定稿（dsh cancelled-stream-prefix-finalize）：给最后一条
   *    流式 AI 消息打 stopped_by_user 标记，新对象引用穿透 ChatMessage
   *    的 memo；标记随 additional_kwargs 落库，刷新后仍能重建「已停止」
   * 3) 异步停止计算：墓碑 + cancelMany。取消与 run 创建的竞态由
   *    sendMessage 的 onRunCreated / finally 补刀兜底
   */
  const stopStream = useCallback(async () => {
    const tid = threadId ?? "";
    const abort = abortMapRef.current.get(tid);
    if (abort) {
      abort.abort();
      abortMapRef.current.delete(tid);

      const arr = streamDataRef.current.get(tid);
      if (arr && arr.length > 0) {
        for (let i = arr.length - 1; i >= 0; i--) {
          const m = arr[i] as Message & { additional_kwargs?: Record<string, unknown> };
          if (m.type === "ai") {
            arr[i] = {
              ...m,
              additional_kwargs: { ...(m.additional_kwargs ?? {}), stopped_by_user: true },
            };
            break;
          }
        }
        flushStreamRender(tid);
      }
    }
    // 本地立即回到空闲；服务端取消异步收敛，墓碑保证期间不被误判
    loadingThreadsRef.current.set(tid, false);
    bumpLoadingIfViewed(tid);

    await cancelThreadRuns(tid);
  }, [threadId, bumpLoadingIfViewed, cancelThreadRuns, flushStreamRender]);

  /**
   * Answer a pending approval interrupt (dsh: allowed-once / rejected) and
   * continue the paused run on the same thread with the original config.
   */
  const resumeInterrupt = useCallback(
    async (decision: "approve" | "reject", reason?: string) => {
      const tid = interrupt?.threadId ?? threadId;
      if (!tid || !interrupt || !assistantId) return;
      const decisions = [
        { type: decision, ...(reason ? { message: reason } : {}) },
      ];
      setInterrupt(null);

      const oldAbort = abortMapRef.current.get(tid);
      if (oldAbort) oldAbort.abort();
      const abortController = new AbortController();
      abortMapRef.current.set(tid, abortController);
      loadingThreadsRef.current.set(tid, true);
      bumpLoadingIfViewed(tid);

      try {
        const stream = client.runs.stream(tid, assistantId, {
          command: { resume: { decisions } },
          config: {
            recursion_limit: 1000,
            configurable: {
              space_id: workspaceId || "default",
              ...lastRunConfigRef.current,
            },
          },
          streamMode: ["messages", "tasks"],
          streamSubgraphs: true,
          // SDK 实现层透传 signal（类型未声明）——本地 abort 立即掐断 SSE
          ...({ signal: abortController.signal }),
        });
        await processStreamEvents(stream, tid, abortController);
      } catch (err: unknown) {
        if (err instanceof Error && err.name === "AbortError") {
          // User aborted, not an error
        } else {
          console.error("[useChat] Resume error:", err);
          toast.error("恢复对话失败，请重试");
        }
      } finally {
        // 与 sendMessage 相同的竞态补刀：仅当本流未被新发送顶替时取消
        if (abortController.signal.aborted) {
          if (shouldCancelAbortedRun(abortMapRef.current.get(tid), abortController)) {
            await cancelThreadRuns(tid);
          }
        }
        await finalizeStream(tid);
      }
    },
    [interrupt, threadId, assistantId, client, workspaceId, processStreamEvents, finalizeStream, bumpLoadingIfViewed, cancelThreadRuns],
  );

  /** 子智能体活动 feed（task 调用 id -> 事件列表）；subagentVersion 变化时刷新 */
  const getSubAgentFeed = useCallback(
    (taskCallId: string): SubAgentEvent[] => subagentStoreRef.current.getFeed(taskCallId),
    [],
  );

  /** 该 task 是否已结束（结果已返回，或整个 run 已结束） */
  const isSubAgentTaskClosed = useCallback(
    (taskCallId: string): boolean => subagentStoreRef.current.isTaskClosed(taskCallId),
    [],
  );

  return {
    stream: null,
    messages: mergedMessages,
    isLoading: isCurrentThreadLoading,
    sendMessage,
    stopStream,
    resumeInterrupt,
    /** 按需创建线程（懒创建）：首条消息前的文件上传用 */
    ensureThreadId,
    todos: [] as TodoItem[],
    files: {} as Record<string, unknown>,
    ui: undefined as unknown[] | undefined,
    interrupt,
    threadId,
    setThreadId,
    streamLoadFailed: !!paginated.error,
    historyError: paginated.error ? String(paginated.error) : null,
    isLoadingHistory: paginated.isLoading || paginated.isValidating,
    hasOlderMessages: paginated.hasMore,
    loadOlderMessages: paginated.loadMore,
    subagentVersion,
    getSubAgentFeed,
    isSubAgentTaskClosed,
  };
}
