"use client";

import useSWRInfinite from "swr/infinite";
import type { Thread, Client } from "@langchain/langgraph-sdk";
import { getConfig } from "@/lib/config";

export interface ThreadItem {
  id: string;
  updatedAt: Date;
  status: Thread["status"];
  title: string;
  description: string;
  assistantId?: string;
}

const DEFAULT_PAGE_SIZE = 20;

export function useThreads(
  client: Client,
  props?: {
    status?: Thread["status"];
    limit?: number;
  },
) {
  const pageSize = props?.limit || DEFAULT_PAGE_SIZE;

  return useSWRInfinite(
    (pageIndex: number, previousPageData: ThreadItem[] | null) => {
      const config = getConfig();

      if (!config) {
        return null;
      }

      // If the previous page returned no items, we've reached the end
      if (previousPageData && previousPageData.length === 0) {
        return null;
      }

      return {
        kind: "threads" as const,
        pageIndex,
        pageSize,
        assistantId: config.assistantId,
        status: props?.status,
      };
    },
    async ({
      assistantId,
      status,
      pageIndex,
      pageSize,
    }: {
      kind: "threads";
      pageIndex: number;
      pageSize: number;
      assistantId: string;
      status?: Thread["status"];
    }) => {
      // Check if assistantId is a UUID (deployed) or graph name (local)
      const isUUID =
        /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
          assistantId,
        );

      const threads = await client.threads.search({
        limit: pageSize,
        offset: pageIndex * pageSize,
        sortBy: "updated_at" as const,
        sortOrder: "desc" as const,
        status,
        // Only filter by assistant_id metadata for deployed graphs (UUIDs)
        // Local dev graphs don't set this metadata
        ...(isUUID ? { metadata: { assistant_id: assistantId } } : {}),
      });

      return threads.map((thread): ThreadItem => {
        let title = "无标题对话";
        let description = "";

        try {
          if (thread.values && typeof thread.values === "object") {
            const values = thread.values as Record<string, unknown>;
            const messages = values.messages as Array<Record<string, unknown>> | undefined;
            if (messages && Array.isArray(messages)) {
              const firstHumanMessage = messages.find(
                (m) => m.type === "human",
              );
              if (firstHumanMessage?.content) {
                const rawContent = firstHumanMessage.content;
                const content: string =
                  typeof rawContent === "string"
                    ? rawContent
                    : Array.isArray(rawContent)
                      ? String((rawContent[0] as Record<string, unknown>)?.text || "")
                      : "";
                title =
                  content.slice(0, 50) + (content.length > 50 ? "..." : "");
              }
              const firstAiMessage = messages.find(
                (m) => m.type === "ai",
              );
              if (firstAiMessage?.content) {
                const content =
                  typeof firstAiMessage.content === "string"
                    ? firstAiMessage.content
                    : "";
                description = content.slice(0, 100);
              }
            }
          }
        } catch {
          title = `对话 ${thread.thread_id.slice(0, 8)}`;
        }

        return {
          id: thread.thread_id,
          updatedAt: new Date(thread.updated_at),
          status: thread.status,
          title,
          description,
          assistantId,
        };
      });
    },
    {
      revalidateFirstPage: true,
      revalidateOnFocus: true,
      errorRetryInterval: 3000,
      dedupingInterval: 2000,
    },
  );
}
