"use client";

import { useState, useCallback, useMemo } from "react";
import { ManagementLayout } from "@/app/components/ManagementLayout";
import { DataTable } from "@/app/components/DataTable";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Plus, ChevronLeft, ChevronRight } from "lucide-react";
import { useProjects } from "@/lib/api/useProjects";
import { useFolderTree } from "@/lib/api/useFolders";
import { useTestCases, useCreateTestCase, useDeleteTestCase } from "@/lib/api/useTestCases";
import { createCaseColumns } from "./components/CaseColumns";
import { CreateCaseDialog } from "./components/CreateCaseDialog";
import type { TestCaseInfo, TestCaseCreate } from "@/app/types/api";

export default function CasesPage() {
  // Project selector state
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const { data: projectsData } = useProjects(1, 100);
  const projects = projectsData?.data ?? [];

  // Folder filter
  const [selectedFolderId, setSelectedFolderId] = useState<string | null>(null);
  const { data: folderTreeResponse } = useFolderTree(selectedProjectId);
  const folderTree = folderTreeResponse?.data ?? [];

  // Pagination
  const [page, setPage] = useState(1);
  const pageSize = 30;

  // Test case data
  const { data: casesData, isLoading, error } = useTestCases(page, pageSize, selectedProjectId ?? undefined, selectedFolderId ?? undefined);
  const testCases = casesData?.data ?? [];
  const info = casesData?.info;

  // Mutations
  const { trigger: createCase, isMutating: isCreating } = useCreateTestCase();
  const { trigger: deleteCase, isMutating: isDeleting } = useDeleteTestCase();

  // Dialog states
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [selectedCase, setSelectedCase] = useState<TestCaseInfo | null>(null);

  const handleCreateCase = useCallback(
    async (data: TestCaseCreate) => {
      await createCase(data);
    },
    [createCase]
  );

  const handleDeleteCase = useCallback(async () => {
    if (selectedCase) {
      await deleteCase(selectedCase.id);
      setDeleteDialogOpen(false);
      setSelectedCase(null);
    }
  }, [selectedCase, deleteCase]);

  const handleEdit = useCallback((testCase: TestCaseInfo) => {
    // Navigate to edit page via Link in column definition
    window.location.href = `/cases/${testCase.id}`;
  }, []);

  const handleDelete = useCallback((testCase: TestCaseInfo) => {
    setSelectedCase(testCase);
    setDeleteDialogOpen(true);
  }, []);

  const columns = useMemo(
    () => createCaseColumns(handleEdit, handleDelete),
    [handleEdit, handleDelete]
  );

  // Reset page when project/folder changes
  const handleProjectChange = (val: string | null) => {
    setSelectedProjectId(val);
    setSelectedFolderId(null);
    setPage(1);
  };

  return (
    <ManagementLayout>
      <div className="space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <h2 className="text-2xl font-bold">测试用例</h2>
            <Select value={selectedProjectId ?? ""} onValueChange={handleProjectChange}>
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
            {selectedProjectId && (
              <Select value={selectedFolderId ?? "all"} onValueChange={(val) => { setSelectedFolderId(val === "all" ? null : val); setPage(1); }}>
                <SelectTrigger>
                  <SelectValue placeholder="所有文件夹" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">所有文件夹</SelectItem>
                  {flattenForSelect(folderTree).map((f) => (
                    <SelectItem key={f.id} value={f.id}>
                      {"  ".repeat(f.depth)} {f.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>
          <Button
            onClick={() => setCreateDialogOpen(true)}
            disabled={!selectedProjectId || isCreating}
          >
            <Plus className="mr-2 h-4 w-4" />
            新建用例
          </Button>
        </div>

        {/* Table content */}
        {!selectedProjectId ? (
          <div className="py-8 text-center text-muted-foreground">
            请先选择一个项目
          </div>
        ) : isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : error ? (
          <div className="py-8 text-center">
            <p className="text-destructive">加载失败</p>
            <Button variant="outline" className="mt-2" onClick={() => window.location.reload()}>
              重试
            </Button>
          </div>
        ) : testCases.length === 0 ? (
          <div className="py-8 text-center text-muted-foreground">
            暂无用例，点击新建用例按钮创建
          </div>
        ) : (
          <>
            <DataTable columns={columns} data={testCases} />

            {/* Pagination */}
            {info && (
              <div className="flex items-center justify-between">
                <p className="text-sm text-muted-foreground">
                  共 {info.total} 条，第 {info.page} / {Math.ceil(info.total / info.page_size)} 页
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!info.prev}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                  >
                    <ChevronLeft className="mr-1 h-4 w-4" />
                    上一页
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!info.next}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    下一页
                    <ChevronRight className="ml-1 h-4 w-4" />
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Create dialog */}
      <CreateCaseDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
        onSubmit={handleCreateCase}
        projectId={selectedProjectId ?? ""}
        folders={folderTree}
      />

      {/* Delete confirmation */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除</AlertDialogTitle>
            <AlertDialogDescription>
              确定要删除用例 &quot;{selectedCase?.name}&quot; 吗？此操作不可撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteCase} disabled={isDeleting}>
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </ManagementLayout>
  );
}

/** Helper to flatten folder tree for select dropdown */
function flattenForSelect(nodes: Array<{ id: string; name: string; children?: Array<{ id: string; name: string; children?: unknown[] }> }>, depth = 0): Array<{ id: string; name: string; depth: number }> {
  const result: Array<{ id: string; name: string; depth: number }> = [];
  for (const node of nodes) {
    result.push({ id: node.id, name: node.name, depth });
    if (node.children?.length) {
      result.push(...flattenForSelect(node.children as Array<{ id: string; name: string; children?: Array<{ id: string; name: string; children?: unknown[] }> }>, depth + 1));
    }
  }
  return result;
}
