import { describe, expect, it } from "vitest";

import {
  STALL_HINT_MS,
  contentLength,
  countRunSteps,
  formatElapsed,
  isStalled,
  progressFingerprint,
  runHud,
} from "./runProgress";

describe("formatElapsed", () => {
  it("按秒/分/时给最短可读写法", () => {
    expect(formatElapsed(0)).toBe("0s");
    expect(formatElapsed(42_000)).toBe("42s");
    expect(formatElapsed(192_000)).toBe("3m12s");
    expect(formatElapsed(3_720_000)).toBe("1h02m");
  });

  it("负数与非法值不炸", () => {
    expect(formatElapsed(-5)).toBe("0s");
  });
});

describe("countRunSteps", () => {
  const human = { type: "human", content: "跑一下新手流程" };

  it("只数最后一条 human 之后的 ai 消息", () => {
    const messages = [
      { type: "human", content: "旧的" },
      { type: "ai", content: "旧回复" },
      human,
      { type: "ai", content: "开始" },
      { type: "tool", content: "{}" },
      { type: "ai", content: "继续" },
    ];
    expect(countRunSteps(messages)).toBe(2);
  });

  it("没有 human 时从头数（刷新后接上流的情况）", () => {
    expect(countRunSteps([{ type: "ai", content: "a" }, { type: "tool", content: "t" }])).toBe(1);
  });

  it("空列表是 0", () => {
    expect(countRunSteps([])).toBe(0);
  });
});

describe("progressFingerprint", () => {
  it("文本变长 / 多一条消息 / 多一个工具调用都会变（= 还在动）", () => {
    const base = [{ type: "ai", content: "abc" }];
    expect(progressFingerprint(base)).not.toBe(progressFingerprint([{ type: "ai", content: "abcd" }]));
    expect(progressFingerprint(base)).not.toBe(progressFingerprint([...base, { type: "tool", content: "t" }]));
    expect(progressFingerprint(base)).not.toBe(
      progressFingerprint([{ type: "ai", content: "abc", tool_calls: [{ name: "x" }] }]),
    );
  });

  it("一模一样的内容指纹相同（没有新东西）", () => {
    expect(progressFingerprint([{ type: "ai", content: "abc" }]))
      .toBe(progressFingerprint([{ type: "ai", content: "abc" }]));
  });

  it("数组形式的内容也能数（Anthropic 块）", () => {
    expect(contentLength({ content: [{ text: "hello" }, { text: "!" }] })).toBe(6);
  });
});

describe("isStalled", () => {
  it("默认 90s 才算静默", () => {
    expect(STALL_HINT_MS).toBe(90_000);
    expect(isStalled(89_999)).toBe(false);
    expect(isStalled(90_000)).toBe(true);
  });
});

describe("runHud", () => {
  it("正常推进：只报时长与步数，不给提示", () => {
    const hud = runHud({ elapsedMs: 192_000, silentMs: 2_000, steps: 12 });
    expect(hud.stalled).toBe(false);
    expect(hud.text).toBe("运行中 · 已 3m12s · 第 12 步");
    expect(hud.hint).toBe("");
  });

  it("还没有步数时不显示「第 0 步」", () => {
    expect(runHud({ elapsedMs: 1_000, silentMs: 0, steps: 0 }).text).toBe("运行中 · 已 1s");
  });

  it("静默超阈值：如实说出来，并告诉人可以等也可以停", () => {
    const hud = runHud({ elapsedMs: 303_000, silentMs: 95_000, steps: 7 });
    expect(hud.stalled).toBe(true);
    expect(hud.text).toContain("已 1m35s 没有新事件");
    expect(hud.hint).toContain("停止");
  });

  it("阈值可覆盖（测试与将来调参用）", () => {
    expect(runHud({ elapsedMs: 5_000, silentMs: 31_000, steps: 1, thresholdMs: 30_000 }).stalled)
      .toBe(true);
  });
});
