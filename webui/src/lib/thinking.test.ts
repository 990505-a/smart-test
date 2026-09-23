import { describe, expect, it } from "vitest";

import {
  THINK_BODY_MAX_CHARS,
  THINK_BODY_MAX_LINES,
  thinkingBody,
  thinkingOmittedNote,
  thinkingSummary,
} from "./thinking";

/** 造一段像真实 reasoning 的文本：短行、行数很多（实测一条就是 9.5 万行）。 */
function fakeReasoning(lines: number, lineLen = 80): string {
  return Array.from({ length: lines }, (_, i) =>
    `${i}: `.padEnd(lineLen, "x"),
  ).join("\n");
}

describe("thinkingSummary", () => {
  it("还在一行行吐的时候给最新一行", () => {
    expect(thinkingSummary("第一行\n第二行\n正在权衡", true)).toBe("正在权衡");
  });

  it("结束后给第一行（和折叠时看到的那句一致）", () => {
    expect(thinkingSummary("\n\n先看现场\n再下结论", false)).toBe("先看现场");
  });

  it("空文本给空串（不炸）", () => {
    expect(thinkingSummary("", true)).toBe("");
    expect(thinkingSummary("   \n  ", false)).toBe("");
  });

  it("43 万字符也不用整串 split —— 只看窗口内的行", () => {
    const huge = fakeReasoning(96_000);
    expect(thinkingSummary(huge, false)).toBe("0: ".padEnd(80, "x"));
    expect(thinkingSummary(huge, true)).toBe("95999: ".padEnd(80, "x"));
  });
});

describe("thinkingBody", () => {
  it("短文本原样返回，不截", () => {
    const info = thinkingBody("看现场\n下结论");
    expect(info.body).toBe("看现场\n下结论");
    expect(info.omittedLines).toBe(0);
    expect(info.omittedChars).toBe(0);
    expect(thinkingOmittedNote(info)).toBe("");
  });

  it("超长文本只留尾部，且从整行开始", () => {
    const huge = fakeReasoning(96_000);
    const info = thinkingBody(huge);

    expect(info.body.length).toBeLessThanOrEqual(THINK_BODY_MAX_CHARS);
    expect(info.omittedChars).toBeGreaterThan(0);
    expect(info.omittedLines).toBeGreaterThan(0);
    // 尾部就是真正的结尾（最后一行必须在）
    expect(info.body.endsWith("95999: ".padEnd(80, "x"))).toBe(true);
    // 不留半行：body 的首行是完整的一行
    expect(info.body.startsWith(fakeReasoning(96_000).split("\n")[info.omittedLines])).toBe(true);
  });

  it("行数预算先生效时，行数不超过上限（哪怕每行很短）", () => {
    const many = fakeReasoning(50_000, 4);     // 每行 4 字符：字符预算吃不完
    const info = thinkingBody(many);
    const rendered = info.body.split("\n").length;

    expect(rendered).toBeLessThanOrEqual(THINK_BODY_MAX_LINES + 1);
    expect(info.omittedLines).toBeGreaterThan(0);
  });

  it("整段一行也不怕（没有换行可对齐）", () => {
    const oneLine = "x".repeat(200_000);
    const info = thinkingBody(oneLine);

    expect(info.body.length).toBeLessThanOrEqual(THINK_BODY_MAX_CHARS + 1);
    expect(info.body.endsWith("x")).toBe(true);
  });

  it("说明里带上省略了多少（给用户一个「这段被截了」的明确信号）", () => {
    const note = thinkingOmittedNote(thinkingBody(fakeReasoning(96_000)));
    expect(note).toContain("省略");
    expect(note).toContain("行");
  });
});
