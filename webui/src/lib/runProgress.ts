/**
 * 「这一轮跑到哪了」的纯计算 —— 给聊天页顶部的运行状态条用。
 *
 * 为什么要有它：以前这一轮跑多久、跑到第几步，界面上没有任何地方说得清，于是
 * 「跑了 35 分钟、前端一片安静」只能靠一个**计数上限**（模型调用 120 次就硬收尾）
 * 来兜——那个闸误伤太狠（一次长探索轻松过 120），而且收尾文案是一句英文的
 * "Model call limits exceeded"，看着像报错。
 *
 * 现在换成看得见的做法：运行中显示「已 X 分钟 · 第 N 步」，静默超过 90s 明确提示
 * 「没有新事件」并让人自己决定等还是停。**看得见 + 随时能停**，比按次数一刀切准，
 * 也不会把正常的长任务砍掉。
 */

/** 静默多久算「可能卡住了」（只是提示，不替用户做决定）。 */
export const STALL_HINT_MS = 90_000;

type AnyMessage = {
  type?: string;
  role?: string;
  content?: unknown;
  tool_calls?: unknown[];
  toolCalls?: unknown[];
};

/** 调用方传进来的消息形状不可控（LangGraph 的 Message / 分页 API 的行 / 流式片段），
 *  这里只做"能读就读"的收窄，不做校验 —— 状态条不该因为一条消息长得怪就崩。 */
function asMsg(value: unknown): AnyMessage {
  return value && typeof value === "object" ? (value as AnyMessage) : {};
}

function kindOf(msg: AnyMessage | undefined | null): string {
  if (!msg) return "";
  return String(msg.type ?? msg.role ?? "").toLowerCase();
}

/** 是不是「模型说话」那条（human/user 之外的都可能在推进，但步数只数 ai）。 */
function isAi(msg: AnyMessage | undefined | null): boolean {
  const k = kindOf(msg);
  return k === "ai" || k === "assistant";
}

function isHuman(msg: AnyMessage | undefined | null): boolean {
  const k = kindOf(msg);
  return k === "human" || k === "user";
}

/** 内容长度（用来判断「有没有新东西」——流式文本增长也算推进）。 */
export function contentLength(msg: unknown): number {
  const c = asMsg(msg).content;
  if (typeof c === "string") return c.length;
  if (Array.isArray(c)) {
    return c.reduce((n, part) => {
      if (typeof part === "string") return n + part.length;
      if (part && typeof part === "object" && "text" in part) {
        return n + String((part as { text?: unknown }).text ?? "").length;
      }
      return n;
    }, 0);
  }
  return 0;
}

/** 这一轮（最后一条 human 之后）模型说了几次 —— 近似「第几步」。 */
export function countRunSteps(messages: readonly unknown[]): number {
  let start = -1;
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (isHuman(asMsg(messages[i]))) {
      start = i;
      break;
    }
  }
  let steps = 0;
  for (let i = start + 1; i < messages.length; i += 1) {
    if (isAi(asMsg(messages[i]))) steps += 1;
  }
  return steps;
}

/**
 * 「有没有新事件」的指纹：消息条数 + 最后一条的内容长度 + 工具调用数。
 * 流式文本每长一点、每冒出一次工具调用，指纹都会变 —— 用它可以判断"还在动"。
 */
export function progressFingerprint(messages: readonly unknown[]): string {
  const last = asMsg(messages[messages.length - 1]);
  const calls = last.tool_calls ?? last.toolCalls ?? [];
  return `${messages.length}:${contentLength(last)}:${Array.isArray(calls) ? calls.length : 0}`;
}

/** 时长 → 「42s」/「3m12s」/「1h02m」（运行状态条上够用就好，不做 i18n）。 */
export function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}h${String(m).padStart(2, "0")}m`;
  if (m > 0) return `${m}m${String(s).padStart(2, "0")}s`;
  return `${s}s`;
}

export function isStalled(silentMs: number, thresholdMs: number = STALL_HINT_MS): boolean {
  return silentMs >= thresholdMs;
}

export interface RunHudInput {
  /** 这一轮开始到现在。 */
  elapsedMs: number;
  /** 距上一次"有新东西"过去了多久。 */
  silentMs: number;
  steps: number;
  thresholdMs?: number;
}

export interface RunHud {
  text: string;
  stalled: boolean;
  /** 给 UI 的第二行提示（没卡住时为空串）。 */
  hint: string;
}

/** 状态条要显示什么（纯函数，前端只负责渲染）。 */
export function runHud(input: RunHudInput): RunHud {
  const threshold = input.thresholdMs ?? STALL_HINT_MS;
  const stalled = isStalled(input.silentMs, threshold);
  const steps = input.steps > 0 ? ` · 第 ${input.steps} 步` : "";
  if (!stalled) {
    return {
      text: `运行中 · 已 ${formatElapsed(input.elapsedMs)}${steps}`,
      stalled: false,
      hint: "",
    };
  }
  return {
    text: `运行中 · 已 ${formatElapsed(input.elapsedMs)}${steps}`
      + ` · 已 ${formatElapsed(input.silentMs)} 没有新事件`,
    stalled: true,
    hint: "可能在跑长工具或长模型请求 —— 可以继续等，也可以点「停止」",
  };
}
