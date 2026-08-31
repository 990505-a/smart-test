"use client";

/**
 * 子智能体实时活动存储（dsh 原则：子代理内部过程不进父会话流）。
 *
 * 开启 streamSubgraphs 后，SSE 会额外下发两类数据：
 * - "messages/metadata" 事件：{msgId: {metadata: {langgraph_checkpoint_ns}}}
 * - 子图内部的 messages/partial / messages/complete（ns 嵌套更深）
 *
 * 根图的 checkpoint ns 形如 "tools:<uuid>"（单段）；子智能体在 task 工具
 * 内部执行嵌套子图，其消息 ns 有 ≥2 个冒号。据此把子智能体内部消息从主
 * 消息流分流到按 task 调用归属的活动 feed，父流保持干净、不入库。
 */

export interface SubAgentEvent {
  id: string;
  kind: "tool" | "text";
  name?: string;
  preview: string;
  /** text 事件的完整内容（保留换行，供面板按 markdown 实时渲染） */
  fullText?: string;
  status: "running" | "done" | "error";
  ts: number;
}

const MAX_FEED_EVENTS = 200;
const PREVIEW_CHARS = 160;

function stringifyValue(value: unknown): string {
  let s: string;
  if (typeof value === "string") s = value;
  else if (value == null) s = "";
  else {
    try {
      s = JSON.stringify(value) ?? "";
    } catch {
      s = String(value);
    }
  }
  return s;
}

/** 消息正文 → 纯文本：content 可能是 string 或内容块数组
 * （[{type:"text",text:"…"}]），后者直接 stringify 会把 JSON 结构
 * 原样显示出来，先抽出各块的 text 再拼接 */
function contentToText(value: unknown): string {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) {
    const parts: string[] = [];
    for (const block of value) {
      if (typeof block === "string") {
        parts.push(block);
      } else if (
        block &&
        typeof block === "object" &&
        typeof (block as Record<string, unknown>).text === "string"
      ) {
        parts.push((block as Record<string, unknown>).text as string);
      }
    }
    if (parts.length > 0) return parts.filter(Boolean).join("\n\n");
  }
  return stringifyValue(value);
}

/** 单行预览（摘要/工具参数用）：压平所有空白并截断 */
function previewOf(value: unknown): string {
  const flat = contentToText(value).replace(/\s+/g, " ").trim();
  return flat.length > PREVIEW_CHARS ? flat.slice(0, PREVIEW_CHARS) + "…" : flat;
}

/** 完整文本（流式输出渲染用）：保留换行结构，只压多余空行 */
function fullTextOf(value: unknown): string {
  return contentToText(value)
    .split("\n")
    .map((l) => l.replace(/[ \t]+/g, " ").trimEnd())
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

interface StreamMsg {
  id?: unknown;
  type?: unknown;
  content?: unknown;
  name?: unknown;
  tool_calls?: Array<{ id?: unknown; name?: unknown; args?: unknown }> | null;
  tool_call_id?: unknown;
}

export class SubAgentActivityStore {
  /** messages/metadata: msg id -> checkpoint ns */
  private metaById = new Map<string, string>();
  /** Pregel task id (the suffix in tools:<id>) -> parent LLM tool call id. */
  private pregelTaskToCall = new Map<string, string>();
  /** 已被启发式配对占用的 task call id（防止两个子图配到同一个） */
  private pairedCallIds = new Set<string>();
  /** 已出现过的子图根 pregel id（按首次出现顺序，供并行配对） */
  private seenPregelRoots: string[] = [];
  /** Open task calls are only a fallback when the protocol gives no owner. */
  private openTaskCallIds: string[] = [];
  private seenTaskCallIds = new Set<string>();
  /** 已返回结果的 task 调用 id —— 内联状态条/面板据此收敛「执行中」 */
  private closedTaskCallIds = new Set<string>();
  private feeds = new Map<string, SubAgentEvent[]>();
  version = 0;

  noteMetadata(data: unknown): void {
    if (!data || typeof data !== "object" || Array.isArray(data)) return;
    for (const [mid, payload] of Object.entries(data as Record<string, unknown>)) {
      const md = (payload as { metadata?: Record<string, unknown> } | null)?.metadata;
      const cns = md?.langgraph_checkpoint_ns ?? md?.checkpoint_ns;
      if (typeof cns === "string") this.metaById.set(mid, cns);
    }
    if (this.metaById.size > 4000) {
      const it = this.metaById.keys();
      for (let i = 0; i < 1000; i++) {
        const k = it.next().value as string;
        this.metaById.delete(k);
      }
    }
  }

  /** Consume the official tasks stream, whose payload carries the original
   * LLM tool_call id while the namespace carries only the Pregel task id. */
  noteTaskEvent(eventType: string, data: unknown): void {
    if (!data || typeof data !== "object") return;
    const item = data as Record<string, unknown>;
    const pregelId = typeof item.id === "string" ? item.id : null;
    const input = item.input as Record<string, unknown> | undefined;
    const toolCall = input?.tool_call as Record<string, unknown> | undefined;
    const callId = typeof toolCall?.id === "string" ? toolCall.id : null;
    if (pregelId && callId) {
      this.pregelTaskToCall.set(pregelId, callId);
      if (!this.feeds.has(callId)) this.feeds.set(callId, []);
    }
    if (eventType.includes("result") || item.result !== undefined || item.error) {
      if (pregelId) {
        const owner = this.pregelTaskToCall.get(pregelId);
        if (owner) this.closedTaskCallIds.add(owner);
      }
    }
    this.version++;
  }

  private namespaceForMessage(msgId: string): string | null {
    const cns = this.metaById.get(msgId);
    if (!cns) return null;
    return cns;
  }

  private pregelIdFromNamespace(cns: string): string | null {
    for (const segment of cns.split("|")) {
      const colon = segment.indexOf(":");
      if (colon >= 0 && segment.startsWith("tools")) {
        return segment.slice(colon + 1);
      }
    }
    return null;
  }

  private isSubgraphMessage(msgId: unknown): boolean {
    if (typeof msgId !== "string") return false;
    const cns = this.namespaceForMessage(msgId);
    return !!cns && cns.includes("|") && cns.startsWith("tools:");
  }

  private ownerFromNs(msgId: unknown): string | null {
    if (typeof msgId !== "string") return null;
    const cns = this.namespaceForMessage(msgId);
    if (!cns) return null;
    const rootPregelId = this.pregelIdFromNamespace(cns);
    if (!rootPregelId) return null;
    const known = this.pregelTaskToCall.get(rootPregelId);
    if (known) return known;

    // ---- 启发式配对（关键）：新版协议的 tasks 事件不再携带 tool_call id，
    // 映射只能等 task 结束才由根工具结果建立——期间子图消息会全部进孤儿桶，
    // 面板永远停在「正在启动…」。改为：子图根 pregel id 首次出现时，把它配给
    // 最早派发且尚未配对的开放 task 调用。顺序场景（一次一个子代理）精确；
    // 并行场景按「派发顺序≈子图启动顺序」配对，LangGraph 按调用顺序执行工具。
    if (!this.seenPregelRoots.includes(rootPregelId)) {
      this.seenPregelRoots.push(rootPregelId);
    }
    const openUnpaired = this.openTaskCallIds.find(
      (callId) => !this.pairedCallIds.has(callId) && !this.closedTaskCallIds.has(callId),
    );
    if (openUnpaired) {
      this.pregelTaskToCall.set(rootPregelId, openUnpaired);
      this.pairedCallIds.add(openUnpaired);
      this.feeds.get(openUnpaired) ?? this.feeds.set(openUnpaired, []);
      return openUnpaired;
    }
    return null;
  }

  /**
   * 观察一条流消息：
   * - 根图消息：跟踪 task 调用的开闭（归属用），返回 false（照常进主消息流）
   * - 子图消息：收入当前开放 task 的活动 feed，返回 true（调用方不得合入主消息流）
   */
  consume(msg: StreamMsg): boolean {
    const id = typeof msg.id === "string" ? msg.id : null;
    if (!id) return false;

    if (!this.isSubgraphMessage(id)) {
      if (msg.type === "ai" && Array.isArray(msg.tool_calls)) {
        for (const tc of msg.tool_calls) {
          const tcId = typeof tc?.id === "string" ? tc.id : null;
          if (tcId && tc.name === "task" && !this.seenTaskCallIds.has(tcId)) {
            this.seenTaskCallIds.add(tcId);
            this.openTaskCallIds.push(tcId);
            if (!this.feeds.has(tcId)) this.feeds.set(tcId, []);
          }
        }
      } else if (msg.type === "tool" && typeof msg.tool_call_id === "string") {
        const tcId = msg.tool_call_id;
        const cns = this.namespaceForMessage(id);
        const pregelId = cns ? this.pregelIdFromNamespace(cns) : null;
        if (pregelId) {
          this.pregelTaskToCall.set(pregelId, tcId);
          if (!this.feeds.has(tcId)) this.feeds.set(tcId, []);
        }
        if (this.seenTaskCallIds.has(tcId)) {
          this.closedTaskCallIds.add(tcId);
          this.openTaskCallIds = this.openTaskCallIds.filter((openId) => openId !== tcId);
        }
      }
      return false;
    }

    // ---- 子智能体内部消息 ----
    // 归属优先级：ns 里的 task call id（并行精确路由）→ 最近派发且未返回
    // 的 task（顺序场景回退）→ 孤儿桶
    const owner = this.ownerFromNs(id) ?? "__orphan__";
    const feed = this.feeds.get(owner) ?? [];
    this.feeds.set(owner, feed);

    if (msg.type === "ai") {
      const text = previewOf(msg.content);
      const full = fullTextOf(msg.content);
      if (text) {
        // 流式 partial 共享同一 id：原地更新最后一条同 id 事件
        const idx = findLastIndex(feed, (e) => e.id === id && e.kind === "text");
        if (idx >= 0) {
          feed[idx] = { ...feed[idx], preview: text, fullText: full, ts: Date.now() };
        } else {
          feed.push({ id, kind: "text", preview: text, fullText: full, status: "done", ts: Date.now() });
        }
      }
      if (Array.isArray(msg.tool_calls)) {
        for (const tc of msg.tool_calls) {
          const tcId = typeof tc?.id === "string" ? tc.id : `${id}-tc-${feed.length}`;
          if (findLastIndex(feed, (e) => e.id === tcId) < 0) {
            feed.push({
              id: tcId,
              kind: "tool",
              name: typeof tc?.name === "string" ? tc.name : undefined,
              preview: previewOf(tc?.args),
              status: "running",
              ts: Date.now(),
            });
          }
        }
      }
    } else if (msg.type === "tool") {
      const resultText = typeof msg.content === "string" ? msg.content : previewOf(msg.content);
      const trimmed = resultText.trim();
      const isError = /^error\b/i.test(trimmed) || trimmed.startsWith("错误") || trimmed.includes("handle_tool_error");
      const tcId = typeof msg.tool_call_id === "string" ? msg.tool_call_id : null;
      const idx = tcId ? findLastIndex(feed, (e) => e.id === tcId && e.kind === "tool") : -1;
      const status: SubAgentEvent["status"] = isError ? "error" : "done";
      if (idx >= 0) {
        feed[idx] = { ...feed[idx], status, preview: previewOf(resultText) || feed[idx].preview, ts: Date.now() };
      } else {
        feed.push({
          id: tcId ?? `${id}-tool-${feed.length}`,
          kind: "tool",
          name: typeof msg.name === "string" ? msg.name : undefined,
          preview: previewOf(resultText),
          status,
          ts: Date.now(),
        });
      }
    }

    if (feed.length > MAX_FEED_EVENTS) feed.splice(0, feed.length - MAX_FEED_EVENTS);
    this.version++;
    return true;
  }

  getFeed(taskCallId: string): SubAgentEvent[] {
    return this.feeds.get(taskCallId) ?? [];
  }

  /** 该 task 是否已返回结果（或整个 run 已结束） */
  isTaskClosed(taskCallId: string): boolean {
    return this.closedTaskCallIds.has(taskCallId);
  }

  /**
   * run 结束（正常完成/停止/出错）时调用：流都没了，不可能还有子智能体
   * 在跑。兜底工具结果消息丢失/未匹配的场景，让「执行中」必然收敛。
   */
  closeAllTasks(): void {
    for (const id of this.seenTaskCallIds) this.closedTaskCallIds.add(id);
    this.openTaskCallIds = [];
  }
}

function findLastIndex<T>(arr: T[], pred: (item: T) => boolean): number {
  for (let i = arr.length - 1; i >= 0; i--) {
    if (pred(arr[i])) return i;
  }
  return -1;
}
