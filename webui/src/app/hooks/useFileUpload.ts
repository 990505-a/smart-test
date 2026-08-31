"use client";

import { useState, useRef, useEffect, ChangeEvent, useCallback } from "react";
import { toast } from "sonner";
import { ContentBlock } from "@/app/types/types";
import {
  fileToContentBlock,
  type UploadStage,
  SUPPORTED_FILE_TYPES,
  SUPPORTED_IMAGE_TYPES,
  MAX_FILE_SIZE,
} from "@/app/utils/multimodal";

/**
 * One in-flight file, mirrored in the composer as a progress chip.
 * progress (0..1) is only meaningful during the "uploading" stage.
 */
export interface UploadItem {
  id: string;
  name: string;
  kind: "image" | "file";
  size: number;
  stage: UploadStage;
  progress: number;
}

/**
 * Hook for drag-drop + paste file upload with base64 conversion.
 * Returns content blocks, per-file upload progress, drag state, and
 * file handling callbacks.
 *
 * Images ride inline with the next message (no thread needed). PDF/MD must
 * be uploaded to /uploads/{threadId}/ before the first message — threads are
 * created lazily, so pass ensureThreadId (from useChat) and the hook will
 * create the thread on demand when the first non-image file arrives.
 */
export function useFileUpload(
  spaceId?: string,
  threadId?: string,
  ensureThreadId?: () => Promise<string | undefined>,
) {
  const [contentBlocks, setContentBlocks] = useState<ContentBlock[]>([]);
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  // In-flight file keys (name+kind), so a second drop of the same file while
  // the first is still uploading is treated as a duplicate.
  const inFlightRef = useRef<Set<string>>(new Set());
  const dropRef = useRef<HTMLDivElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const dragCounter = useRef(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const isDuplicate = useCallback(
    (file: File, blocks: ContentBlock[]) => {
      if (SUPPORTED_IMAGE_TYPES.includes(file.type)) {
        return blocks.some(
          (b) =>
            b.type === "image" &&
            b.metadata?.name === file.name &&
            b.mimeType === file.type,
        );
      }
      if (SUPPORTED_FILE_TYPES.includes(file.type)) {
        return blocks.some(
          (b) =>
            b.type === "file" &&
            b.metadata?.filename === file.name &&
            b.mimeType === file.type,
        );
      }
      return false;
    },
    [],
  );

  const processFiles = useCallback(
    async (files: File[], currentBlocks: ContentBlock[]) => {
      const validFiles = files.filter(
        (file) =>
          SUPPORTED_FILE_TYPES.includes(file.type) &&
          file.size <= MAX_FILE_SIZE,
      );
      const invalidFiles = files.filter(
        (file) => !SUPPORTED_FILE_TYPES.includes(file.type),
      );
      const oversizedFiles = files.filter(
        (file) =>
          SUPPORTED_FILE_TYPES.includes(file.type) && file.size > MAX_FILE_SIZE,
      );
      const fileKey = (file: File) =>
        SUPPORTED_IMAGE_TYPES.includes(file.type)
          ? `image:${file.name}:${file.type}`
          : `file:${file.name}:${file.type}`;
      const seenInBatch = new Set<string>();
      const duplicateFiles: File[] = [];
      const uniqueFiles: File[] = [];
      for (const file of validFiles) {
        const key = fileKey(file);
        if (
          seenInBatch.has(key) ||
          isDuplicate(file, currentBlocks) ||
          inFlightRef.current.has(key)
        ) {
          duplicateFiles.push(file);
        } else {
          seenInBatch.add(key);
          uniqueFiles.push(file);
        }
      }

      if (invalidFiles.length > 0) {
        toast.error(
          `Unsupported file type. Supported: JPEG, PNG, GIF, WEBP, PDF.`,
        );
      }
      if (oversizedFiles.length > 0) {
        toast.error(
          `File too large (max 20MB): ${oversizedFiles.map((f) => f.name).join(", ")}`,
        );
      }
      if (duplicateFiles.length > 0) {
        toast.error(
          `Duplicate file(s): ${duplicateFiles.map((f) => f.name).join(", ")}`,
        );
      }

      // Reserve every accepted key before any await. This prevents duplicate
      // files in the same batch or in concurrent drops from both starting.
      uniqueFiles.forEach((file) => inFlightRef.current.add(fileKey(file)));

      // Non-image files need a workspace thread. Do not continue with an empty
      // thread id when lazy thread creation fails, or the upload would be lost.
      let uploadThreadId = threadId;
      const nonImageFiles = uniqueFiles.filter(
        (f) => !SUPPORTED_IMAGE_TYPES.includes(f.type),
      );
      let filesToProcess = uniqueFiles;
      if (nonImageFiles.length > 0 && !uploadThreadId) {
        if (!ensureThreadId) {
          nonImageFiles.forEach((file) => inFlightRef.current.delete(fileKey(file)));
          toast.error("无法创建对话，文件上传已取消，请重试");
          filesToProcess = uniqueFiles.filter((file) =>
            SUPPORTED_IMAGE_TYPES.includes(file.type),
          );
        } else {
          uploadThreadId = (await ensureThreadId()) ?? "";
          if (!uploadThreadId) {
            nonImageFiles.forEach((file) => inFlightRef.current.delete(fileKey(file)));
            toast.error("无法创建对话，文件上传已取消，请重试");
            filesToProcess = uniqueFiles.filter((file) =>
              SUPPORTED_IMAGE_TYPES.includes(file.type),
            );
          }
        }
      }

      for (const file of filesToProcess) {
        const key = fileKey(file);
        const id = crypto.randomUUID();
        const kind: UploadItem["kind"] = SUPPORTED_IMAGE_TYPES.includes(file.type)
          ? "image"
          : "file";
        setUploads((prev) => [
          ...prev,
          { id, name: file.name, kind, size: file.size, stage: "reading", progress: 0 },
        ]);

        fileToContentBlock(file, spaceId, uploadThreadId, (stage, progress) => {
          setUploads((prev) =>
            prev.map((u) =>
              u.id === id ? { ...u, stage, progress: progress ?? u.progress } : u,
            ),
          );
        })
          .then((block) => {
            setContentBlocks((prev) => [...prev, block]);
          })
          .catch((err: unknown) => {
            const reason = err instanceof Error ? err.message : "请重试";
            toast.error(`${file.name} 上传失败：${reason}`);
          })
          .finally(() => {
            inFlightRef.current.delete(key);
            setUploads((prev) => prev.filter((u) => u.id !== id));
          });
      }
    },
    [isDuplicate, threadId, spaceId, ensureThreadId],
  );

  // Handle file input change (click-to-upload)
  const handleFileUpload = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (!files) return;
      processFiles(Array.from(files), contentBlocks);
      e.target.value = "";
    },
    [contentBlocks, processFiles],
  );

  // Handle file input change (click-to-upload)
  useEffect(() => {
    const dropTarget = dropRef.current;
    if (!dropTarget) return;

    const handleDragEnter = (e: DragEvent) => {
      if (!e.dataTransfer?.types?.includes("Files")) return;
      e.preventDefault();
      dragCounter.current += 1;
      setIsDragging(true);
    };
    const handleDragLeave = (e: DragEvent) => {
      if (!e.dataTransfer?.types?.includes("Files")) return;
      e.preventDefault();
      dragCounter.current -= 1;
      if (dragCounter.current <= 0) {
        dragCounter.current = 0;
        setIsDragging(false);
      }
    };
    const handleDrop = (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      dragCounter.current = 0;
      setIsDragging(false);
      const files = e.dataTransfer ? Array.from(e.dataTransfer.files) : [];
      if (files.length > 0) processFiles(files, contentBlocks);
    };
    const handleDragOver = (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
    };

    dropTarget.addEventListener("dragenter", handleDragEnter);
    dropTarget.addEventListener("dragleave", handleDragLeave);
    dropTarget.addEventListener("drop", handleDrop);
    dropTarget.addEventListener("dragover", handleDragOver);
    return () => {
      dropTarget.removeEventListener("dragenter", handleDragEnter);
      dropTarget.removeEventListener("dragleave", handleDragLeave);
      dropTarget.removeEventListener("drop", handleDrop);
      dropTarget.removeEventListener("dragover", handleDragOver);
      dragCounter.current = 0;
    };
  }, [contentBlocks, processFiles]);

  const removeContentBlock = useCallback((index: number) => {
    setContentBlocks((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const clearContentBlocks = useCallback(() => {
    setContentBlocks([]);
  }, []);

  /**
   * Handle paste event for files (images, PDFs).
   * Can be used as onPaste={handlePaste} on a textarea or input.
   */
  const handlePaste = useCallback(
    (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
      const items = e.clipboardData.items;
      if (!items) return;

      const files: File[] = [];
      for (let i = 0; i < items.length; i += 1) {
        const item = items[i];
        if (item.kind === "file") {
          const file = item.getAsFile();
          if (file) files.push(file);
        }
      }

      if (files.length === 0) return;
      e.preventDefault();

      processFiles(files, contentBlocks);
    },
    [contentBlocks, processFiles],
  );

  const addFiles = useCallback(
    (files: File[]) => {
      processFiles(files, contentBlocks);
    },
    [contentBlocks, processFiles],
  );

  return {
    contentBlocks,
    uploads,
    isUploading: uploads.length > 0,
    isDragging,
    addFiles,
    removeContentBlock,
    clearContentBlocks,
    handleFileUpload,
    handlePaste,
    dropRef,
    inputRef,
  };
}
