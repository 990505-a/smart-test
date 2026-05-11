"use client";

import { useState, useRef, useEffect, ChangeEvent, useCallback } from "react";
import { toast } from "sonner";
import { ContentBlock } from "@/app/types/types";
import {
  fileToContentBlock,
  SUPPORTED_FILE_TYPES,
  MAX_FILE_SIZE,
} from "@/app/utils/multimodal";

/**
 * Hook for drag-drop + paste file upload with base64 conversion.
 * Returns content blocks, drag state, and file handling callbacks.
 */
export function useFileUpload() {
  const [contentBlocks, setContentBlocks] = useState<ContentBlock[]>([]);
  const dropRef = useRef<HTMLDivElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const dragCounter = useRef(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const isDuplicate = useCallback(
    (file: File, blocks: ContentBlock[]) => {
      if (file.type === "application/pdf") {
        return blocks.some(
          (b) =>
            b.type === "file" &&
            b.mimeType === "application/pdf" &&
            b.metadata?.filename === file.name,
        );
      }
      if (SUPPORTED_FILE_TYPES.includes(file.type)) {
        return blocks.some(
          (b) =>
            b.type === "image" &&
            b.metadata?.name === file.name &&
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
      const duplicateFiles = validFiles.filter((file) =>
        isDuplicate(file, currentBlocks),
      );
      const uniqueFiles = validFiles.filter(
        (file) => !isDuplicate(file, currentBlocks),
      );

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

      const newBlocks = uniqueFiles.length
        ? await Promise.all(uniqueFiles.map(fileToContentBlock))
        : [];
      return newBlocks;
    },
    [isDuplicate],
  );

  // Handle file input change (click-to-upload)
  const handleFileUpload = useCallback(
    async (e: ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (!files) return;
      const fileArray = Array.from(files);
      const newBlocks = await processFiles(fileArray, contentBlocks);
      setContentBlocks((prev) => [...prev, ...newBlocks]);
      e.target.value = "";
    },
    [contentBlocks, processFiles],
  );

  // Global drag/drop event listeners
  useEffect(() => {
    const handleWindowDragEnter = (e: DragEvent) => {
      if (e.dataTransfer?.types?.includes("Files")) {
        dragCounter.current += 1;
        setIsDragging(true);
      }
    };

    const handleWindowDragLeave = (e: DragEvent) => {
      if (e.dataTransfer?.types?.includes("Files")) {
        dragCounter.current -= 1;
        if (dragCounter.current <= 0) {
          setIsDragging(false);
          dragCounter.current = 0;
        }
      }
    };

    const handleWindowDrop = async (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      dragCounter.current = 0;
      setIsDragging(false);

      if (!e.dataTransfer) return;
      const files = Array.from(e.dataTransfer.files);
      const newBlocks = await processFiles(files, contentBlocks);
      setContentBlocks((prev) => [...prev, ...newBlocks]);
    };

    const handleWindowDragEnd = () => {
      dragCounter.current = 0;
      setIsDragging(false);
    };

    const handleWindowDragOver = (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
    };

    window.addEventListener("dragenter", handleWindowDragEnter);
    window.addEventListener("dragleave", handleWindowDragLeave);
    window.addEventListener("drop", handleWindowDrop);
    window.addEventListener("dragend", handleWindowDragEnd);
    window.addEventListener("dragover", handleWindowDragOver);

    return () => {
      window.removeEventListener("dragenter", handleWindowDragEnter);
      window.removeEventListener("dragleave", handleWindowDragLeave);
      window.removeEventListener("drop", handleWindowDrop);
      window.removeEventListener("dragend", handleWindowDragEnd);
      window.removeEventListener("dragover", handleWindowDragOver);
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
    async (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
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

      const newBlocks = await processFiles(files, contentBlocks);
      setContentBlocks((prev) => [...prev, ...newBlocks]);
    },
    [contentBlocks, processFiles],
  );

  const addFiles = useCallback(
    async (files: File[]) => {
      const newBlocks = await processFiles(files, contentBlocks);
      setContentBlocks((prev) => [...prev, ...newBlocks]);
    },
    [contentBlocks, processFiles],
  );

  return {
    contentBlocks,
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
