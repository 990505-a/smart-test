"use client";

import Link from "next/link";
import { CheckCircle2, XCircle, ExternalLink, HelpCircle } from "lucide-react";
import { cn } from "@/lib/utils";

export interface SaveResultData {
  status: "success" | "error" | "unconfirmed";
  document_name?: string;
  document_url?: string;
  revision?: number;
  lifecycle_status?: string;
  lint_status?: string;
  review_status?: string;
  project_name?: string;
  case_count?: number;
  // Legacy fields kept while old chat messages are still displayed.
  project_id?: string;
  identifiers?: string[];
  error?: string;
}

interface ToolResultCardProps {
  data: SaveResultData;
  className?: string;
}

export function ToolResultCard({ data, className }: ToolResultCardProps) {
  const isSuccess = data.status === "success";
  const isUnconfirmed = data.status === "unconfirmed";
  const documentName = data.document_name ?? data.project_name;

  return (
    <div
      className={cn(
        "my-3 flex items-start gap-3 rounded-lg border px-4 py-3",
        isSuccess
          ? "border-green-200 bg-green-50 dark:border-green-800 dark:bg-green-950/30"
          : isUnconfirmed
            ? "border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30"
            : "border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950/30",
        className
      )}
    >
      {isSuccess ? (
        <CheckCircle2 className="mt-0.5 h-5 w-5 flex-shrink-0 text-green-600 dark:text-green-400" />
      ) : isUnconfirmed ? (
        <HelpCircle className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-600 dark:text-amber-400" />
      ) : (
        <XCircle className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-600 dark:text-red-400" />
      )}
      <div className="min-w-0 flex-1">
        {isSuccess ? (
          <>
            <p className="m-0 text-sm font-medium text-green-800 dark:text-green-200">
              已保存 {data.case_count ?? 0} 条测试用例到「{documentName ?? "未命名文档"}」
            </p>
            {data.revision !== undefined && (
              <p className="m-0 mt-1 text-xs text-green-700 dark:text-green-300">
                草稿版本 v{data.revision}
                {data.lint_status ? ` · Lint ${data.lint_status}` : ""}
                {data.review_status ? ` · 评审 ${data.review_status}` : ""}
              </p>
            )}
            {data.identifiers && data.identifiers.length > 0 && (
              <p className="m-0 mt-1 text-xs text-green-700 dark:text-green-300">
                用例编号: {data.identifiers.slice(0, 5).join(", ")}
                {data.identifiers.length > 5 ? ` 等 ${data.identifiers.length} 条` : ""}
              </p>
            )}
            {(data.document_url || documentName) && (
              <Link
                href={data.document_url ?? `/cases?name=${encodeURIComponent(documentName ?? "")}`}
                className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-green-700 hover:text-green-900 dark:text-green-300 dark:hover:text-green-100"
              >
                <ExternalLink className="h-3 w-3" />
                在管理页面查看
              </Link>
            )}
          </>
        ) : isUnconfirmed ? (
          <>
            <p className="m-0 text-sm font-medium text-amber-800 dark:text-amber-200">
              保存结果未确认
            </p>
            <p className="m-0 mt-1 text-xs text-amber-700 dark:text-amber-300">
              {data.error ?? "请前往用例文档页面确认实际保存状态"}
            </p>
            {documentName && (
              <Link
                href={`/cases?name=${encodeURIComponent(documentName)}`}
                className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-amber-700 hover:text-amber-900 dark:text-amber-300 dark:hover:text-amber-100"
              >
                <ExternalLink className="h-3 w-3" />
                打开用例文档
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
    const data: SaveResultData = { status: "unconfirmed" };
    for (const line of block.split("\n")) {
      const trimmed = line.trim();
      if (trimmed.startsWith("status:")) data.status = trimmed.slice(7).trim() as "success" | "error";
      else if (trimmed.startsWith("document_name:")) data.document_name = trimmed.slice(15).trim();
      else if (trimmed.startsWith("document_url:")) data.document_url = trimmed.slice(14).trim();
      else if (trimmed.startsWith("revision:")) data.revision = parseInt(trimmed.slice(9).trim(), 10);
      else if (trimmed.startsWith("lifecycle_status:")) data.lifecycle_status = trimmed.slice(17).trim();
      else if (trimmed.startsWith("lint_status:")) data.lint_status = trimmed.slice(12).trim();
      else if (trimmed.startsWith("review_status:")) data.review_status = trimmed.slice(14).trim();
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
