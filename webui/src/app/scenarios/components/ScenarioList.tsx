"use client";

import { useState, useCallback } from "react";
import { DataTable } from "@/app/components/DataTable";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Plus, Play, Trash2, Eye } from "lucide-react";
import { ColumnDef } from "@tanstack/react-table";
import { Badge } from "@/components/ui/badge";
import {
  useScenarios,
  useCreateScenario,
  useDeleteScenario,
} from "@/lib/api/useScenarios";
import { executeScenario } from "@/lib/api/useScenarios";
import { useProjects } from "@/lib/api/useProjects";
import type { ScenarioInfo } from "@/app/types/api";

interface ScenarioListProps {
  onSelect: (scenario: ScenarioInfo) => void;
}

export function ScenarioList({ onSelect }: ScenarioListProps) {
  // Project selector
  const { data: projectsData } = useProjects(1, 100);
  const projects = projectsData?.data ?? [];
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const projectId = selectedProjectId || undefined;

  // Pagination & filters
  const [page, setPage] = useState(1);
  const pageSize = 30;
  const [statusFilter, setStatusFilter] = useState<string>("");

  // Data
  const { data, error, isLoading, mutate } = useScenarios(
    page,
    pageSize,
    projectId,
    statusFilter || undefined,
  );

  // Mutations
  const { trigger: createScenario, isMutating: isCreating } = useCreateScenario();
  const { trigger: deleteScenario, isMutating: isDeleting } = useDeleteScenario();

  // Dialogs
  const [createOpen, setCreateOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [selected, setSelected] = useState<ScenarioInfo | null>(null);

  // Create form
  const [createProjectId, setCreateProjectId] = useState("");
  const [createName, setCreateName] = useState("");
  const [createDesc, setCreateDesc] = useState("");

  const handleCreate = useCallback(async () => {
    if (!createProjectId || !createName.trim()) return;
    await createScenario({
      project_id: createProjectId,
      name: createName.trim(),
      description: createDesc || undefined,
    });
    setCreateOpen(false);
    setCreateName("");
    setCreateDesc("");
    setCreateProjectId("");
    mutate();
  }, [createProjectId, createName, createDesc, createScenario, mutate]);

  const handleDelete = useCallback(async () => {
    if (selected) {
      await deleteScenario(selected.id);
      setDeleteOpen(false);
      setSelected(null);
      mutate();
    }
  }, [selected, deleteScenario, mutate]);

  const handleExecute = useCallback(
    async (scenario: ScenarioInfo) => {
      await executeScenario(scenario.id);
      mutate();
    },
    [mutate],
  );

  const handleProjectChange = (val: string | null) => {
    setSelectedProjectId(val === "all" ? "" : (val ?? ""));
    setPage(1);
  };

  const statusBadge = (s: string) => {
    switch (s) {
      case "active":
      case "ready":
        return "bg-green-100 text-green-800";
      case "draft":
        return "bg-gray-100 text-gray-800";
      case "deprecated":
        return "bg-red-100 text-red-800";
      default:
        return "bg-blue-100 text-blue-800";
    }
  };

  const columns: ColumnDef<ScenarioInfo>[] = [
    {
      accessorKey: "identifier",
      header: "标识",
      cell: ({ getValue }) => (
        <span className="font-mono text-xs">{getValue() as string}</span>
      ),
    },
    {
      accessorKey: "name",
      header: "名称",
      cell: ({ row }) => (
        <button
          className="text-left hover:underline font-medium"
          onClick={() => onSelect(row.original)}
        >
          {row.original.name}
        </button>
      ),
    },
    {
      accessorKey: "status",
      header: "状态",
      cell: ({ getValue }) => {
        const s = getValue() as string;
        return <Badge className={statusBadge(s)}>{s}</Badge>;
      },
    },
    {
      accessorKey: "total_steps",
      header: "步骤数",
    },
    {
      accessorKey: "last_run_status",
      header: "最近执行",
      cell: ({ getValue }) => {
        const s = getValue() as string | null;
        return s ? (
          <Badge variant="outline">{s}</Badge>
        ) : (
          <span className="text-muted-foreground">-</span>
        );
      },
    },
    {
      accessorKey: "created_at",
      header: "创建时间",
      cell: ({ getValue }) =>
        new Date(getValue() as string).toLocaleDateString("zh-CN"),
    },
    {
      id: "actions",
      header: "操作",
      cell: ({ row }) => {
        const sc = row.original;
        return (
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="sm" onClick={() => onSelect(sc)} title="编辑">
              <Eye className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="sm" onClick={() => handleExecute(sc)} title="执行">
              <Play className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setSelected(sc);
                setDeleteOpen(true);
              }}
              title="删除"
            >
              <Trash2 className="h-4 w-4 text-destructive" />
            </Button>
          </div>
        );
      },
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h2 className="text-xl font-semibold">测试场景</h2>
          <Select value={selectedProjectId || null} onValueChange={handleProjectChange}>
            <SelectTrigger className="w-[200px]">
              <SelectValue placeholder="选择项目" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部项目</SelectItem>
              {projects.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button onClick={() => setCreateOpen(true)} size="sm" disabled={isCreating}>
          <Plus className="mr-2 h-4 w-4" />
          新建场景
        </Button>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3">
        <Select value={statusFilter || "all"} onValueChange={(v) => { setStatusFilter(v === "all" ? "" : (v ?? "")); setPage(1); }}>
          <SelectTrigger className="w-[150px]">
            <SelectValue placeholder="状态筛选" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部状态</SelectItem>
            <SelectItem value="draft">草稿</SelectItem>
            <SelectItem value="active">活跃</SelectItem>
            <SelectItem value="deprecated">废弃</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : error ? (
        <div className="flex flex-col items-center justify-center gap-2 py-8">
          <p className="text-destructive">加载失败</p>
          <Button variant="outline" size="sm" onClick={() => window.location.reload()}>
            重试
          </Button>
        </div>
      ) : !data?.data?.length ? (
        <div className="flex flex-col items-center justify-center gap-2 py-8">
          <p className="text-muted-foreground">暂无测试场景，点击新建按钮创建</p>
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            新建场景
          </Button>
        </div>
      ) : (
        <>
          <DataTable columns={columns} data={data.data} />
          {data.info && (
            <div className="flex items-center justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={!data.info.prev || page <= 1}
                onClick={() => setPage(page - 1)}
              >
                上一页
              </Button>
              <span className="text-sm text-muted-foreground">
                第 {data.info.page} 页 / 共{" "}
                {Math.ceil(data.info.total / data.info.page_size)} 页
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={!data.info.next}
                onClick={() => setPage(page + 1)}
              >
                下一页
              </Button>
            </div>
          )}
        </>
      )}

      {/* Create dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>新建测试场景</DialogTitle>
            <DialogDescription>
              创建一个新的测试场景，可在其中添加多个测试步骤。
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label>所属项目</Label>
              <Select value={createProjectId} onValueChange={(v) => { if (v) setCreateProjectId(v); }}>
                <SelectTrigger>
                  <SelectValue placeholder="选择项目" />
                </SelectTrigger>
                <SelectContent>
                  {projects.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="scName">场景名称</Label>
              <Input
                id="scName"
                placeholder="请输入场景名称"
                value={createName}
                onChange={(e) => setCreateName(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="scDesc">描述</Label>
              <Textarea
                id="scDesc"
                placeholder="可选描述"
                value={createDesc}
                onChange={(e) => setCreateDesc(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              取消
            </Button>
            <Button
              onClick={handleCreate}
              disabled={!createProjectId || !createName.trim() || isCreating}
            >
              {isCreating ? "创建中..." : "创建"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirmation */}
      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除</AlertDialogTitle>
            <AlertDialogDescription>
              确定删除测试场景 &quot;{selected?.name}&quot; 吗？此操作不可撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} disabled={isDeleting}>
              {isDeleting ? "删除中..." : "确定删除"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
