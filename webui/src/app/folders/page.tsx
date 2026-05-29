"use client";

import { useState, useCallback } from "react";
import { ManagementLayout } from "@/app/components/ManagementLayout";
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
import { Plus } from "lucide-react";
import { useProjects } from "@/lib/api/useProjects";
import { useFolderTree, useCreateFolder, useUpdateFolder, useDeleteFolder } from "@/lib/api/useFolders";
import { FolderTree } from "./components/FolderTree";
import { CreateFolderDialog } from "./components/CreateFolderDialog";
import type { FolderTreeNode, FolderCreate, FolderUpdate } from "@/app/types/api";

export default function FoldersPage() {
  // Project selector state
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const { data: projectsData, isLoading: projectsLoading } = useProjects(1, 100);
  const projects = projectsData?.data ?? [];

  // Folder data
  const { data: treeResponse, isLoading: treeLoading, error: treeError } = useFolderTree(selectedProjectId);
  const folderTree = treeResponse?.data ?? [];

  // Mutations
  const { trigger: createFolder, isMutating: isCreating } = useCreateFolder();
  const { trigger: updateFolder, isMutating: isUpdating } = useUpdateFolder();
  const { trigger: deleteFolder, isMutating: isDeleting } = useDeleteFolder();

  // Dialog states
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [selectedFolder, setSelectedFolder] = useState<FolderTreeNode | null>(null);

  const handleCreateFolder = useCallback(
    async (data: FolderCreate | { id: string; data: FolderUpdate }) => {
      if ("project_id" in data) {
        await createFolder(data as FolderCreate);
      }
    },
    [createFolder]
  );

  const handleEditFolder = useCallback(
    async (data: FolderCreate | { id: string; data: FolderUpdate }) => {
      if ("id" in data) {
        await updateFolder(data as { id: string; data: FolderUpdate });
      }
    },
    [updateFolder]
  );

  const handleDeleteFolder = useCallback(async () => {
    if (selectedFolder) {
      await deleteFolder(selectedFolder.id);
      setDeleteDialogOpen(false);
      setSelectedFolder(null);
    }
  }, [selectedFolder, deleteFolder]);

  const handleReorder = useCallback(
    async (id: string, _newParentId: string | null, _newIndex: number) => {
      // For basic same-level reorder, update the folder position
      // The backend may need a position field or index-based ordering
      // For now, we just trigger a visual reorder via drag-drop
      // Full implementation would call updateFolder with new position data
      console.log("Reorder folder", id, "to index", _newIndex);
    },
    []
  );

  const handleEdit = useCallback((node: FolderTreeNode) => {
    setSelectedFolder(node);
    setEditDialogOpen(true);
  }, []);

  const handleDelete = useCallback((node: FolderTreeNode) => {
    setSelectedFolder(node);
    setDeleteDialogOpen(true);
  }, []);

  return (
    <ManagementLayout>
      <div className="space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <h2 className="text-2xl font-bold">文件夹管理</h2>
            <Select
              value={selectedProjectId ?? null}
              onValueChange={setSelectedProjectId}
            >
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
          <Button
            onClick={() => setCreateDialogOpen(true)}
            disabled={!selectedProjectId || isCreating}
          >
            <Plus className="mr-2 h-4 w-4" />
            新建文件夹
          </Button>
        </div>

        {/* Folder tree content */}
        {!selectedProjectId ? (
          <div className="py-8 text-center text-muted-foreground">
            请先选择一个项目
          </div>
        ) : treeLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-3/4" />
            <Skeleton className="h-8 w-1/2" />
          </div>
        ) : treeError ? (
          <div className="py-8 text-center">
            <p className="text-destructive">加载失败</p>
            <Button variant="outline" className="mt-2" onClick={() => window.location.reload()}>
              重试
            </Button>
          </div>
        ) : (
          <FolderTree
            nodes={folderTree}
            onEdit={handleEdit}
            onDelete={handleDelete}
            onReorder={handleReorder}
          />
        )}
      </div>

      {/* Create dialog */}
      <CreateFolderDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
        onSubmit={handleCreateFolder}
        mode="create"
        projectId={selectedProjectId ?? ""}
        parentFolders={folderTree}
      />

      {/* Edit dialog */}
      <CreateFolderDialog
        open={editDialogOpen}
        onOpenChange={setEditDialogOpen}
        onSubmit={handleEditFolder}
        initialData={selectedFolder}
        mode="edit"
        projectId={selectedProjectId ?? ""}
        parentFolders={folderTree}
      />

      {/* Delete confirmation */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除</AlertDialogTitle>
            <AlertDialogDescription>
              确定要删除文件夹 &quot;{selectedFolder?.name}&quot; 吗？此操作不可撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteFolder}
              disabled={isDeleting}
            >
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </ManagementLayout>
  );
}
