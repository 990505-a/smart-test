import { ContentBlock } from "@/app/types/types";
import { toast } from "sonner";

const SUPPORTED_IMAGE_TYPES = [
  "image/jpeg",
  "image/png",
  "image/gif",
  "image/webp",
];

const SUPPORTED_FILE_TYPES = [...SUPPORTED_IMAGE_TYPES, "application/pdf"];

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
 * Images become { type: "image" }, PDFs become { type: "file" }.
 */
export async function fileToContentBlock(
  file: File,
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

  // PDF
  return {
    type: "file",
    mimeType: file.type || "application/pdf",
    data,
    metadata: { filename: file.name },
  };
}

export { SUPPORTED_FILE_TYPES, SUPPORTED_IMAGE_TYPES, MAX_FILE_SIZE };
