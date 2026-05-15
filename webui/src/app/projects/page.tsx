"use client";

import React, { useState } from "react";
import { ManagementLayout } from "@/app/components/ManagementLayout";
import { DataTable } from "@/app/components/DataTable";
import { useProjects, useCreateProject, useUpdateProject, useDeleteProject } from "@/lib/api/useProjects";
import { createProjectColumns } from "@/app/projects/components/ProjectColumns";
import { CreateProjectDialog } from "@/app/projects/components/CreateProjectDialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogAction,
  AlertDialogCancel,
} from "@/components/ui/alert-dialog";
import { Plus } from "lucide-react";
import type { ProjectInfo, ProjectCreate, ProjectUpdate } from "@/app/types/api";

export default function ProjectsPage() {
  const [page, setPage] = useState(1);
  const pageSize = 30;

  const { data, error, isLoading } = useProjects(page, pageSize);
  const { trigger: createProject, isMutating: isCreating } = useCreateProject();
  const { trigger: updateProject, isMutating: isUpdating } = useUpdateProject();
  const { trigger: deleteProject, isMutating: isDeleting } = useDeleteProject();

  // Dialog states
  const [createOpen, setCreateOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [selectedProject, setSelectedProject] = useState<ProjectInfo | null>(null);

  const handleEdit = (project: ProjectInfo) => {
    setSelectedProject(project);
    setEditOpen(true);
  };

  const handleDelete = (project: ProjectInfo) => {
    setSelectedProject(project);
    setDeleteOpen(true);
  };

  const handleCreateSubmit = async (formData: ProjectCreate | { identifier: string; data: ProjectUpdate }) => {
    await createProject(formData as ProjectCreate);
  };

  const handleEditSubmit = async (formData: ProjectCreate | { identifier: string; data: ProjectUpdate }) => {
    await updateProject(formData as { identifier: string; data: ProjectUpdate });
  };

  const handleDeleteConfirm = async () => {
    if (selectedProject) {
      await deleteProject(selectedProject.identifier);
      setDeleteOpen(false);
      setSelectedProject(null);
    }
  };

  const columns = createProjectColumns(handleEdit, handleDelete);

  return (
    <ManagementLayout>
      <div className="flex flex-col gap-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold">项目列表</h2>
          <Button onClick={() => setCreateOpen(true)} size="sm" disabled={isCreating || isUpdating}>
            <Plus className="mr-2 h-4 w-4" />
            新建项目
          </Button>
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
            <p className="text-muted-foreground">暂无项目，点击新建项目按钮创建</p>
            <Button size="sm" onClick={() => setCreateOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              新建项目
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
                  第 {data.info.page} 页 / 共 {Math.ceil(data.info.total / data.info.page_size)} 页
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
      </div>

      {/* Create dialog */}
      <CreateProjectDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onSubmit={handleCreateSubmit}
        mode="create"
      />

      {/* Edit dialog */}
      <CreateProjectDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        onSubmit={handleEditSubmit}
        initialData={selectedProject}
        mode="edit"
      />

      {/* Delete confirmation */}
      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除</AlertDialogTitle>
            <AlertDialogDescription>
              确定删除该项目吗？此操作不可撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteConfirm}
              disabled={isDeleting}
            >
              {isDeleting ? "删除中..." : "确定删除"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </ManagementLayout>
  );
}
