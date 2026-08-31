"use client";

/**
 * Shared page-level UI primitives — one place for the patterns every
 * management page uses, so headers, statuses, empty states and pagination
 * stay identical across the app.
 */

import React from "react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight, Inbox } from "lucide-react";

// ---------------------------------------------------------------------------
// PageHeader — consistent title / description / actions row
// ---------------------------------------------------------------------------

export function PageHeader({
  title,
  description,
  actions,
  className,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("mb-6 flex flex-wrap items-start justify-between gap-3", className)}>
      <div className="min-w-0">
        <h1 className="text-xl font-semibold leading-8 tracking-tight">{title}</h1>
        {description && (
          <p className="mt-0.5 text-sm leading-6 text-muted-foreground">{description}</p>
        )}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// StatusBadge — one registry for raw enum values → Chinese label + tone
// ---------------------------------------------------------------------------

export type StatusTone = "neutral" | "info" | "success" | "warning" | "danger" | "brand";

const TONE_CLASS: Record<StatusTone, string> = {
  neutral: "bg-secondary text-secondary-foreground",
  info: "bg-muted text-muted-foreground",
  success: "bg-success/12 text-success",
  warning: "bg-warning/12 text-warning",
  danger: "bg-destructive/10 text-destructive",
  brand: "bg-brand/10 text-brand",
};

/** Central registry: add new raw values here instead of inlining maps in pages. */
const STATUS_MAP: Record<string, { label: string; tone: StatusTone }> = {
  // generic
  active: { label: "运行中", tone: "brand" },
  running: { label: "运行中", tone: "brand" },
  pending: { label: "待处理", tone: "neutral" },
  queued: { label: "排队中", tone: "info" },
  completed: { label: "已完成", tone: "success" },
  success: { label: "成功", tone: "success" },
  passed: { label: "通过", tone: "success" },
  ok: { label: "正常", tone: "success" },
  connected: { label: "已连接", tone: "success" },
  failed: { label: "失败", tone: "danger" },
  error: { label: "错误", tone: "danger" },
  broken: { label: "异常", tone: "danger" },
  disconnected: { label: "未连接", tone: "danger" },
  cancelled: { label: "已取消", tone: "info" },
  repairing: { label: "修复中", tone: "warning" },
  skipped: { label: "已跳过", tone: "info" },
  // api-auto scripts / runs
  draft: { label: "草稿", tone: "neutral" },
  ready: { label: "就绪", tone: "info" },
  // review batches / verdicts
  in_review: { label: "评审中", tone: "brand" },
  annotated: { label: "已标注", tone: "info" },
  evolving: { label: "进化中", tone: "warning" },
  released: { label: "已外发", tone: "brand" },
  reviewing: { label: "回看中", tone: "info" },
  done: { label: "已完成", tone: "success" },
  good: { label: "好", tone: "success" },
  bad: { label: "坏", tone: "danger" },
  unmarked: { label: "未标注", tone: "neutral" },
  confirmed: { label: "已确认", tone: "info" },
  overturned: { label: "已推翻", tone: "warning" },
  lint_failed: { label: "Lint 未通过", tone: "danger" },
  lint_passed: { label: "Lint 已通过", tone: "success" },
  changes_requested: { label: "需要修改", tone: "warning" },
  approved: { label: "已批准", tone: "success" },
  release_blocked: { label: "发布受阻", tone: "danger" },
  // api-auto scripts / rag documents
  archived: { label: "已归档", tone: "info" },
  parsed: { label: "已解析", tone: "success" },
  processed: { label: "已处理", tone: "success" },
};

export function StatusBadge({
  status,
  fallbackLabel,
  className,
}: {
  status: string | null | undefined;
  /** shown when the raw value isn't in the registry */
  fallbackLabel?: string;
  className?: string;
}) {
  const raw = (status ?? "").trim();
  const entry = STATUS_MAP[raw.toLowerCase()] ?? (raw ? { label: fallbackLabel ?? raw, tone: "neutral" as StatusTone } : null);
  if (!entry) return null;
  return (
    <Badge variant="secondary" className={cn("font-normal", TONE_CLASS[entry.tone], className)}>
      {entry.label}
    </Badge>
  );
}

// ---------------------------------------------------------------------------
// EmptyState — icon + title + description + optional action
// ---------------------------------------------------------------------------

export function EmptyState({
  title,
  description,
  action,
  icon: Icon = Inbox,
  className,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  icon?: React.ComponentType<{ className?: string }>;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-1.5 rounded-xl border border-dashed py-16 text-center", className)}>
      <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-muted">
        <Icon className="h-5 w-5 text-muted-foreground" />
      </div>
      <p className="text-sm font-medium">{title}</p>
      {description && (
        <p className="max-w-sm text-[13px] leading-5 text-muted-foreground">{description}</p>
      )}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pagination — total on the left, prev/next on the right
// ---------------------------------------------------------------------------

export function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
  className,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  className?: string;
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className={cn("flex items-center justify-between pt-1 text-[13px] text-muted-foreground", className)}>
      <span>共 {total} 条</span>
      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="tabular-nums">
          {page} / {totalPages}
        </span>
        <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
