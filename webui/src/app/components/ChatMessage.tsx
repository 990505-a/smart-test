"use client";

import React, { useMemo, useState, useCallback } from "react";
import type { ContentBlock, ToolCall, SubAgent } from "@/app/types/types";
import { PIPELINE_STAGES } from "@/app/types/types";
import { cn } from "@/lib/utils";
import { File } from "lucide-react";
import { ToolResultCard, parseSaveResults, stripSaveResultMarkers } from "@/app/components/ToolResultCard";
import { ToolCallBox } from "@/app/components/ToolCallBox";
import { SubAgentIndicator } from "@/app/components/SubAgentIndicator";
import { MarkdownContent } from "@/app/components/MarkdownContent";

/** image_url block as sent to OpenAI-compatible APIs */
interface ImageUrlBlock {
  type: "image_url";
  image_url: { url: string };
}

function isImageUrlBlock(block: unknown): block is ImageUrlBlock {
  if (typeof block !== "object" || block === null || !("type" in block))
    return false;
  const b = block as { type: unknown; image_url?: unknown };
  return (
    b.type === "image_url" &&
    typeof b.image_url === "object" &&
    b.image_url !== null &&
    "url" in (b.image_url as object) &&
    typeof (b.image_url as { url: unknown }).url === "string"
  );
}

interface ChatMessageProps {
  message: {
    id?: string;
    type: string;
    name?: string;
    content: string | Array<Record<string, unknown>>;
    additional_kwargs?: Record<string, unknown>;
    tool_calls?: Array<{
      name: string;
      args?: Record<string, unknown>;
      id?: string;
    }>;
  };
  toolCalls?: ToolCall[];
  isStreaming?: boolean;
  ui?: unknown[];
  stream?: unknown;
  graphId?: string;
}

function extractStringContent(
  content: string | Array<Record<string, unknown>>,
): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map((block) => {
        if ("text" in block && typeof block.text === "string") return block.text;
        return "";
      })
      .join("");
  }
  return "";
}

export const ChatMessage = React.memo<ChatMessageProps>(
  ({ message, toolCalls = [], isStreaming = false, ui, stream, graphId }) => {
    const isUser = message.type === "human";
    const isAi = message.type === "ai";
    const isTool = message.type === "tool";
    const messageContent = extractStringContent(message.content);
    const hasContent = messageContent && messageContent.trim() !== "";
    const hasToolCalls = toolCalls.length > 0;
    const visibleToolCalls = toolCalls.filter((tc) => tc.name !== "task");

    // Extract sub-agents from "task" tool calls
    const subAgents = useMemo(() => {
      return toolCalls
        .filter((tc) => tc.name === "task" && tc.args.subagent_type && tc.args.subagent_type !== "")
        .map((tc): SubAgent => ({
          id: tc.id,
          name: tc.name,
          subAgentName: tc.args.subagent_type as string,
          input: tc.args,
          output: tc.result ? { result: tc.result } : undefined,
          status: tc.status === "completed" ? "completed" : tc.status === "error" ? "error" : "active",
        }));
    }, [toolCalls]);

    // Map UI components to tool call IDs for GenUI rendering
    const uiMap = useMemo(() => {
      if (!ui) return new Map<string, unknown>();
      const map = new Map<string, unknown>();
      for (const u of ui) {
        const meta = (u as Record<string, unknown>)?.metadata as Record<string, unknown> | undefined;
        if (meta?.tool_call_id) {
          map.set(meta.tool_call_id as string, u);
        }
      }
      return map;
    }, [ui]);

    // Images: image_url blocks in message.content
    const imageUrlBlocks = useMemo(() => {
      if (!Array.isArray(message.content)) return [];
      return (message.content as unknown[]).filter(isImageUrlBlock);
    }, [message.content]);

    // PDFs: in additional_kwargs.attachments
    const pdfBlocks = useMemo(() => {
      const rawAttachments = message.additional_kwargs?.attachments;
      if (!Array.isArray(rawAttachments)) return [];
      return (rawAttachments as ContentBlock[]).filter(
        (b) => b.type === "file",
      );
    }, [message.additional_kwargs]);

    const hasAttachments = imageUrlBlocks.length > 0 || pdfBlocks.length > 0;

    // Detect [SAVE_RESULT] blocks in AI message content
    const saveResults = useMemo(() => {
      if (isUser || !messageContent) return [];
      return parseSaveResults(messageContent);
    }, [isUser, messageContent]);

    // Strip save result markers from display content
    const displayContent = useMemo(() => {
      if (saveResults.length === 0) return messageContent;
      return stripSaveResultMarkers(messageContent);
    }, [messageContent, saveResults]);

    // Detect pipeline stage markers in AI message content
    const detectedStage = useMemo(() => {
      if (isUser || !displayContent) return null;
      for (const stage of PIPELINE_STAGES) {
        if (displayContent.includes(stage.marker)) return stage.id;
      }
      return null;
    }, [isUser, displayContent]);

    // Tool messages are handled by the processedMessages logic in ChatInterface
    // They get matched to tool calls on AI messages, so we skip standalone display
    if (isTool) return null;

    // Skip system messages
    if (!isUser && !isAi) return null;

    return (
      <div
        className={cn(
          "flex w-full max-w-full overflow-x-hidden",
          isUser && "flex-row-reverse",
        )}
      >
        <div
          className={cn("min-w-0 max-w-full", isUser ? "max-w-[70%]" : "w-full")}
        >
          {isUser ? (
            /* Human message: images + PDFs + text */
            <div className="mt-4 flex flex-col items-end gap-2">
              {hasAttachments && (
                <div className="flex flex-wrap justify-end gap-2">
                  {imageUrlBlocks.map((block, idx) => (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      key={`img-${idx}`}
                      src={block.image_url.url}
                      alt={`uploaded image ${idx + 1}`}
                      className="h-16 w-16 rounded-md object-cover"
                    />
                  ))}
                  {pdfBlocks.map((block, idx) => (
                    <div
                      key={`pdf-${idx}`}
                      className="flex items-center gap-2 rounded-md border bg-muted px-3 py-2"
                    >
                      <File className="h-5 w-5 text-teal-700" />
                      <span className="text-xs text-foreground">
                        {block.metadata?.filename || "PDF file"}
                      </span>
                    </div>
                  ))}
                </div>
              )}
              {hasContent && (
                <div className="overflow-hidden break-words rounded-xl rounded-br-none border border-border bg-primary/10 px-3 py-2 text-sm leading-relaxed">
                  <p className="m-0 whitespace-pre-wrap break-words">
                    {messageContent}
                  </p>
                </div>
              )}
            </div>
          ) : (
            /* AI message: tool calls + rendered markdown */
            (hasToolCalls || hasContent) && (
              <div className="mt-4 min-w-0 overflow-hidden break-words text-sm leading-relaxed">
                {/* Pipeline stage indicator */}
                {detectedStage && (
                  <div className="mb-2 flex flex-wrap gap-1.5">
                    {PIPELINE_STAGES.map((stage) => (
                      <span
                        key={stage.id}
                        className={cn(
                          "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
                          stage.id === detectedStage
                            ? "bg-primary text-primary-foreground"
                            : "bg-muted text-muted-foreground",
                        )}
                      >
                        {stage.label}
                      </span>
                    ))}
                  </div>
                )}

                {/* Tool call boxes (skip "task" calls) */}
                {visibleToolCalls.length > 0 && (
                  <div className="mb-2 space-y-0.5">
                    {visibleToolCalls.map((tc) => (
                      <ToolCallBox
                        key={tc.id}
                        toolCall={tc}
                        uiComponent={uiMap.get(tc.id)}
                        stream={stream}
                        graphId={graphId}
                      />
                    ))}
                  </div>
                )}

                {/* Sub-agent indicators for "task" tool calls */}
                {subAgents.length > 0 && (
                  <div className="mb-2 flex w-fit max-w-full flex-col gap-4">
                    {subAgents.map((sa) => (
                      <SubAgentIndicator key={sa.id} subAgent={sa} />
                    ))}
                  </div>
                )}

                {/* Text content */}
                {hasContent && (
                  isStreaming ? (
                    <>
                      <MarkdownContent
                        content={displayContent}
                        streaming
                        className="[&_p:last-child]:inline [&_p:not(:last-child)]:inline-block"
                      />
                      <span className="animate-pulse">|</span>
                    </>
                  ) : (
                    <>
                      {saveResults.length > 0 && (
                        <div className="space-y-2">
                          {saveResults.map((result, idx) => (
                            <ToolResultCard key={`save-result-${idx}`} data={result} />
                          ))}
                        </div>
                      )}
                      <MarkdownContent content={displayContent} />
                    </>
                  )
                )}
              </div>
            )
          )}
        </div>
      </div>
    );
  },
);

ChatMessage.displayName = "ChatMessage";
