"use client";

import { useState, useEffect } from "react";
import { z } from "zod";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { FolderTreeNode, FolderCreate, FolderUpdate } from "@/app/types/api";

const folderSchema = z.object({
  name: z.string().min(1, "请输入文件夹名称"),
  description: z.string().optional(),
  parent_id: z.string().nullable().optional(),
  folder_type: z.enum(["test_case", "api_test"]).optional(),
});

interface CreateFolderDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (data: FolderCreate | { id: string; data: FolderUpdate }) => void;
  initialData?: FolderTreeNode | null;
  mode: "create" | "edit";
  projectId: string;
  parentFolders?: FolderTreeNode[];
}

/** Flatten tree nodes into a list for the parent folder select dropdown */
function flattenNodes(nodes: FolderTreeNode[], depth = 0): Array<{ id: string; name: string; depth: number }> {
  const result: Array<{ id: string; name: string; depth: number }> = [];
  for (const node of nodes) {
    result.push({ id: node.id, name: node.name, depth });
    if (node.children?.length) {
      result.push(...flattenNodes(node.children, depth + 1));
    }
  }
  return result;
}

export function CreateFolderDialog({
  open,
  onOpenChange,
  onSubmit,
  initialData,
  mode,
  projectId,
  parentFolders = [],
}: CreateFolderDialogProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [parentId, setParentId] = useState<string | null>(null);
  const [folderType, setFolderType] = useState<"test_case" | "api_test">("test_case");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      if (mode === "edit" && initialData) {
        setName(initialData.name);
        setDescription(initialData.description || "");
        setParentId(initialData.parent_id);
        setFolderType(initialData.folder_type);
      } else {
        setName("");
        setDescription("");
        setParentId(null);
        setFolderType("test_case");
      }
      setError(null);
    }
  }, [open, mode, initialData]);

  const handleSubmit = () => {
    const result = folderSchema.safeParse({ name, description, parent_id: parentId, folder_type: folderType });
    if (!result.success) {
      setError(result.error.issues[0].message);
      return;
    }

    if (mode === "create") {
      onSubmit({
        project_id: projectId,
        name,
        description: description || undefined,
        parent_id: parentId,
        folder_type: folderType,
      });
    } else if (initialData) {
      onSubmit({
        id: initialData.id,
        data: {
          name,
          description: description || undefined,
        },
      });
    }
    onOpenChange(false);
  };

  const flatFolders = flattenNodes(parentFolders);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>{mode === "create" ? "新建文件夹" : "编辑文件夹"}</DialogTitle>
          <DialogDescription>
            {mode === "create"
              ? "在当前项目下创建新的文件夹来组织测试用例。"
              : "修改文件夹的名称和描述。"}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="folderName">文件夹名称</Label>
            <Input
              id="folderName"
              placeholder="请输入文件夹名称"
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setError(null);
              }}
            />
            {error && <p className="text-sm text-destructive">{error}</p>}
          </div>

          <div className="grid gap-2">
            <Label htmlFor="folderDescription">描述</Label>
            <Textarea
              id="folderDescription"
              placeholder="可选描述"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          {mode === "create" && (
            <>
              <div className="grid gap-2">
                <Label>父文件夹</Label>
                <Select value={parentId ?? "root"} onValueChange={(val) => setParentId(val === "root" ? null : val)}>
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="无 (根目录)" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="root">无 (根目录)</SelectItem>
                    {flatFolders.map((f) => (
                      <SelectItem key={f.id} value={f.id}>
                        {"  ".repeat(f.depth)}
                        {f.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="grid gap-2">
                <Label>文件夹类型</Label>
                <Select value={folderType} onValueChange={(val) => setFolderType(val as "test_case" | "api_test")}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="test_case">测试用例</SelectItem>
                    <SelectItem value="api_test">API 测试</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleSubmit}>
            {mode === "create" ? "创建" : "保存"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
