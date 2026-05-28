"use client";

import useSWRInfinite from "swr/infinite";
import type {
  PaginatedMessagesResponse,
  PaginatedMessage,
} from "@/app/types/types";
import { getConfig } from "@/lib/config";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

/**
 * Hook for paginated message loading from the backend endpoint.
 *
 * Uses cursor-based pagination via useSWRInfinite. The API returns pages
 * from newest (first page) to oldest (subsequent pages), with each page's
 * messages in chronological order within itself.
 *
 * Flattening all pages and reversing gives a complete chronological message list.
 */
export function usePaginatedMessages(
  threadId: string | null,
  pageSize: number = 20,
) {
  const { data, error, size, setSize, mutate, isLoading, isValidating } =
    useSWRInfinite<PaginatedMessagesResponse>(
      (pageIndex, previousPageData) => {
        // No thread selected
        if (!threadId) return null;

        // No more pages
        if (previousPageData && !previousPageData.has_more) return null;

        const config = getConfig();
        const apiBase = config?.fastapiUrl || "http://localhost:8000";

        // First page: no cursor
        if (pageIndex === 0) {
          return `${apiBase}/api/v2/threads/${threadId}/messages?limit=${pageSize}`;
        }

        // Subsequent pages: use next_cursor from previous page
        if (previousPageData?.next_cursor) {
          return `${apiBase}/api/v2/threads/${threadId}/messages?limit=${pageSize}&cursor=${previousPageData.next_cursor}`;
        }

        return null;
      },
      fetcher,
      {
        revalidateFirstPage: false,
        revalidateOnFocus: false,
        revalidateOnReconnect: false,
      },
    );

  // Flatten pages and reverse to chronological order.
  // API returns pages newest-first, each page is chronologically ordered.
  // Reversing the flat list gives oldest-to-newest display order.
  const messages: PaginatedMessage[] = data
    ? [...data.flatMap((page) => page.messages)].reverse()
    : [];

  // Total count from first page
  const total: number = data?.[0]?.total ?? 0;

  // Whether more older messages exist
  const hasMore: boolean = data ? data[data.length - 1]?.has_more ?? false : false;

  // Load next page (older messages)
  const loadMore = () => setSize(size + 1);

  return {
    messages,
    total,
    hasMore,
    loadMore,
    isLoading,
    isValidating,
    mutate,
    error,
  };
}

export type { PaginatedMessage, PaginatedMessagesResponse as PaginatedResponse };
