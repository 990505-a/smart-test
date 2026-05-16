"use client";

import React, { useState, useRef, useCallback, useEffect, useMemo, FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { ArrowUp, Square, Plus } from "lucide-react";
import { ChatMessage } from "@/app/components/ChatMessage";
import { useChatContext } from "@/providers/ChatProvider";
import { cn } from "@/lib/utils";
import { useStickToBottom } from "use-stick-to-bottom";
import { useFileUpload } from "@/app/hooks/useFileUpload";
import { ContentBlocksPreview } from "@/app/components/ContentBlocksPreview";
import type { ToolCall } from "@/app/types/types";
import type { Message } from "@langchain/langgraph-sdk";

interface ChatInterfaceProps {
  assistantId: string;
}

export const ChatInterface = React.memo<ChatInterfaceProps>(({ assistantId }) => {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const [input, setInput] = useState("");
  const { scrollRef, contentRef } = useStickToBottom();

  const {
    contentBlocks,
    handleFileUpload,
    dropRef,
    removeContentBlock,
    clearContentBlocks,
    isDragging,
    handlePaste,
  } = useFileUpload();

  const {
    messages,
    isLoading,
    sendMessage,
    stopStream,
  } = useChatContext();

  const submitDisabled = isLoading || !assistantId;

  const handleSubmit = useCallback(
    (e?: FormEvent) => {
      if (e) {
        e.preventDefault();
      }
      const messageText = input.trim();
      if (
        (!messageText && contentBlocks.length === 0) ||
        isLoading ||
        submitDisabled
      )
        return;
      sendMessage(messageText, contentBlocks);
      setInput("");
      clearContentBlocks();
    },
    [input, contentBlocks, isLoading, sendMessage, submitDisabled, clearContentBlocks],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (submitDisabled) return;
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit, submitDisabled],
  );

  // Extract tool calls from messages, matching classroom's processedMessages pattern
  const processedMessages = useMemo(() => {
    if (!messages) return [];
    const messageMap = new Map<
      string,
      { message: Message; toolCalls: ToolCall[] }
    >();

    messages.forEach((message: Message) => {
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
          toolCallsInMessage.push(...(toolUseBlocks as any[]));
        }

        const toolCallsWithStatus = toolCallsInMessage.map(
          (tc): ToolCall => {
            const name =
              tc.function?.name || tc.name || tc.type || "unknown";
            const args =
              tc.function?.arguments || tc.args || tc.input || {};
            return {
              id: tc.id || `tool-${Math.random()}`,
              name,
              args: typeof args === "object" && args !== null ? args as Record<string, unknown> : {},
              status: "pending" as const,
            };
          },
        );

        messageMap.set(message.id!, { message, toolCalls: toolCallsWithStatus });
      } else if (message.type === "tool") {
        const toolCallId = (message as any).tool_call_id;
        if (!toolCallId) return;
        for (const [, data] of Array.from(messageMap.entries())) {
          const idx = data.toolCalls.findIndex((tc) => tc.id === toolCallId);
          if (idx === -1) continue;
          const content =
            typeof message.content === "string"
              ? message.content
              : Array.isArray(message.content)
                ? message.content
                    .map((b: any) =>
                      typeof b === "string" ? b : b.text ?? "",
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
        messageMap.set(message.id!, { message, toolCalls: [] });
      }
    });

    return Array.from(messageMap.values());
  }, [messages]);

  // Auto-scroll to bottom when new messages arrive
  const lastMessageId = messages?.at(-1)?.id;

  useEffect(() => {
    const scrollElement = scrollRef.current;
    if (!scrollElement) return;

    const frameId = window.requestAnimationFrame(() => {
      scrollElement.scrollTo({
        top: scrollElement.scrollHeight,
        behavior: isLoading ? "auto" : "smooth",
      });
    });

    return () => window.cancelAnimationFrame(frameId);
  }, [lastMessageId, messages?.length, isLoading, scrollRef]);

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Message list area */}
      <div
        className="flex-1 overflow-y-auto overflow-x-hidden overscroll-contain"
        ref={scrollRef}
      >
        <div
          className="mx-auto w-full max-w-[1024px] px-6 pb-6 pt-4"
          ref={contentRef}
        >
          {processedMessages.length > 0 ? (
            processedMessages.map((data, index) => {
              const isLastMessage = index === processedMessages.length - 1;
              return (
                <ChatMessage
                  key={data.message.id ?? `msg-${index}`}
                  message={data.message}
                  toolCalls={data.toolCalls}
                  isStreaming={isLastMessage && isLoading}
                />
              );
            })
          ) : (
            <div className="flex flex-col items-center justify-center p-8">
              <p className="text-lg font-medium text-muted-foreground">
                智能测试平台
              </p>
              <p className="mt-2 text-sm text-muted-foreground">
                输入消息开始对话
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Input area */}
      <div className="flex-shrink-0 bg-background">
        <div
          ref={dropRef}
          className={cn(
            "mx-4 mb-6 flex flex-shrink-0 flex-col overflow-hidden rounded-xl border border-border bg-background",
            "mx-auto w-[calc(100%-32px)] max-w-[1024px] transition-colors duration-200 ease-in-out",
            isDragging && "border-primary border-2 border-dotted",
          )}
        >
          <form onSubmit={handleSubmit} className="flex flex-col">
            <ContentBlocksPreview
              blocks={contentBlocks}
              onRemove={removeContentBlock}
            />
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              onPaste={handlePaste}
              placeholder={isLoading ? "运行中..." : "输入您的消息..."}
              className="flex-1 resize-none border-0 bg-transparent px-[18px] pb-[13px] pt-[14px] text-sm leading-7 text-foreground outline-none placeholder:text-muted-foreground"
              rows={1}
            />
            <div className="flex justify-between gap-2 p-3">
              <div className="flex items-center gap-4">
                <label
                  htmlFor="file-input"
                  className="flex cursor-pointer items-center gap-2 text-muted-foreground hover:text-foreground"
                >
                  <Plus className="size-5" />
                  <span className="text-sm">上传 PDF 或图片</span>
                </label>
                <input
                  id="file-input"
                  type="file"
                  onChange={handleFileUpload}
                  multiple
                  accept="image/jpeg,image/png,image/gif,image/webp,application/pdf"
                  className="hidden"
                />
              </div>
              <div className="flex justify-end gap-2">
                <Button
                  type={isLoading ? "button" : "submit"}
                  variant={isLoading ? "destructive" : "default"}
                  onClick={isLoading ? stopStream : handleSubmit}
                  disabled={
                    !isLoading &&
                    (submitDisabled ||
                      (!input.trim() && contentBlocks.length === 0))
                  }
                >
                  {isLoading ? (
                    <>
                      <Square size={14} />
                      <span>停止</span>
                    </>
                  ) : (
                    <>
                      <ArrowUp size={18} />
                      <span>发送</span>
                    </>
                  )}
                </Button>
              </div>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
});

ChatInterface.displayName = "ChatInterface";
