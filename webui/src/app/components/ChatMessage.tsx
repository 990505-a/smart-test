"use client";

import React, { useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ContentBlock } from "@/app/types/types";
import { PIPELINE_STAGES } from "@/app/types/types";
import { cn } from "@/lib/utils";
import { File } from "lucide-react";

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
    content: string | Array<Record<string, unknown>>;
    additional_kwargs?: Record<string, unknown>;
  };
  isStreaming?: boolean;
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
  ({ message, isStreaming = false }) => {
    const isUser = message.type === "human";
    const isAi = message.type === "ai";
    const messageContent = extractStringContent(message.content);
    const hasContent = messageContent && messageContent.trim() !== "";

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

    // Detect pipeline stage markers in AI message content
    const detectedStage = useMemo(() => {
      if (isUser || !messageContent) return null;
      for (const stage of PIPELINE_STAGES) {
        if (messageContent.includes(stage.marker)) return stage.id;
      }
      return null;
    }, [isUser, messageContent]);

    // Skip rendering for tool/system messages without visible content
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
            /* AI message: rendered with markdown */
            hasContent && (
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
                {isStreaming ? (
                  <div className="prose min-w-0 max-w-full text-sm">
                    <p className="m-0 whitespace-pre-wrap break-words">
                      {messageContent}
                      <span className="animate-pulse">|</span>
                    </p>
                  </div>
                ) : (
                  <div className="prose prose-sm max-w-none dark:prose-invert">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {messageContent}
                    </ReactMarkdown>
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
