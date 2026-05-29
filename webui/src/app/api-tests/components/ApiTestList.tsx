"use client";

import { useState, useCallback } from "react";
import { DataTable } from "@/app/components/DataTable";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
import { Textarea } from "@/components/ui/textarea";
import { Plus, Search, Play, Trash2, Eye } from "lucide-react";
import { ColumnDef } from "@tanstack/react-table";
import { useApiTests, useCreateApiTest, useDeleteApiTest } from "@/lib/api/useApiTests";
import { useProjects } from "@/lib/api/useProjects";
import { triggerExecution } from "@/lib/api/useApiTests";
import { Badge } from "@/components/ui/badge";
import type { APITestInfo, APITestCreate } from "@/app/types/api";

interface ApiTestListProps {
  onSelectTest: (test: APITestInfo) => void;
}

export function ApiTestList({ onSelectTest }: ApiTestListProps) {
  // Project selector
  const { data: projectsData } = useProjects(1, 100);
  const projects = projectsData?.data ?? [];
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(
    projects[0]?.id ?? null,
  );

  // Resolve projectId once projects load
  const projectId = selectedProjectId || projects[0]?.id || null;

  // Pagination & filters
  const [page, setPage] = useState(1);
  const pageSize = 30;
  const [search, setSearch] = useState("");
  const [scriptFormat, setScriptFormat] = useState<string>("");

  // Data
  const { data, error, isLoading, mutate } = useApiTests(
    projectId,
    page,
    pageSize,
    search || undefined,
    scriptFormat || undefined,
  );

  // Mutations
  const { trigger: createTest, isMutating: isCreating } = useCreateApiTest(projectId);
  const { trigger: deleteTest, isMutating: isDeleting } = useDeleteApiTest(projectId);

  // Dialogs
  const [createOpen, setCreateOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [selectedTest, setSelectedTest] = useState<APITestInfo | null>(null);

  // Create form
  const [createName, setCreateName] = useState("");
  const [createDesc, setCreateDesc] = useState("");
  const [createSchemaUrl, setCreateSchemaUrl] = useState("");

  const handleCreateSubmit = useCallback(async () => {
    if (!projectId || !createName.trim()) return;
    const payload: APITestCreate = {
      project_id: projectId,
      name: createName.trim(),
      description: createDesc || undefined,
      schema_url: createSchemaUrl || undefined,
    };
    await createTest(payload);
    setCreateOpen(false);
    setCreateName("");
    setCreateDesc("");
    setCreateSchemaUrl("");
    mutate();
  }, [projectId, createName, createDesc, createSchemaUrl, createTest, mutate]);

  const handleDelete = useCallback(async () => {
    if (selectedTest) {
      await deleteTest(selectedTest.id);
      setDeleteOpen(false);
      setSelectedTest(null);
      mutate();
    }
  }, [selectedTest, deleteTest, mutate]);

  const handleRun = useCallback(
    async (test: APITestInfo) => {
      await triggerExecution(test.project_id, test.id);
      mutate();
    },
    [mutate],
  );

  const handleProjectChange = (val: string | null) => {
    if (val) {
      setSelectedProjectId(val);
      setPage(1);
    }
  };

  // Table columns
  const columns: ColumnDef<APITestInfo>[] = [
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
          onClick={() => onSelectTest(row.original)}
        >
          {row.original.name}
        </button>
      ),
    },
    {
      accessorKey: "script_format",
      header: "脚本格式",
      cell: ({ getValue }) => (
        <Badge variant="secondary">{getValue() as string}</Badge>
      ),
    },
    {
      accessorKey: "total_endpoints",
      header: "端点数",
    },
    {
      accessorKey: "total_scenarios",
      header: "场景数",
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
        const test = row.original;
        return (
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onSelectTest(test)}
              title="查看详情"
            >
              <Eye className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => handleRun(test)}
              title="执行测试"
            >
              <Play className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setSelectedTest(test);
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
          <h2 className="text-xl font-semibold">API测试</h2>
          <Select value={selectedProjectId ?? null} onValueChange={handleProjectChange}>
            <SelectTrigger className="w-[200px]">
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
        <Button onClick={() => setCreateOpen(true)} size="sm" disabled={isCreating}>
          <Plus className="mr-2 h-4 w-4" />
          新建API测试
        </Button>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="搜索测试名称..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            className="pl-9"
          />
        </div>
        <Select value={scriptFormat} onValueChange={(v) => { setScriptFormat(v === "all" ? "" : (v ?? "")); setPage(1); }}>
          <SelectTrigger className="w-[150px]">
            <SelectValue placeholder="脚本格式" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部格式</SelectItem>
            <SelectItem value="playwright">Playwright</SelectItem>
            <SelectItem value="pytest">Pytest</SelectItem>
            <SelectItem value="supertest">Supertest</SelectItem>
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
          <p className="text-muted-foreground">暂无API测试，点击新建按钮创建</p>
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            新建API测试
          </Button>
        </div>
      ) : (
        <>
          <DataTable columns={columns} data={data.data} />

          {/* Pagination */}
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
            <DialogTitle>新建API测试</DialogTitle>
            <DialogDescription>
              创建一个新的API测试配置。
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="testName">测试名称</Label>
              <Input
                id="testName"
                placeholder="请输入测试名称"
                value={createName}
                onChange={(e) => setCreateName(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="testDesc">描述</Label>
              <Textarea
                id="testDesc"
                placeholder="可选描述"
                value={createDesc}
                onChange={(e) => setCreateDesc(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="schemaUrl">Schema URL</Label>
              <Input
                id="schemaUrl"
                placeholder="https://example.com/openapi.json"
                value={createSchemaUrl}
                onChange={(e) => setCreateSchemaUrl(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              取消
            </Button>
            <Button
              onClick={handleCreateSubmit}
              disabled={!createName.trim() || isCreating}
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
              确定删除API测试 &quot;{selectedTest?.name}&quot; 吗？此操作不可撤销。
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
