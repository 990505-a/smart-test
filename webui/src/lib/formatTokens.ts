/** Format a token count for the chat UI: 20369 → "20.4k", 15 → "15". */
export function formatTokenCount(n: number | null | undefined): string {
  if (!n || n < 0) return "0";
  if (n < 1000) return String(n);
  const k = n / 1000;
  // 保留一位小数，但剪掉 ".0"：12300 → "12.3k"，12000 → "12k"
  const rounded = Math.round(k * 10) / 10;
  return `${rounded % 1 === 0 ? rounded.toFixed(0) : rounded.toFixed(1)}k`;
}

/** langchain usage_metadata 的最小形状（见 ChatMessage 的类型注释）。 */
export interface UsageLike {
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
  input_token_details?: Record<string, unknown>;
}

export interface ContextUsage {
  /** 当前上下文水位 ≈ 最后一次模型调用的 total_tokens。 */
  used: number;
  input: number;
  output: number;
}

/**
 * 取**最后一次模型调用**的 token 用量作为当前上下文水位。
 *
 * 为什么取最后一条而不是累加：每轮 input 都会把全部历史重发给模型，
 * 把各条 AI 回复的 total_tokens 加起来会把历史重复计成数倍（实测长会话
 * 累出 460 万）；而最后一条的 input 就是当前完整对话，total ≈ 真实水位，
 * 与后端 SummarizationMiddleware 的 85% 压缩触发点同口径。
 *
 * 从后往前找**带 usage 的** AI 消息：流式最后一块才带 usage，正在生成的
 * 回合可能还没有——此时退回上一条已完成回合的值，落定后自动更新。
 */
export function pickLatestContextUsage(
  messages: Array<{ type?: string; usage_metadata?: UsageLike | null }>,
): ContextUsage | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (!m || m.type !== "ai") continue;
    const u = m.usage_metadata;
    if (!u) continue;
    const input = u.input_tokens ?? 0;
    const output = u.output_tokens ?? 0;
    const used =
      typeof u.total_tokens === "number" ? u.total_tokens : input + output;
    if (used > 0) return { used, input, output };
  }
  return null;
}