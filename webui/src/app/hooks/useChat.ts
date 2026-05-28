"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import { useStream } from "@langchain/langgraph-sdk/react";
import type { Message } from "@langchain/langgraph-sdk";
import { v4 as uuidv4 } from "uuid";
import { useClient } from "@/providers/ClientProvider";
import { useQueryState } from "nuqs";
import { revalidateTestCases } from "@/lib/api/useTestCases";
import { revalidateProjects } from "@/lib/api/useProjects";
import { usePaginatedMessages } from "@/lib/api/messages";
import type { ContentBlock, StateType } from "@/app/types/types";

/**
 * Hook wrapping @langchain/langgraph-sdk useStream for SSE streaming chat.
 * Handles image/PDF content splitting and message construction.
 *
 * Uses paginated loading for existing threads to avoid fetching the full
 * thread state (which can be 25MB+). Only the latest 20 messages are loaded
 * initially; older messages load on scroll-up via usePaginatedMessages.
 *
 * During active streaming, paginated messages and streaming messages are
 * merged with deduplication (stream wins).
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

  // Paginated message loading for existing threads
  const paginated = usePaginatedMessages(threadId);

  // Ref to track real threadId for submit — useStream receives null to
  // prevent it from fetching the full thread state on mount.
  const realThreadIdRef = useRef(threadId);

  useEffect(() => {
    realThreadIdRef.current = threadId;
  }, [threadId]);

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

  // Pass threadId: null to useStream to prevent it from fetching the full
  // thread state. We use paginated messages for history instead.
  // The realThreadIdRef holds the actual threadId for submit operations.
  const stream = useStream<StateType>({
    assistantId,
    client: client ?? undefined,
    reconnectOnMount: false,
    threadId: null,
    onThreadId: setThreadId,
    fetchStateHistory: false,
    onFinish: scheduleHistoryRevalidate,
    onError: (error) => {
      console.error("[useChat] stream error:", error);
      scheduleHistoryRevalidate();
    },
    onCreated: scheduleHistoryRevalidate,
  });

  // Dual-source merge: paginated messages as base, streaming messages override.
  // During active streaming, stream messages are more current, so they win on dedup.
  // When not streaming, use paginated messages only.
  const mergedMessages = useMemo(() => {
    // If there are streaming messages, merge with paginated
    if (stream.messages && stream.messages.length > 0) {
      const merged = new Map<string, Message>();

      // Add paginated messages first (older history)
      for (const msg of paginated.messages) {
        if (msg.id) {
          merged.set(msg.id, msg as unknown as Message);
        }
      }

      // Override with streaming messages (more current, wins on dedup)
      for (const msg of stream.messages) {
        if (msg.id) {
          merged.set(msg.id, msg);
        }
      }

      return Array.from(merged.values());
    }

    // Not streaming: convert paginated messages to Message-compatible array
    return paginated.messages as unknown as Message[];
  }, [stream.messages, paginated.messages]);

  /**
   * Send a message with optional multimodal content blocks.
   * Images go into content array as image_url format.
   * Markdown files are decoded to text and embedded directly.
   * PDF files use pre-extracted text from metadata (extracted during upload).
   */
  const sendMessage = useCallback(
    (content: string, contentBlocks?: ContentBlock[], context?: { repoPath?: string; taskId?: string }) => {
      const imageBlocks =
        contentBlocks?.filter((b) => b.type === "image") ?? [];
      const fileBlocks =
        contentBlocks?.filter((b) => b.type !== "image") ?? [];

      // Convert image blocks to image_url format (OpenAI-compatible)
      const imageUrlBlocks = imageBlocks.map((b) => ({
        type: "image_url" as const,
        image_url: {
          url: `data:${b.mimeType};base64,${b.data}`,
        },
      }));

      // Process file blocks: embed extracted text directly in the message.
      const fileTextParts: string[] = [];
      for (const fb of fileBlocks) {
        const filename = fb.metadata?.filename || fb.metadata?.name || "document";
        const extractedText = fb.metadata?.extractedText;

        if (extractedText) {
          fileTextParts.push(`### File: ${filename}\n\n${extractedText}`);
        } else {
          fileTextParts.push(`### File: ${filename}\n\n[Text extraction failed or unavailable.]`);
        }
      }

      const fileText = fileTextParts.length > 0
        ? `\n\n[Uploaded ${fileTextParts.length} file(s)]\n\n${fileTextParts.join("\n\n---\n\n")}`
        : "";

      const hasBlocks = imageUrlBlocks.length > 0 || fileText.length > 0;
      const messageContent: Message["content"] =
        hasBlocks
          ? ([
              ...(content.trim().length > 0
                ? [{ type: "text" as const, text: content + fileText }]
                : [{ type: "text" as const, text: fileText.trim() }]),
              ...imageUrlBlocks,
            ] as Message["content"])
          : content;

      const newMessage = {
        id: uuidv4(),
        type: "human" as const,
        content: messageContent,
      };

      // For existing threads, set the threadId before submitting so useStream
      // knows which thread to stream from. This sets the internal threadId
      // that submit() reads as usableThreadId.
      const existingThreadId = realThreadIdRef.current;
      if (existingThreadId) {
        setThreadId(existingThreadId);
      }

      stream.submit(
        {
          messages: [newMessage],
        },
        {
          optimisticValues: (prev) => ({
            messages: [...(prev.messages ?? []), newMessage],
          }),
          config: {
            recursion_limit: 1000,
            configurable: {
              space_id: workspaceId || "default",
              repo_path: context?.repoPath || "",
              task_id: context?.taskId || "",
            },
          },
        },
      );

      // Update thread list immediately when sending a message
      onHistoryRevalidate?.();
    },
    [stream, onHistoryRevalidate, workspaceId, setThreadId],
  );

  const stopStream = useCallback(() => {
    stream.stop();
  }, [stream]);

  const resumeInterrupt = useCallback(
    (value: unknown) => {
      stream.submit(null, { command: { resume: value } });
      onHistoryRevalidate?.();
    },
    [stream, onHistoryRevalidate],
  );

  const currentValues = stream.values as StateType | null;
  const values = currentValues ?? ({} as StateType);

  return {
    stream,
    messages: mergedMessages,
    isLoading: stream.isLoading,
    sendMessage,
    stopStream,
    resumeInterrupt,
    todos: values.todos ?? [],
    files: values.files ?? {},
    ui: values.ui,
    interrupt: stream.interrupt,
    threadId,
    setThreadId,
    // Paginated message controls
    isLoadingHistory: paginated.isLoading || paginated.isValidating,
    hasOlderMessages: paginated.hasMore,
    loadOlderMessages: paginated.loadMore,
  };
}
