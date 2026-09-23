/**
 * 思考（reasoning_content）文本的**渲染预算**。
 *
 * 为什么要专门管这件事：DeepSeek 这类模型的 reasoning 是逐 token 吐出来的，
 * 一串长思考可以到 **43.5 万字符 / 9.5 万行**（2026-09-23 实测：会话 01a0cd2b
 * 一条消息的 `additional_kwargs.reasoning_content`）。展开时把整段塞进一个
 * `<p whitespace-pre-wrap break-words>`，浏览器要为每一行建行盒 —— 点一下
 * 就是几万次布局，页面直接像卡死。折叠状态下同样不能整串 `split("\n")` 求
 * 首尾行：那是每次流式刷帧都要建 9.5 万个字符串。
 *
 * 所以两条都只处理**窗口**：摘要看首/尾 4 千字符，正文从尾部按"行数 + 字符数"
 * 双预算截取（思考是越往后越接近结论，尾部信息量最大）。
 */

/** 摘要只看这么大一段：够取到一行完整的判断，又不至于整串扫 */
const SUMMARY_WINDOW = 4000;

/** 正文的行数 / 字符数上限（两个谁先到算谁）。1500 行 ≈ 一屏多，足够人看 */
export const THINK_BODY_MAX_LINES = 1500;
export const THINK_BODY_MAX_CHARS = 60_000;

/** 头部那一行摘要：还在思考时给"最新一行"，结束后给"第一行"。 */
export function thinkingSummary(text: string, running: boolean): string {
  if (!text) return "";
  if (!running) {
    const head = text.slice(0, SUMMARY_WINDOW);
    const line = head.split("\n").find((l) => l.trim());
    return (line ?? "").trim();
  }
  const tail = text.slice(-SUMMARY_WINDOW);
  const lines = tail.split("\n");
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    if (lines[i].trim()) return lines[i].trim();
  }
  return "";
}

export interface ThinkingBody {
  /** 真正放进 DOM 的那段（截断时是尾部） */
  body: string;
  /** 被省略掉的行数 / 字符数（0 = 没截） */
  omittedLines: number;
  omittedChars: number;
}

function countNewlines(text: string, from: number, to: number): number {
  let n = 0;
  for (let i = from; i < to; i += 1) {
    if (text.charCodeAt(i) === 10) n += 1;
  }
  return n;
}

/** 从尾部截出可渲染的一段：先按字符预算粗切，再对齐行首、按行数预算修剪。 */
export function thinkingBody(text: string): ThinkingBody {
  if (!text) return { body: "", omittedLines: 0, omittedChars: 0 };
  const len = text.length;
  let start = len;
  let chars = 0;
  let lines = 0;
  // 从尾部往前扫（单次遍历、不 split）：两个预算谁先到就停
  while (start > 0) {
    if (chars >= THINK_BODY_MAX_CHARS || lines >= THINK_BODY_MAX_LINES) break;
    start -= 1;
    chars += 1;
    if (text.charCodeAt(start) === 10) lines += 1;
  }
  if (start === 0) return { body: text, omittedLines: 0, omittedChars: 0 };
  // 别从半行开始：往前找到下一个换行再切。整段没有换行（一个超长行）时
  // indexOf 会给 -1，这时**保持窗口原样** —— 早先写成"一直往后找到换行为止"，
  // 结果那种文本会被推到末尾、正文变成空串。
  const boundary = text.indexOf("\n", start);
  const aligned = boundary >= 0 ? boundary + 1 : start;
  if (aligned < len) start = aligned;
  return {
    body: text.slice(start),
    omittedLines: countNewlines(text, 0, start),
    omittedChars: start,
  };
}

/** 截断说明那一行（没截就给空串）。 */
export function thinkingOmittedNote(info: ThinkingBody): string {
  if (!info.omittedLines && !info.omittedChars) return "";
  const lines = info.omittedLines.toLocaleString("zh-CN");
  const chars = info.omittedChars.toLocaleString("zh-CN");
  return `前面省略了 ${lines} 行（${chars} 字符）—— 思考太长，只渲染最后一段；完整内容在会话记录里`;
}
