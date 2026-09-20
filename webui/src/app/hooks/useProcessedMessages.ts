"use client";

import { useMemo } from "react";
import type { Message } from "@langchain/langgraph-sdk";
import type { ToolCall } from "@/app/types/types";

/** Stable empty tool-call array shared by all human messages (memo safety). */
export const EMPTY_TOOLCALLS: ToolCall[] = [];

/**
 * Fold a LangGraph message stream into renderable rows: each `ai` message with
 * its tool calls, each tool call carrying the status/result merged in from the
 * matching `tool` message.
 *
 * 从 ChatInterface 抽出来的：把消息与工具调用折叠成可渲染的列表。原先对话页与
 * 「代码图谱 → AI 分析」面板都要做同一件事（后者 2026-09 删除），而这里踩过的坑
 * （历史消息缺 tool_call_id、随机 id 会破坏 memo、流结束后 pending 要收敛成
 * completed）没必要在两个地方各踩一遍。
 */
export function useProcessedMessages(
  messages: Message[] | null | undefined,
  isLoading: boolean,
  subagentVersion?: number,
): { message: Message; toolCalls: ToolCall[] }[] {
  return useMemo(() => {
    if (!messages) return [];
    const messageMap = new Map<
      string,
      { message: Message; toolCalls: ToolCall[] }
    >();

    messages.forEach((message: Message) => {
      if (!message) return;
      if (message.type === "ai") {
        const toolCallsInMessage: Array<{
          id?: string;
          function?: { name?: string; arguments?: unknown };
          name?: string;
          type?: string;
          args?: unknown;
          input?: unknown;
        }> = [];

        if (
          message.additional_kwargs?.tool_calls &&
          Array.isArray(message.additional_kwargs.tool_calls)
        ) {
          toolCallsInMessage.push(...message.additional_kwargs.tool_calls);
        } else if (message.tool_calls && Array.isArray(message.tool_calls)) {
          toolCallsInMessage.push(
            ...message.tool_calls.filter(
              (tc: { name?: string }) => tc.name !== "",
            ),
          );
        } else if (Array.isArray(message.content)) {
          const toolUseBlocks = (message.content as Array<{ type?: string }>).filter(
            (block) => block.type === "tool_use",
          );
          toolCallsInMessage.push(...(toolUseBlocks as typeof toolCallsInMessage));
        }

        const toolCallsWithStatus = toolCallsInMessage.map(
          (tc, i): ToolCall => {
            const name =
              tc.function?.name || tc.name || tc.type || "unknown";
            const args =
              tc.function?.arguments || tc.args || tc.input || {};
            return {
              // Deterministic fallback id: random ids remount tool cards on
              // every recompute and break React reconciliation.
              id: tc.id || `tool-${name}-${i}`,
              name,
              args: typeof args === "object" && args !== null ? args as Record<string, unknown> : {},
              status: "pending" as const,
            };
          },
        );

        messageMap.set(message.id!, { message, toolCalls: toolCallsWithStatus });
      } else if (message.type === "tool") {
        // 历史消息从 SQLite 加载时 tool_call_id 曾并入 additional_kwargs 返回，两处都读
        const toolMsg = message as Message & { tool_call_id?: string };
        const toolCallId =
          toolMsg.tool_call_id ??
          (message.additional_kwargs as { tool_call_id?: string } | undefined)
            ?.tool_call_id;
        if (!toolCallId) return;
        for (const [, data] of Array.from(messageMap.entries())) {
          const idx = data.toolCalls.findIndex((tc) => tc.id === toolCallId);
          if (idx === -1) continue;
          const content =
            typeof message.content === "string"
              ? message.content
              : Array.isArray(message.content)
                ? message.content
                    .map((b) =>
                      typeof b === "string" ? b : (b as { text?: string }).text ?? "",
                    )
                    .join("")
                : "";
          data.toolCalls[idx] = {
            ...data.toolCalls[idx],
            status: "completed" as const,
            result: content,
          };
          break;
        }
      } else if (message.type === "human") {
        // Shared constant: a fresh [] literal per message would defeat
        // React.memo on ChatMessage for every historical message.
        messageMap.set(message.id!, { message, toolCalls: EMPTY_TOOLCALLS });
      }
    });

    // 流已结束（或纯历史查看）时，仍未等到结果的工具调用按已完成渲染：
    // 旧数据缺少 tool_call_id 时结果永远匹配不上，子智能体会一直转「执行中」
    if (!isLoading) {
      for (const [, data] of Array.from(messageMap.entries())) {
        // 跳过空数组：human 消息共享 EMPTY_TOOLCALLS，重新 map 会破坏 memo
        if (data.toolCalls.length === 0) continue;
        data.toolCalls = data.toolCalls.map((tc) =>
          tc.status === "pending" ? { ...tc, status: "completed" as const } : tc,
        );
      }
    }

    return Array.from(messageMap.values());
  }, [messages, isLoading, subagentVersion]);
}
