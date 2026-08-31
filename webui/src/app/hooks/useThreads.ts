"use client";

import useSWRInfinite from "swr/infinite";
import { getFastapiUrl } from "@/lib/config";

export interface ThreadItem {
  id: string;
  updatedAt: Date;
  title: string;
  description: string;
}

const DEFAULT_PAGE_SIZE = 20;

async function fetcher(url: string) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch threads: ${res.status}`);
  return res.json();
}

export function useThreads() {
  return useSWRInfinite(
    (pageIndex: number, previousPageData: { threads: ThreadItem[] } | null) => {
      if (previousPageData && previousPageData.threads.length === 0) {
        return null;
      }

      const apiBase = getFastapiUrl();
      return `${apiBase}/api/v2/threads?limit=${DEFAULT_PAGE_SIZE}&offset=${pageIndex * DEFAULT_PAGE_SIZE}`;
    },
    async (url: string) => {
      const data = await fetcher(url);
      return {
        threads: (data.threads || []).map(
          (t: { thread_id: string; title: string; description: string; updated_at: string }) => ({
            id: t.thread_id,
            updatedAt: new Date(t.updated_at),
            title: t.title || "无标题对话",
            description: t.description || "",
          })
        ),
        total: data.total || 0,
      };
    },
    {
      revalidateFirstPage: true,
    }
  );
}
