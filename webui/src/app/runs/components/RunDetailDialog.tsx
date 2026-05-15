"use client";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { format } from "date-fns";
import type { TestRunInfo } from "@/app/types/api";

const runStateLabels: Record<string, string> = {
  new_run: "新建",
  in_progress: "进行中",
  under_review: "评审中",
  rejected: "已拒绝",
  done: "完成",
  closed: "已关闭",
};

const runStateColors: Record<string, string> = {
  new_run: "bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200",
  in_progress: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  under_review: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
  rejected: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  done: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  closed: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
};

const statusColors: Record<string, string> = {
  passed: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  failed: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  skipped: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
  blocked: "bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200",
  not_executed: "bg-gray-50 text-gray-500 dark:bg-gray-800 dark:text-gray-400",
};

const statusLabels: Record<string, string> = {
  passed: "通过",
  failed: "失败",
  skipped: "跳过",
  blocked: "阻塞",
  not_executed: "未执行",
};

interface RunDetailDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  run: TestRunInfo | null;
}

const statCards = [
  { key: "passed_count", label: "通过", bg: "bg-green-50 dark:bg-green-950", text: "text-green-700 dark:text-green-300" },
  { key: "failed_count", label: "失败", bg: "bg-red-50 dark:bg-red-950", text: "text-red-700 dark:text-red-300" },
  { key: "skipped_count", label: "跳过", bg: "bg-yellow-50 dark:bg-yellow-950", text: "text-yellow-700 dark:text-yellow-300" },
  { key: "blocked_count", label: "阻塞", bg: "bg-gray-50 dark:bg-gray-900", text: "text-gray-700 dark:text-gray-300" },
  { key: "not_executed_count", label: "未执行", bg: "bg-gray-50 dark:bg-gray-800", text: "text-gray-500 dark:text-gray-400" },
] as const;

export function RunDetailDialog({ open, onOpenChange, run }: RunDetailDialogProps) {
  if (!run) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[700px] max-h-[80vh] overflow-auto">
        <DialogHeader>
          <div className="flex items-center gap-3">
            <DialogTitle>{run.name}</DialogTitle>
            <span className="font-mono text-sm text-muted-foreground">{run.identifier}</span>
            <Badge variant="outline" className={runStateColors[run.run_state] || ""}>
              {runStateLabels[run.run_state] || run.run_state}
            </Badge>
          </div>
          <DialogDescription>
            {run.description || "无描述"}
          </DialogDescription>
        </DialogHeader>

        {/* Stats summary */}
        <div className="grid grid-cols-5 gap-3">
          {statCards.map(({ key, label, bg, text }) => (
            <div key={key} className={`rounded-lg p-3 text-center ${bg}`}>
              <div className={`text-2xl font-bold ${text}`}>
                {run[key] as number}
              </div>
              <div className="text-xs text-muted-foreground mt-1">{label}</div>
            </div>
          ))}
        </div>

        <div className="text-sm text-muted-foreground">
          总用例数: {run.test_cases_count}
        </div>

        {/* Test run cases table */}
        {run.test_run_cases.length > 0 && (
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>用例 ID</TableHead>
                  <TableHead>最新状态</TableHead>
                  <TableHead>创建时间</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {run.test_run_cases.map((trc) => (
                  <TableRow key={trc.id}>
                    <TableCell className="font-mono text-xs">
                      {trc.test_case_id.slice(0, 8)}...
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className={statusColors[trc.latest_status] || ""}>
                        {statusLabels[trc.latest_status] || trc.latest_status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-sm">
                      {trc.created_at ? format(new Date(trc.created_at), "yyyy-MM-dd HH:mm") : "-"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        <DialogFooter showCloseButton>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            关闭
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
