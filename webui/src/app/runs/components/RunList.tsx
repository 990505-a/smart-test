"use client";

import { ColumnDef } from "@tanstack/react-table";
import { DataTable } from "@/app/components/DataTable";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Eye, Trash2 } from "lucide-react";
import { format } from "date-fns";
import type { TestRunInfo } from "@/app/types/api";

const runStateColors: Record<string, string> = {
  new_run: "bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200",
  in_progress: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  under_review: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
  rejected: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  done: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  closed: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
};

const runStateLabels: Record<string, string> = {
  new_run: "新建",
  in_progress: "进行中",
  under_review: "评审中",
  rejected: "已拒绝",
  done: "完成",
  closed: "已关闭",
};

interface RunListProps {
  runs: TestRunInfo[];
  onViewDetail: (run: TestRunInfo) => void;
  onDelete: (run: TestRunInfo) => void;
  isLoading: boolean;
}

export function RunList({ runs, onViewDetail, onDelete, isLoading }: RunListProps) {
  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    );
  }

  if (runs.length === 0) {
    return (
      <div className="py-8 text-center text-muted-foreground">
        暂无测试执行记录
      </div>
    );
  }

  const columns: ColumnDef<TestRunInfo>[] = [
    {
      accessorKey: "identifier",
      header: "编号",
      cell: ({ row }) => (
        <span className="font-mono text-sm">{row.getValue("identifier")}</span>
      ),
    },
    {
      accessorKey: "name",
      header: "名称",
      cell: ({ row }) => (
        <span className="text-sm font-medium">{row.getValue("name")}</span>
      ),
    },
    {
      accessorKey: "run_state",
      header: "状态",
      cell: ({ row }) => {
        const state = row.getValue("run_state") as string;
        return (
          <Badge variant="outline" className={runStateColors[state] || ""}>
            {runStateLabels[state] || state}
          </Badge>
        );
      },
    },
    {
      accessorKey: "test_cases_count",
      header: "用例总数",
      cell: ({ row }) => (
        <span className="text-sm">{row.getValue("test_cases_count")}</span>
      ),
    },
    {
      id: "pass_rate",
      header: "通过率",
      cell: ({ row }) => {
        const { test_cases_count, passed_count } = row.original;
        const rate = test_cases_count > 0 ? ((passed_count / test_cases_count) * 100).toFixed(1) : "0.0";
        return <span className="text-sm">{rate}%</span>;
      },
    },
    {
      accessorKey: "created_at",
      header: "创建时间",
      cell: ({ row }) => {
        const val = row.getValue("created_at") as string;
        return val ? <span className="text-sm">{format(new Date(val), "yyyy-MM-dd HH:mm")}</span> : "-";
      },
    },
    {
      id: "actions",
      header: "操作",
      cell: ({ row }) => (
        <div className="flex gap-1">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => onViewDetail(row.original)}
          >
            <Eye className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => onDelete(row.original)}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      ),
    },
  ];

  return <DataTable columns={columns} data={runs} />;
}
