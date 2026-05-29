"use client";

import { ColumnDef } from "@tanstack/react-table";
import Link from "next/link";
import type { TestCaseInfo } from "@/app/types/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Pencil, Trash2 } from "lucide-react";
import { format } from "date-fns";
import { formatUTCDate } from "@/lib/utils";

const priorityColors: Record<string, string> = {
  critical: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  high: "bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200",
  medium: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
  low: "bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200",
};

const stateLabels: Record<string, string> = {
  new: "新建",
  review_pending: "待评审",
  reviewed: "已评审",
  not_run: "未执行",
  passed: "通过",
  failed: "失败",
  blocked: "阻塞",
  skipped: "跳过",
};

export function createCaseColumns(
  onEdit: (testCase: TestCaseInfo) => void,
  onDelete: (testCase: TestCaseInfo) => void
): ColumnDef<TestCaseInfo>[] {
  return [
    {
      accessorKey: "identifier",
      header: "编号",
      cell: ({ row }) => (
        <span className="font-mono text-sm">{row.getValue("identifier")}</span>
      ),
    },
    {
      accessorKey: "name",
      header: "用例名称",
      cell: ({ row }) => (
        <Link
          href={`/cases/${row.original.id}`}
          className="text-sm text-primary hover:underline"
        >
          {row.getValue("name")}
        </Link>
      ),
    },
    {
      accessorKey: "priority",
      header: "优先级",
      cell: ({ row }) => {
        const priority = row.getValue("priority") as string;
        return (
          <Badge variant="outline" className={priorityColors[priority] || ""}>
            {priority}
          </Badge>
        );
      },
    },
    {
      accessorKey: "state",
      header: "状态",
      cell: ({ row }) => {
        const state = row.getValue("state") as string;
        return (
          <Badge variant="outline">
            {stateLabels[state] || state}
          </Badge>
        );
      },
    },
    {
      accessorKey: "template",
      header: "类型",
      cell: ({ row }) => {
        const template = row.getValue("template") as string;
        return template === "test_case_bdd" ? "BDD" : "标准";
      },
    },
    {
      accessorKey: "updated_at",
      header: "更新时间",
      cell: ({ row }) => {
        const val = row.getValue("updated_at") as string | null;
        return val ? formatUTCDate(val) : "-";
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
            onClick={() => onEdit(row.original)}
          >
            <Pencil className="h-4 w-4" />
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
}
