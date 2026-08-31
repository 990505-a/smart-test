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

/** Lifecycle stages surfaced to the upload-progress UI. */
export type UploadStage = "reading" | "uploading" | "processing";

export type UploadStageListener = (
  stage: UploadStage,
  progress?: number,
) => void;

/**
 * POST JSON with real upload progress. fetch() cannot report request-body
 * progress, so use XHR's upload.onprogress — the only browser API that can.
 */
function postJsonWithProgress(
  url: string,
  body: string,
  onProgress?: (fraction: number) => void,
): Promise<{ ok: boolean; json: () => Promise<Record<string, unknown>> }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress && e.total > 0) {
        onProgress(Math.min(1, e.loaded / e.total));
      }
    };
    xhr.onload = () => {
      let parsed: Record<string, unknown> = {};
      try {
        parsed = xhr.responseText ? JSON.parse(xhr.responseText) as Record<string, unknown> : {};
      } catch {
        parsed = {};
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve({ ok: true, json: () => Promise.resolve(parsed) });
      } else {
        const detail =
          typeof parsed.error === "string" ? `: ${parsed.error}` : "";
        reject(new Error(`上传失败（HTTP ${xhr.status}）${detail}`));
      }
    };
    xhr.onerror = () => reject(new Error("网络错误，上传失败"));
    xhr.send(body);
  });
}

/**
 * Convert a File to a ContentBlock for chat message payloads.
 *
 * For PDFs/Markdowns: single round-trip to /api/upload-to-workspace.
 * The backend extracts text, saves the original + .txt sidecar to the
 * workspace and returns virtual paths — stored in workspacePath so the
 * agent can read_file them. Full text is intentionally NOT embedded in
 * the message to avoid thread state bloat.
 *
 * onStage reports upload lifecycle for progress UI; upload failures throw
 * (the caller decides how to surface them) instead of silently producing
 * an unreadable path-less block.
 */
export async function fileToContentBlock(
  file: File,
  spaceId?: string,
  threadId?: string,
  onStage?: UploadStageListener,
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

  onStage?.("reading");
  const data = await fileToBase64(file);

  if (SUPPORTED_IMAGE_TYPES.includes(file.type)) {
    // Images ride inline with the next message — no server hop needed.
    return {
      type: "image",
      mimeType: file.type,
      data,
      metadata: { name: file.name },
    };
  }

  // PDF / Markdown: upload original file once — the backend extracts text,
  // saves a .txt sidecar in the workspace and returns path references.
  const block: ContentBlock = {
    type: "file",
    mimeType: file.type || "application/pdf",
    data,
    metadata: { filename: file.name },
  };

  onStage?.("uploading", 0);
  const resp = await postJsonWithProgress(
    "/api/upload-to-workspace",
    JSON.stringify({
      data,
      filename: file.name,
      mimeType: file.type,
      spaceId: spaceId || "default",
      agentName: "testcase",
      threadId: threadId || "",
    }),
    (fraction) => onStage?.("uploading", fraction),
  );
  // Body sent — server-side text extraction still takes a moment.
  onStage?.("processing");
  const result = await resp.json();
  block.metadata!.workspacePath =
    (result.text_file_path as string) ||
    (result.workspace_path as string) ||
    "";

  return block;
}

export { SUPPORTED_FILE_TYPES, SUPPORTED_IMAGE_TYPES, MAX_FILE_SIZE };
