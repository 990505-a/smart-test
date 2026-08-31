"use client";

import React from "react";
import { File, Image as ImageIcon, Loader2 } from "lucide-react";
import type { UploadItem } from "@/app/hooks/useFileUpload";
import { cn } from "@/lib/utils";

const STAGE_LABEL: Record<UploadItem["stage"], string> = {
  reading: "读取文件…",
  uploading: "上传中…",
  processing: "解析文本…",
};

/**
 * Per-file upload progress chips shown in the composer while files are
 * being converted/uploaded. Each chip disappears as soon as its file
 * graduates into a real content-block preview (or fails with a toast).
 */
export const UploadProgressList: React.FC<{ uploads: UploadItem[] }> = ({
  uploads,
}) => {
  if (!uploads.length) return null;
  return (
    <div className="flex flex-wrap gap-2 p-3.5 pb-0">
      {uploads.map((u) => {
        // Images never hit the network — their bar just flashes through.
        const percent =
          u.stage === "processing"
            ? 100
            : u.stage === "uploading"
              ? Math.max(4, Math.round(u.progress * 100))
              : 4;
        return (
          <div
            key={u.id}
            className="flex w-56 flex-col gap-1.5 rounded-md border border-border bg-muted px-3 py-2"
          >
            <div className="flex items-center gap-2">
              {u.kind === "image" ? (
                <ImageIcon className="h-4 w-4 shrink-0 text-teal-700" />
              ) : (
                <File className="h-4 w-4 shrink-0 text-teal-700" />
              )}
              <span className="min-w-0 flex-1 truncate text-xs text-foreground">
                {u.name}
              </span>
              {u.stage === "uploading" ? (
                <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                  {percent}%
                </span>
              ) : (
                <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-muted-foreground" />
              )}
            </div>
            <div className="h-1 overflow-hidden rounded-full bg-muted-foreground/15">
              <div
                className={cn(
                  "h-full rounded-full bg-teal-600 transition-[width] duration-150",
                  (u.stage === "reading" || u.stage === "processing") &&
                    "motion-safe:animate-pulse",
                )}
                style={{ width: `${percent}%` }}
              />
            </div>
            <span className="text-[10px] text-muted-foreground">
              {STAGE_LABEL[u.stage]}
              {u.stage === "uploading" && ` ${percent}%`}
            </span>
          </div>
        );
      })}
    </div>
  );
};
