"use client";

import React from "react";
import { File, X as XIcon } from "lucide-react";
import type { ContentBlock } from "@/app/types/types";
import { cn } from "@/lib/utils";

export interface MultimodalPreviewProps {
  block: ContentBlock;
  removable?: boolean;
  onRemove?: () => void;
  className?: string;
  size?: "sm" | "md" | "lg";
}

export const MultimodalPreview: React.FC<MultimodalPreviewProps> = ({
  block,
  removable = false,
  onRemove,
  className,
  size = "md",
}) => {
  // Image block
  if (block.type === "image" && block.mimeType.startsWith("image/")) {
    const url = `data:${block.mimeType};base64,${block.data}`;
    const imgClass =
      size === "sm"
        ? "rounded-md object-cover h-10 w-10"
        : size === "lg"
          ? "rounded-md object-cover h-24 w-24"
          : "rounded-md object-cover h-16 w-16";
    return (
      <div className={cn("relative inline-block", className)}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={url}
          alt={String(block.metadata?.name || "uploaded image")}
          className={imgClass}
        />
        {removable && (
          <button
            type="button"
            className="absolute top-1 right-1 z-10 rounded-full bg-gray-500 text-white hover:bg-gray-700"
            onClick={onRemove}
            aria-label="Remove image"
          >
            <XIcon className="h-4 w-4" />
          </button>
        )}
      </div>
    );
  }

  // PDF / file block
  if (block.type === "file") {
    const filename =
      block.metadata?.filename || block.metadata?.name || "PDF file";
    return (
      <div
        className={cn(
          "relative flex items-start gap-2 rounded-md border bg-muted px-3 py-2",
          className,
        )}
      >
        <div className="flex flex-shrink-0 flex-col items-start justify-start">
          <File
            className={cn(
              "text-teal-700",
              size === "sm" ? "h-5 w-5" : "h-7 w-7",
            )}
          />
        </div>
        <span
          className="min-w-0 flex-1 text-sm break-all text-foreground"
          style={{ wordBreak: "break-all", whiteSpace: "pre-wrap" }}
        >
          {String(filename)}
        </span>
        {removable && (
          <button
            type="button"
            className="ml-2 self-start rounded-full bg-muted-foreground/20 p-1 text-teal-700 hover:bg-muted-foreground/30"
            onClick={onRemove}
            aria-label="Remove file"
          >
            <XIcon className="h-4 w-4" />
          </button>
        )}
      </div>
    );
  }

  // Fallback for unknown types
  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-md border bg-muted px-3 py-2 text-muted-foreground",
        className,
      )}
    >
      <File className="h-5 w-5 flex-shrink-0" />
      <span className="truncate text-xs">Unsupported file type</span>
      {removable && (
        <button
          type="button"
          className="ml-2 rounded-full bg-muted-foreground/20 p-1 text-muted-foreground hover:bg-muted-foreground/30"
          onClick={onRemove}
          aria-label="Remove file"
        >
          <XIcon className="h-4 w-4" />
        </button>
      )}
    </div>
  );
};
