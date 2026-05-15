"use client";

import Link from "next/link";
import { CheckCircle2, XCircle, ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";

export interface SaveResultData {
  status: "success" | "error";
  project_id?: string;
  project_name?: string;
  case_count?: number;
  identifiers?: string[];
  error?: string;
}

interface ToolResultCardProps {
  data: SaveResultData;
  className?: string;
}

export function ToolResultCard({ data, className }: ToolResultCardProps) {
  const isSuccess = data.status === "success";

  return (
    <div
      className={cn(
        "my-3 flex items-start gap-3 rounded-lg border px-4 py-3",
        isSuccess
          ? "border-green-200 bg-green-50 dark:border-green-800 dark:bg-green-950/30"
          : "border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950/30",
        className
      )}
    >
      {isSuccess ? (
        <CheckCircle2 className="mt-0.5 h-5 w-5 flex-shrink-0 text-green-600 dark:text-green-400" />
      ) : (
        <XCircle className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-600 dark:text-red-400" />
      )}
      <div className="min-w-0 flex-1">
        {isSuccess ? (
          <>
            <p className="m-0 text-sm font-medium text-green-800 dark:text-green-200">
              已保存 {data.case_count ?? 0} 条测试用例到项目「{data.project_name ?? "未命名项目"}」
            </p>
            {data.identifiers && data.identifiers.length > 0 && (
              <p className="m-0 mt-1 text-xs text-green-700 dark:text-green-300">
                用例编号: {data.identifiers.slice(0, 5).join(", ")}
                {data.identifiers.length > 5 ? ` 等 ${data.identifiers.length} 条` : ""}
              </p>
            )}
            {data.project_id && (
              <Link
                href={`/cases?project=${data.project_id}`}
                className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-green-700 hover:text-green-900 dark:text-green-300 dark:hover:text-green-100"
              >
                <ExternalLink className="h-3 w-3" />
                在管理页面查看
              </Link>
            )}
          </>
        ) : (
          <>
            <p className="m-0 text-sm font-medium text-red-800 dark:text-red-200">
              保存失败
            </p>
            <p className="m-0 mt-1 text-xs text-red-700 dark:text-red-300">
              {data.error ?? "未知错误，请稍后重试"}
            </p>
          </>
        )}
      </div>
    </div>
  );
}

const SAVE_RESULT_REGEX = /\[SAVE_RESULT\]\s*\n([\s\S]*?)\n\[\/SAVE_RESULT\]/g;

export function parseSaveResults(content: string): SaveResultData[] {
  const results: SaveResultData[] = [];
  let match: RegExpExecArray | null;
  while ((match = SAVE_RESULT_REGEX.exec(content)) !== null) {
    const block = match[1];
    const data: SaveResultData = { status: "success" };
    for (const line of block.split("\n")) {
      const trimmed = line.trim();
      if (trimmed.startsWith("status:")) data.status = trimmed.slice(7).trim() as "success" | "error";
      else if (trimmed.startsWith("project_id:")) data.project_id = trimmed.slice(11).trim();
      else if (trimmed.startsWith("project_name:")) data.project_name = trimmed.slice(14).trim();
      else if (trimmed.startsWith("case_count:")) data.case_count = parseInt(trimmed.slice(11).trim(), 10);
      else if (trimmed.startsWith("identifiers:")) data.identifiers = trimmed.slice(13).trim().split(",").map(s => s.trim()).filter(Boolean);
      else if (trimmed.startsWith("error:")) data.error = trimmed.slice(6).trim();
    }
    results.push(data);
  }
  return results;
}

/** Strip [SAVE_RESULT] blocks from content so they don't render as raw text */
export function stripSaveResultMarkers(content: string): string {
  return content.replace(SAVE_RESULT_REGEX, "").trim();
}
