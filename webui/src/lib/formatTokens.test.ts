/**
 * pickLatestContextUsage 单元测试：会话 token 显示改为「最后一次模型调用」
 * 而非全部累加（2026-09-22 修复：长会话累加虚高到 460 万）。
 */
import { describe, expect, it } from "vitest";
import { formatTokenCount, pickLatestContextUsage } from "./formatTokens";

const msg = (type: string, usage?: Record<string, number>) => ({
  type,
  usage_metadata: usage ?? undefined,
});

describe("pickLatestContextUsage", () => {
  it("取最后一条带 usage 的 AI 消息，而不是累加", () => {
    const usage = pickLatestContextUsage([
      msg("human"),
      msg("ai", { input_tokens: 1000, output_tokens: 500, total_tokens: 1500 }),
      msg("human"),
      msg("ai", { input_tokens: 5000, output_tokens: 800, total_tokens: 5800 }),
    ]);
    expect(usage).toEqual({ used: 5800, input: 5000, output: 800 });
  });

  it("最后一条 AI 还在流式（无 usage）时退回上一条已完成的", () => {
    const usage = pickLatestContextUsage([
      msg("ai", { input_tokens: 1000, output_tokens: 500, total_tokens: 1500 }),
      msg("human"),
      msg("ai"), // 正在生成
    ]);
    expect(usage?.used).toBe(1500);
  });

  it("忽略 tool / human 消息上可能带的 usage", () => {
    expect(pickLatestContextUsage([
      msg("ai", { input_tokens: 10, output_tokens: 5, total_tokens: 15 }),
      msg("tool", { total_tokens: 999999 }),
    ])?.used).toBe(15);
  });

  it("全都没有 usage 时返回 null", () => {
    expect(pickLatestContextUsage([msg("human"), msg("ai")])).toBeNull();
    expect(pickLatestContextUsage([])).toBeNull();
  });

  it("total_tokens 缺失时用 input+output 兜底；零值跳过", () => {
    expect(pickLatestContextUsage([
      msg("ai", { input_tokens: 0, output_tokens: 0, total_tokens: 0 }),
      msg("ai", { input_tokens: 300, output_tokens: 100 }),
    ])?.used).toBe(400);
  });
});

describe("formatTokenCount", () => {
  it("20369 → 20.4k；剪掉 .0", () => {
    expect(formatTokenCount(20369)).toBe("20.4k");
    expect(formatTokenCount(12000)).toBe("12k");
    expect(formatTokenCount(15)).toBe("15");
    expect(formatTokenCount(0)).toBe("0");
  });
});
