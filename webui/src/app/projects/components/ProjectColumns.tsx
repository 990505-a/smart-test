"use client";

import { ColumnDef } from "@tanstack/react-table";
import type { ProjectInfo } from "@/app/types/api";
import { Button } from "@/components/ui/button";
import { Pencil, Trash2 } from "lucide-react";
import { format } from "date-fns";

export function createProjectColumns(
  onEdit: (project: ProjectInfo) => void,
  onDelete: (project: ProjectInfo) => void
): ColumnDef<ProjectInfo>[] {
  return [
    {
      accessorKey: "identifier",
      header: "标识符",
      cell: ({ row }) => <span className="font-mono text-sm">{row.getValue("identifier")}</span>,
    },
    {
      accessorKey: "name",
      header: "项目名称",
    },
    {
      accessorKey: "description",
      header: "描述",
      cell: ({ row }) => row.getValue("description") || "-",
    },
    {
      accessorKey: "created_at",
      header: "创建时间",
      cell: ({ row }) => format(new Date(row.getValue("created_at")), "yyyy-MM-dd HH:mm"),
    },
    {
      id: "actions",
      header: "操作",
      cell: ({ row }) => (
        <div className="flex gap-1">
          <Button variant="ghost" size="icon" onClick={() => onEdit(row.original)}>
            <Pencil className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" onClick={() => onDelete(row.original)}>
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      ),
    },
  ];
}
