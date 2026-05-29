import { ContentBlock } from "@/app/types/types";
import { toast } from "sonner";

const SUPPORTED_IMAGE_TYPES = [
  "image/jpeg",
  "image/png",
  "image/gif",
  "image/webp",
];

const SUPPORTED_FILE_TYPES = [
  ...SUPPORTED_IMAGE_TYPES,
  "application/pdf",
  "text/markdown",
];

const MAX_FILE_SIZE = 20 * 1024 * 1024; // 20MB

/**
 * Convert a File to a base64 string (strips data:...;base64, prefix).
 */
export async function fileToBase64(file: File): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const result = reader.result as string;
      resolve(result.split(",")[1]);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

/**
 * Convert a File to a ContentBlock for chat message payloads.
 *
 * For PDFs/Markdowns:
 * 1. Extract text (PDF via /api/extract-pdf-text, MD via base64 decode)
 * 2. Save extracted text to workspace via /api/upload-to-workspace
 * 3. Store both extractedText (for embedding in message) and workspacePath (for sub-agents)
 */
export async function fileToContentBlock(
  file: File,
  spaceId?: string,
): Promise<ContentBlock> {
  if (!SUPPORTED_FILE_TYPES.includes(file.type)) {
    toast.error(
      `Unsupported file type: ${file.type}. Supported: ${SUPPORTED_FILE_TYPES.join(", ")}`,
    );
    return Promise.reject(new Error(`Unsupported file type: ${file.type}`));
  }

  if (file.size > MAX_FILE_SIZE) {
    toast.error(`File too large: ${file.name} (${(file.size / 1024 / 1024).toFixed(1)}MB). Maximum size is 20MB.`);
    return Promise.reject(new Error(`File too large: ${file.name}`));
  }

  const data = await fileToBase64(file);

  if (SUPPORTED_IMAGE_TYPES.includes(file.type)) {
    return {
      type: "image",
      mimeType: file.type,
      data,
      metadata: { name: file.name },
    };
  }

  // PDF or Markdown
  const block: ContentBlock = {
    type: "file",
    mimeType: file.type || "application/pdf",
    data,
    metadata: { filename: file.name },
  };

  // Step 1: Extract text
  if (file.type === "application/pdf") {
    try {
      const resp = await fetch("/api/extract-pdf", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ data, filename: file.name }),
      });
      if (resp.ok) {
        const result = await resp.json();
        block.metadata!.extractedText = result.text || "";
      }
    } catch {
      // Extraction failed
    }
  } else if (file.type === "text/markdown") {
    try {
      // atob() doesn't handle UTF-8 — use TextDecoder for proper Chinese/Unicode support
      const binary = atob(data);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      block.metadata!.extractedText = new TextDecoder("utf-8").decode(bytes);
    } catch {
      block.metadata!.extractedText = "[Markdown decode failed]";
    }
  }

  // Step 2: Save extracted text to workspace (so sub-agents can read_file it)
  if (block.metadata!.extractedText) {
    try {
      const resp = await fetch("/api/upload-to-workspace", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          data,
          filename: file.name,
          mimeType: file.type,
          spaceId: spaceId || "default",
          agentName: "testcase",
        }),
      });
      if (resp.ok) {
        const result = await resp.json();
        block.metadata!.workspacePath = result.text_file_path || "";
      }
    } catch {
      // Save failed — sub-agents won't be able to read file from workspace
    }
  }

  return block;
}

export { SUPPORTED_FILE_TYPES, SUPPORTED_IMAGE_TYPES, MAX_FILE_SIZE };
