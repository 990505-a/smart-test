"use client";

import { useState, useCallback } from "react";
import { PageHeader, EmptyState, Pagination } from "@/app/components/ui-patterns";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardHeader,
  CardContent,
  CardFooter,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Plus,
  Search,
  Pencil,
  Trash2,
  Loader2,
} from "lucide-react";
import {
  useMemories,
  useCreateMemory,
  useUpdateMemory,
  useDeleteMemory,
} from "@/lib/api/useMemories";
import type { MemoryInfo, MemoryCreate, MemoryUpdate } from "@/lib/api/useMemories";

const CATEGORY_OPTIONS = [
  { value: "preference", label: "偏好" },
  { value: "domain_knowledge", label: "领域知识" },
  { value: "project_context", label: "项目上下文" },
  { value: "convention", label: "约定" },
] as const;

function getCategoryLabel(category: string | null): string {
  if (!category) return "未分类";
  const found = CATEGORY_OPTIONS.find((o) => o.value === category);
  return found ? found.label : category;
}

function getCategoryBadgeVariant(
  category: string | null
): "default" | "secondary" | "outline" {
  switch (category) {
    case "preference":
      return "default";
    case "domain_knowledge":
      return "secondary";
    case "project_context":
      return "outline";
    default:
      return "outline";
  }
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "-";
  try {
    return new Date(dateStr).toLocaleString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return dateStr;
  }
}

// === Memory Form Dialog (shared between create and edit) ===
function MemoryFormDialog({
  open,
  onOpenChange,
  title,
  initialValues,
  onSubmit,
  isSubmitting,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  initialValues: { key: string; content: string; category: string };
  onSubmit: (data: MemoryCreate) => Promise<void>;
  isSubmitting: boolean;
}) {
  const [formKey, setFormKey] = useState(initialValues.key);
  const [formContent, setFormContent] = useState(initialValues.content);
  const [formCategory, setFormCategory] = useState(initialValues.category);

  // Reset form when dialog opens with new initial values
  const handleOpenChange = useCallback(
    (nextOpen: boolean) => {
      if (nextOpen) {
        setFormKey(initialValues.key);
        setFormContent(initialValues.content);
        setFormCategory(initialValues.category);
      }
      onOpenChange(nextOpen);
    },
    [initialValues, onOpenChange]
  );

  const handleSubmit = useCallback(async () => {
    if (!formKey.trim() || !formContent.trim()) return;
    await onSubmit({
      key: formKey.trim(),
      content: formContent.trim(),
      category: formCategory || undefined,
    });
    onOpenChange(false);
  }, [formKey, formContent, formCategory, onSubmit, onOpenChange]);

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="memory-key">键 (Key)</Label>
            <Input
              id="memory-key"
              value={formKey}
              onChange={(e) => setFormKey(e.target.value)}
              placeholder="记忆的唯一标识键"
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="memory-content">内容 (Content)</Label>
            <Textarea
              id="memory-content"
              value={formContent}
              onChange={(e) => setFormContent(e.target.value)}
              placeholder="记忆内容"
              rows={4}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="memory-category">分类 (Category)</Label>
            <Select
              value={formCategory || "none"}
              onValueChange={(val) =>
                setFormCategory(val === "none" ? "" : (val ?? ""))
              }
            >
              <SelectTrigger id="memory-category">
                <SelectValue placeholder="选择分类" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">无分类</SelectItem>
                {CATEGORY_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isSubmitting}
          >
            取消
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!formKey.trim() || !formContent.trim() || isSubmitting}
          >
            {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            确定
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// === Main Page ===
export default function MemoriesPage() {
  // Filters
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [category, setCategory] = useState<string | null>(null);

  // Pagination
  const [page, setPage] = useState(1);
  const pageSize = 30;

  // Data
  const { data: memoriesData, isLoading, error } = useMemories(
    page,
    pageSize,
    category ?? undefined,
    search || undefined
  );
  const memories = memoriesData?.data ?? [];
  const info = memoriesData?.info;

  // Mutations
  const { trigger: createMemory, isMutating: isCreating } = useCreateMemory();
  const { trigger: updateMemory, isMutating: isUpdating } = useUpdateMemory();
  const { trigger: deleteMemory, isMutating: isDeleting } = useDeleteMemory();

  // Dialog states
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [selectedMemory, setSelectedMemory] = useState<MemoryInfo | null>(null);

  // Handlers
  const handleCreate = useCallback(
    async (data: MemoryCreate) => {
      await createMemory(data);
      setCreateDialogOpen(false);
    },
    [createMemory]
  );

  const handleUpdate = useCallback(
    async (data: MemoryCreate) => {
      if (!selectedMemory) return;
      const updateData: MemoryUpdate = {};
      if (data.key !== selectedMemory.key) updateData.key = data.key;
      if (data.content !== selectedMemory.content) updateData.content = data.content;
      if ((data.category ?? "") !== (selectedMemory.category ?? "")) updateData.category = data.category;
      await updateMemory({ id: selectedMemory.id, data: updateData });
      setEditDialogOpen(false);
      setSelectedMemory(null);
    },
    [selectedMemory, updateMemory]
  );

  const handleDelete = useCallback(async () => {
    if (!selectedMemory) return;
    await deleteMemory(selectedMemory.id);
    setDeleteDialogOpen(false);
    setSelectedMemory(null);
  }, [selectedMemory, deleteMemory]);

  const handleSearch = useCallback(() => {
    setSearch(searchInput);
    setPage(1);
  }, [searchInput]);

  const handleSearchKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter") {
        handleSearch();
      }
    },
    [handleSearch]
  );

  const handleCategoryChange = useCallback((val: string | null) => {
    setCategory(val === "all" ? null : val);
    setPage(1);
  }, []);

  const openEditDialog = useCallback((memory: MemoryInfo) => {
    setSelectedMemory(memory);
    setEditDialogOpen(true);
  }, []);

  const openDeleteDialog = useCallback((memory: MemoryInfo) => {
    setSelectedMemory(memory);
    setDeleteDialogOpen(true);
  }, []);

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-5xl px-6 py-8 lg:px-8">
        <div className="space-y-4">
          {/* Header */}
          <PageHeader
            title="智能体记忆"
            actions={
              <>
                <div className="flex items-center gap-1">
                  <Input
                    placeholder="搜索记忆..."
                    value={searchInput}
                    onChange={(e) => setSearchInput(e.target.value)}
                    onKeyDown={handleSearchKeyDown}
                    className="w-[200px]"
                  />
                  <Button variant="outline" size="icon" onClick={handleSearch}>
                    <Search className="h-4 w-4" />
                  </Button>
                </div>
                {/* Category filter */}
                <Select
                  value={category ?? "all"}
                  onValueChange={handleCategoryChange}
                >
                  <SelectTrigger className="w-[140px]">
                    <SelectValue placeholder="全部分类" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">全部分类</SelectItem>
                    {CATEGORY_OPTIONS.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {/* Create button */}
                <Button onClick={() => setCreateDialogOpen(true)}>
                  <Plus className="mr-2 h-4 w-4" />
                  新建记忆
                </Button>
              </>
            }
          />

        {/* Content */}
        {isLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-28 w-full" />
            ))}
          </div>
        ) : error ? (
          <div className="py-8 text-center">
            <p className="text-destructive">加载失败</p>
            <Button
              variant="outline"
              className="mt-2"
              onClick={() => window.location.reload()}
            >
              重试
            </Button>
          </div>
        ) : memories.length === 0 ? (
          <EmptyState
            title="暂无记忆"
            description="点击「新建记忆」按钮创建，供智能体在对话中检索"
          />
        ) : (
          <>
            <div className="space-y-3">
              {memories.map((memory) => (
                <Card key={memory.id}>
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Badge variant={getCategoryBadgeVariant(memory.category)}>
                          {getCategoryLabel(memory.category)}
                        </Badge>
                        <span className="font-medium">{memory.key}</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => openEditDialog(memory)}
                          title="编辑"
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => openDeleteDialog(memory)}
                          title="删除"
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <p className="line-clamp-3 whitespace-pre-wrap text-sm text-muted-foreground">
                      {memory.content}
                    </p>
                  </CardContent>
                  <CardFooter className="text-xs text-muted-foreground">
                    <span>创建: {formatDate(memory.created_at)}</span>
                    {memory.updated_at && (
                      <span className="ml-4">
                        更新: {formatDate(memory.updated_at)}
                      </span>
                    )}
                  </CardFooter>
                </Card>
              ))}
            </div>

            {/* Pagination */}
            {info && (
              <Pagination
                page={info.page}
                pageSize={info.page_size}
                total={info.total}
                onPageChange={(next) => setPage(next)}
              />
            )}
          </>
        )}
        </div>
      </div>

      {/* Create dialog */}
      <MemoryFormDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
        title="新建记忆"
        initialValues={{ key: "", content: "", category: "" }}
        onSubmit={handleCreate}
        isSubmitting={isCreating}
      />

      {/* Edit dialog */}
      <MemoryFormDialog
        open={editDialogOpen}
        onOpenChange={(open) => {
          setEditDialogOpen(open);
          if (!open) setSelectedMemory(null);
        }}
        title="编辑记忆"
        initialValues={{
          key: selectedMemory?.key ?? "",
          content: selectedMemory?.content ?? "",
          category: selectedMemory?.category ?? "",
        }}
        onSubmit={handleUpdate}
        isSubmitting={isUpdating}
      />

      {/* Delete confirmation */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除</AlertDialogTitle>
            <AlertDialogDescription>
              确定要删除记忆 &quot;{selectedMemory?.key}&quot;
              吗？此操作不可撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              disabled={isDeleting}
            >
              {isDeleting && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              )}
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
