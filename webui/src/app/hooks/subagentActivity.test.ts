/**
 * SubAgentActivityStore 归属逻辑测试。
 *
 * 场景来自 2026-08-31 对 langgraph-api 0.13 + deepagents 0.7.9 的真实抓包：
 * - tasks 事件不再携带 tool_call id（旧协议有），pregel→call 映射只能靠
 *   「子图根 pregel id 首次出现时配给最早的未配对开放 task」启发式；
 * - 子图消息 ns 形如 `tools:<pregel>|model:<uuid>`，根工具结果 ns 为
 *   `tools:<pregel>`（任务结束时才到，是权威映射的补充来源）。
 */

import { describe, expect, it } from "vitest";

import { SubAgentActivityStore } from "./subagentActivity";

function meta(store: SubAgentActivityStore, msgId: string, ns: string) {
  store.noteMetadata({ [msgId]: { metadata: { langgraph_checkpoint_ns: ns } } });
}

describe("SubAgentActivityStore 子图归属", () => {
  it("单个子代理:子图消息应归入该 task 的 feed 而非孤儿桶", () => {
    const store = new SubAgentActivityStore();
    // 根 ai 消息派发 task
    meta(store, "root-ai", "model:2c091ff4");
    expect(
      store.consume({
        id: "root-ai", type: "ai", content: "",
        tool_calls: [{ id: "call_TASK1", name: "task", args: { description: "读 README" } }],
      }),
    ).toBe(false); // 根消息照常进主流程

    // 子代理 ai 消息(嵌套 ns)带工具调用
    meta(store, "sub-ai-1", "tools:904a6d76|model:5af6899c");
    const swallowed = store.consume({
      id: "sub-ai-1", type: "ai", content: "开始分析",
      tool_calls: [{ id: "call_read1", name: "read_file", args: { file_path: "/repo/README.md" } }],
    });
    expect(swallowed).toBe(true);

    const feed = store.getFeed("call_TASK1");
    expect(feed.some((e) => e.kind === "tool" && e.name === "read_file")).toBe(true);
    expect(feed.some((e) => e.kind === "text")).toBe(true);

    // 子代理工具结果也归同一 feed
    meta(store, "sub-tool-1", "tools:904a6d76|tools:94a7ce8f");
    store.consume({ id: "sub-tool-1", type: "tool", tool_call_id: "call_read1", name: "read_file", content: "# 项目说明" });
    const after = store.getFeed("call_TASK1");
    expect(after.filter((e) => e.kind === "tool" && e.status === "done").length).toBe(1);
  });

  it("并行子代理:两个子图根按派发顺序配对,互不串扰", () => {
    const store = new SubAgentActivityStore();
    meta(store, "root-ai", "model:2c091ff4");
    store.consume({
      id: "root-ai", type: "ai", content: "",
      tool_calls: [
        { id: "call_A", name: "task", args: { description: "任务A" } },
        { id: "call_B", name: "task", args: { description: "任务B" } },
      ],
    });

    // 子图根按 A、B 顺序出现
    meta(store, "sub-a-1", "tools:pregelA|model:m1");
    store.consume({ id: "sub-a-1", type: "ai", content: "", tool_calls: [{ id: "t_a1", name: "grep", args: {} }] });
    meta(store, "sub-b-1", "tools:pregelB|model:m2");
    store.consume({ id: "sub-b-1", type: "ai", content: "", tool_calls: [{ id: "t_b1", name: "ls", args: {} }] });

    expect(store.getFeed("call_A").some((e) => e.name === "grep")).toBe(true);
    expect(store.getFeed("call_B").some((e) => e.name === "ls")).toBe(true);
    expect(store.getFeed("call_A").some((e) => e.name === "ls")).toBe(false);
    expect(store.getFeed("call_B").some((e) => e.name === "grep")).toBe(false);
  });

  it("task 结束后收敛:根工具结果触发 closed,面板可判定完成", () => {
    const store = new SubAgentActivityStore();
    meta(store, "root-ai", "model:m0");
    store.consume({
      id: "root-ai", type: "ai", content: "",
      tool_calls: [{ id: "call_T", name: "task", args: {} }],
    });
    meta(store, "sub-1", "tools:pregelT|model:m1");
    store.consume({ id: "sub-1", type: "ai", content: "done" });

    // 根级 task 工具结果(ns 为 tools:pregelT)→ 权威映射 + 关闭
    meta(store, "root-tool", "tools:pregelT");
    store.consume({ id: "root-tool", type: "tool", tool_call_id: "call_T", name: "task", content: "分析完成" });
    expect(store.isTaskClosed("call_T")).toBe(true);
  });
});
