"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import type { ContentBlock, ToolCall, SubAgent } from "@/app/types/types";
import { PIPELINE_STAGES } from "@/app/types/types";
import { cn } from "@/lib/utils";
import { File, ChevronDown, ChevronUp, Brain, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
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
  /** 打开子智能体实时操作面板（右侧抽屉） */
  onSubAgentActivity?: (subAgent: SubAgent) => void;
  /** task 调用是否已结束（结果已返回或 run 已结束）——执行中状态的收敛通道 */
  isSubAgentClosed?: (taskCallId: string) => boolean;
}

function firstNonEmptyLine(text: string): string {
  return text.split("\n").find((l) => l.trim()) ?? "";
}

function lastNonEmptyLine(text: string): string {
  const lines = text.split("\n");
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    if (lines[i].trim()) return lines[i];
  }
  return "";
}

/**
 * Collapsible reasoning panel (dsh-style "Think" row): while the model is
 * still thinking, the header shows a live tail of the latest reasoning line
 * with a pulsing indicator; once the answer text starts, it settles to a
 * static "已深度思考" row. Expanded body is plain grey text that follows
 * the stream.
 */
const ThinkingBlock = React.memo<{ content: string; running?: boolean }>(
  ({ content, running }) => {
    const [isExpanded, setIsExpanded] = useState(false);
    const bodyRef = useRef<HTMLDivElement>(null);

    // Keep the expanded body pinned to the newest reasoning while streaming.
    useEffect(() => {
      if (running && isExpanded && bodyRef.current) {
        bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
      }
    }, [content, running, isExpanded]);

    const summary = useMemo(
      () => (running ? lastNonEmptyLine(content) : firstNonEmptyLine(content)),
      [content, running],
    );

    return (
      <div className="mb-2 overflow-hidden rounded-lg border border-border/50 bg-muted/30">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setIsExpanded((prev) => !prev)}
          className="flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left"
        >
          <div className="flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
            <Brain
              size={14}
              className={running ? "motion-safe:animate-pulse shrink-0" : "shrink-0"}
            />
            <span className="shrink-0 font-medium">
              {running ? "正在思考…" : "已深度思考"}
            </span>
            {summary && (
              <span className="min-w-0 truncate opacity-70">· {summary}</span>
            )}
          </div>
          {isExpanded ? (
            <ChevronUp size={14} className="shrink-0 text-muted-foreground" />
          ) : (
            <ChevronDown size={14} className="shrink-0 text-muted-foreground" />
          )}
        </Button>
        {isExpanded && (
          <div
            ref={bodyRef}
            className="max-h-72 overflow-y-auto border-t border-border/50 px-3 py-2"
          >
            <p className="whitespace-pre-wrap break-words text-xs leading-5 text-muted-foreground">
              {content}
            </p>
          </div>
        )}
      </div>
    );
  },
);
ThinkingBlock.displayName = "ThinkingBlock";

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

/** Strip LLM-internal content blocks from user message display. */
function stripInternalContent(text: string): string {
  if (!text) return text;
  // Remove [代码分析上下文 ...] prefix
  let result = text.replace(/\[代码分析上下文[^\]]*\]\s*/g, "");
  // Remove [Wiki 知识库] line
  result = result.replace(/\[Wiki 知识库\][^\n]*\n?/g, "");
  // Remove [Uploaded N file(s)] header and all ### File content (PDF/MD text)
  // Users don't need to see extracted file text in their message bubble
  result = result.replace(/\n*\[Uploaded \d+ file\(s\)\][\s\S]*$/g, "");
  // Remove leading whitespace from repo lines
  result = result.replace(/^\s*仓库路径:.*$/gm, "");
  return result.trim();
}

export const ChatMessage = React.memo<ChatMessageProps>(
  ({ message, toolCalls = [], isStreaming = false, ui, stream, graphId, onSubAgentActivity, isSubAgentClosed }) => {
    const isUser = message.type === "human";
    const isAi = message.type === "ai";
    const isTool = message.type === "tool";
    const rawContent = extractStringContent(message.content);
    // For user messages, strip LLM-internal sections ([代码分析上下文...] and [Uploaded N file(s)] blocks)
    const messageContent = isUser ? stripInternalContent(rawContent) : rawContent;
    const hasContent = messageContent && messageContent.trim() !== "";
    const hasToolCalls = toolCalls.length > 0;
    const visibleToolCalls = toolCalls.filter((tc) => tc.name !== "task");
    // dsh interrupted 语义：用户中途停止，已显示内容即定稿前缀。
    // 标记由 stopStream 写入 additional_kwargs 并随消息落库，刷新可重建
    const stoppedByUser = isAi && message.additional_kwargs?.stopped_by_user === true;

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
          status:
            tc.status === "completed" || isSubAgentClosed?.(tc.id)
              ? "completed"
              : tc.status === "error"
                ? "error"
                : "active",
        }));
    }, [toolCalls, isSubAgentClosed]);

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

    // Extract DeepSeek R1 reasoning/thinking content
    const reasoningContent = useMemo(() => {
      if (!isAi) return null;
      // Way 1: additional_kwargs.reasoning_content (DeepSeek API native)
      const rc = message.additional_kwargs?.reasoning_content;
      if (typeof rc === "string" && rc.trim()) return rc;
      // Way 2: thinking block in content array (LangChain standard)
      if (Array.isArray(message.content)) {
        const thinkingBlock = (message.content as Array<Record<string, unknown>>).find(
          (b) => b.type === "thinking" && typeof b.text === "string",
        );
        if (thinkingBlock && typeof thinkingBlock.text === "string" && thinkingBlock.text.trim()) {
          return thinkingBlock.text as string;
        }
      }
      return null;
    }, [isAi, message.additional_kwargs, message.content]);

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

    // Streaming renders are already coalesced (50ms flush) and incremental
    // (only the tail block re-parses), so the extra urgent+deferred double
    // render from useDeferredValue cost more than it saved.

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
                <div className="overflow-hidden break-words rounded-[22px] rounded-br-md bg-secondary px-4 py-2.5 text-[15px] leading-6">
                  <p className="m-0 whitespace-pre-wrap break-words">
                    {messageContent}
                  </p>
                </div>
              )}
            </div>
          ) : (
            /* AI message: tool calls + rendered markdown */
            (hasToolCalls || hasContent || reasoningContent) && (
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

                {/* Thinking block (reasoning_content / thinking blocks) —
                    "running" only while streaming and before answer text
                    starts arriving, mirroring dsh's Think row lifecycle */}
                {isAi && reasoningContent && (
                  <ThinkingBlock
                    content={reasoningContent}
                    running={isStreaming && !hasContent}
                  />
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

                {/* Text content */}
                {hasContent && (
                  isStreaming ? (
                    <>
                      <MarkdownContent
                        content={displayContent}
                        streaming
                        className="[&_p:last-child]:inline [&_p:not(:last-child)]:inline-block"
                      />
                      <span className="inline-block w-[2px] animate-none bg-foreground opacity-70">|</span>
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

                {/* 已停止标记（dsh interrupted）：用户中途停止生成，
                    已显示的内容就是定稿前缀 */}
                {stoppedByUser && !isStreaming && (
                  <div className="mt-1.5 flex items-center gap-1 text-xs text-muted-foreground">
                    <Square size={9} className="shrink-0 fill-current" />
                    <span>已停止</span>
                  </div>
                )}

                {/* Sub-agent indicators：跟在回答文字之后——文字是宣告、
                    指示器是动作，先读到宣告再看派发更符合阅读顺序 */}
                {subAgents.length > 0 && (
                  <div className="mt-3 flex w-fit max-w-full flex-col gap-2">
                    {subAgents.map((sa) => (
                      <SubAgentIndicator
                        key={sa.id}
                        subAgent={sa}
                        onOpenActivity={onSubAgentActivity}
                      />
                    ))}
                  </div>
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
