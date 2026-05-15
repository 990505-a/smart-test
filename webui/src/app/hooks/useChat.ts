"use client";

import { useCallback, useEffect, useRef } from "react";
import { useStream } from "@langchain/langgraph-sdk/react";
import type { Message } from "@langchain/langgraph-sdk";
import { v4 as uuidv4 } from "uuid";
import { useClient } from "@/providers/ClientProvider";
import { useQueryState } from "nuqs";
import { getConfig } from "@/lib/config";
import { revalidateTestCases } from "@/lib/api/useTestCases";
import { revalidateProjects } from "@/lib/api/useProjects";
import type { ContentBlock, StateType } from "@/app/types/types";

/**
 * Hook wrapping @langchain/langgraph-sdk useStream for SSE streaming chat.
 * Handles image/PDF content splitting and message construction.
 */
export function useChat({
  assistantId,
  workspaceId = "default",
  onHistoryRevalidate,
}: {
  assistantId: string;
  workspaceId?: string;
  onHistoryRevalidate?: () => void;
}) {
  const [threadId, setThreadId] = useQueryState("threadId");
  const client = useClient();

  const revalidateHistoryRef = useRef(onHistoryRevalidate);

  useEffect(() => {
    revalidateHistoryRef.current = onHistoryRevalidate;
  }, [onHistoryRevalidate]);

  const revalidateManagementCache = useCallback(() => {
    // Revalidate test cases and projects cache so management UI updates
    // after Agent auto-saves
    revalidateTestCases();
    revalidateProjects();
  }, []);

  const scheduleHistoryRevalidate = useCallback(() => {
    if (typeof window === "undefined") {
      revalidateHistoryRef.current?.();
      revalidateManagementCache();
      return;
    }
    window.setTimeout(() => {
      revalidateHistoryRef.current?.();
      revalidateManagementCache();
    }, 0);
  }, [revalidateManagementCache]);

  const stream = useStream<StateType>({
    assistantId,
    client: client ?? undefined,
    reconnectOnMount: true,
    threadId: threadId ?? null,
    onThreadId: setThreadId,
    fetchStateHistory: true,
    onFinish: scheduleHistoryRevalidate,
    onError: scheduleHistoryRevalidate,
    onCreated: scheduleHistoryRevalidate,
  });

  /**
   * Send a message with optional multimodal content blocks.
   * Images go into content array as image_url format.
   * PDFs go into additional_kwargs.attachments.
   */
  const sendMessage = useCallback(
    (content: string, contentBlocks?: ContentBlock[]) => {
      // Split blocks: images go into content array as image_url format,
      // PDFs go into additional_kwargs.attachments
      const imageBlocks =
        contentBlocks?.filter((b) => b.type === "image") ?? [];
      const pdfBlocks =
        contentBlocks?.filter((b) => b.type !== "image") ?? [];

      // Convert image blocks to image_url format (OpenAI-compatible)
      const imageUrlBlocks = imageBlocks.map((b) => ({
        type: "image_url" as const,
        image_url: {
          url: `data:${b.mimeType};base64,${b.data}`,
        },
      }));

      const messageContent: Message["content"] =
        imageUrlBlocks.length > 0
          ? ([
              ...(content.trim().length > 0
                ? [{ type: "text" as const, text: content }]
                : []),
              ...imageUrlBlocks,
            ] as Message["content"])
          : content;

      const config = getConfig();
      const newMessage = {
        id: uuidv4(),
        type: "human" as const,
        content: messageContent,
        ...(pdfBlocks.length > 0 || config?.enablePdfMultimodal !== undefined
          ? {
              additional_kwargs: {
                ...(pdfBlocks.length > 0 ? { attachments: pdfBlocks } : {}),
                enable_multimodal: config?.enablePdfMultimodal ?? true,
              },
            }
          : {}),
      };

      stream.submit(
        { messages: [newMessage] },
        {
          optimisticValues: (prev) => ({
            messages: [...(prev.messages ?? []), newMessage],
          }),
          config: {
            recursion_limit: 1000,
            configurable: { space_id: workspaceId || "default" },
          },
        },
      );

      // Update thread list immediately when sending a message
      onHistoryRevalidate?.();
    },
    [stream, onHistoryRevalidate, workspaceId],
  );

  const stopStream = useCallback(() => {
    stream.stop();
  }, [stream]);

  return {
    stream,
    messages: stream.messages,
    isLoading: stream.isLoading,
    sendMessage,
    stopStream,
    threadId,
    setThreadId,
  };
}
