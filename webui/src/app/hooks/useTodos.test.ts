/**
 * 任务清单解析单测（useTodos.ts）。
 *
 * 每条用例对应一种真实的参数形态：历史消息里的对象参数、流式增量里的 JSON
 * 字符串、以及"最后一次调用还在流式"时的回退。这条链路此前是空的
 * （useChat 恒返回 todos: []），所以没有历史数据可依赖，只能靠这些用例兜住。
 */
import { describe, expect, it } from "vitest";
import type { Message } from "@langchain/langgraph-sdk";
import { latestTodos, parseTodos } from "./useTodos";

function aiWithToolCall(name: string, args: unknown): Message {
  return { type: "ai", id: `m-${name}-${Math.random()}`, content: "", tool_calls: [{ name, args }] } as unknown as Message;
}

describe("parseTodos", () => {
  it("解析对象参数（历史消息形态）", () => {
    const todos = parseTodos({
      todos: [
        { content: "读需求文档", status: "completed" },
        { content: "写用例", status: "in_progress" },
        { content: "自检", status: "pending" },
      ],
    });
    expect(todos?.map((t) => t.status)).toEqual(["completed", "in_progress", "pending"]);
    expect(todos?.[0].content).toBe("读需求文档");
    expect(todos?.[1].id).toBe("todo-1");
  });

  it("解析 JSON 字符串参数（流式增量形态）", () => {
    const todos = parseTodos('{"todos":[{"content":"A","status":"pending"}]}');
    expect(todos).toEqual([{ id: "todo-0", content: "A", status: "pending" }]);
  });

  it("参数不完整（流式截断）返回 null 而不是空列表", () => {
    expect(parseTodos('{"todos":[{"content":"A","stat')).toBeNull();
  });

  it("结构不对返回 null", () => {
    expect(parseTodos(undefined)).toBeNull();
    expect(parseTodos({})).toBeNull();
    expect(parseTodos({ todos: "not-a-list" })).toBeNull();
  });

  it("丢弃非法条目，保留合法条目（id 用原下标，保证列表重算时不错位）", () => {
    const todos = parseTodos({
      todos: [
        { content: "", status: "pending" },          // 空内容
        { content: "缺状态" },                        // 缺 status
        { content: "未知状态", status: "doing" },     // 非法 status
        { content: "合法", status: "completed" },
      ],
    });
    expect(todos).toEqual([{ id: "todo-3", content: "合法", status: "completed" }]);
  });

  it("空清单是合法的（模型清空计划）", () => {
    expect(parseTodos({ todos: [] })).toEqual([]);
  });
});

describe("latestTodos", () => {
  it("没有消息 / 没有 write_todos 时是空列表", () => {
    expect(latestTodos(null)).toEqual([]);
    expect(latestTodos([])).toEqual([]);
    expect(latestTodos([aiWithToolCall("read_file", { path: "/a" })])).toEqual([]);
  });

  it("取最后一次 write_todos（整份覆盖，不是增量）", () => {
    const messages = [
      aiWithToolCall("write_todos", { todos: [{ content: "旧", status: "pending" }] }),
      aiWithToolCall("read_file", { path: "/a" }),
      aiWithToolCall("write_todos", { todos: [{ content: "新", status: "completed" }] }),
    ];
    expect(latestTodos(messages)).toEqual([{ id: "todo-0", content: "新", status: "completed" }]);
  });

  it("最后一次参数还在流式时回退到上一版完整清单", () => {
    const messages = [
      aiWithToolCall("write_todos", { todos: [{ content: "完整", status: "in_progress" }] }),
      aiWithToolCall("write_todos", '{"todos":[{"content":"半'),
    ];
    expect(latestTodos(messages)?.[0].content).toBe("完整");
  });
});
