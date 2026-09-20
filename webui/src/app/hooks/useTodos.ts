"use client";

import { useMemo } from "react";
import type { Message } from "@langchain/langgraph-sdk";
import type { TodoItem } from "@/app/types/types";

/**
 * 会话最新的任务清单（`write_todos` 工具写的那份）。
 *
 * 为什么从消息里取而不是读 LangGraph state：`write_todos` 每次调用都把**整份**
 * 清单写进工具参数，所以最后一次调用的参数就是当前状态——不需要为一个面板多开
 * 一个 stream mode（`values`/`updates` 会把整份 state 推给浏览器），而消息本来就
 * 落库了，刷新页面重放历史同样能还原出清单。
 */

/**
 * 解析一次 `write_todos` 调用的参数。
 *
 * 参数形态有两种：历史消息里是对象（`{todos: [...]}`），流式增量里可能是 JSON
 * 字符串，两种都认。结构不完整（还在流式）时返回 null，由调用方继续往前找。
 */
export function parseTodos(raw: unknown): TodoItem[] | null {
  let value: unknown = raw;
  if (typeof value === "string") {
    try {
      value = JSON.parse(value);
    } catch {
      return null;
    }
  }
  if (!value || typeof value !== "object") return null;

  const list = (value as { todos?: unknown }).todos;
  if (!Array.isArray(list)) return null;

  const items: TodoItem[] = [];
  list.forEach((entry, index) => {
    if (!entry || typeof entry !== "object") return;
    const { content, status } = entry as { content?: unknown; status?: unknown };
    if (typeof content !== "string" || !content) return;
    if (status !== "pending" && status !== "in_progress" && status !== "completed") return;
    // 确定性 id：随机 id 会让列表每次重算都重挂载
    items.push({ id: `todo-${index}`, content, status });
  });
  return items;
}

/**
 * 从后往前找最近一次可用的 `write_todos`。
 *
 * 最近一次调用若还在流式（参数不完整）就继续往前找：宁可显示上一版完整清单，
 * 也不要闪成空列表。
 */
export function latestTodos(messages: Message[] | null | undefined): TodoItem[] {
  if (!messages?.length) return [];
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const calls = (messages[i] as { tool_calls?: unknown }).tool_calls;
    if (!Array.isArray(calls)) continue;
    for (let j = calls.length - 1; j >= 0; j -= 1) {
      const call = calls[j] as { name?: string; args?: unknown } | null;
      if (call?.name !== "write_todos") continue;
      const parsed = parseTodos(call.args);
      if (parsed) return parsed;
    }
  }
  return [];
}

export function useTodos(messages: Message[] | null | undefined): TodoItem[] {
  return useMemo(() => latestTodos(messages), [messages]);
}
