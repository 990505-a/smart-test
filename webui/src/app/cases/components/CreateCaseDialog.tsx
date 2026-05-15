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
import type { FolderTreeNode, TestCaseCreate } from "@/app/types/api";

const caseSchema = z.object({
  name: z.string().min(1, "请输入用例名称"),
  priority: z.enum(["low", "medium", "high", "critical"]).optional(),
  template: z.enum(["test_case", "test_case_bdd"]).optional(),
  folder_id: z.string().nullable().optional(),
  description: z.string().optional(),
  preconditions: z.string().optional(),
});

interface CreateCaseDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (data: TestCaseCreate) => void;
  projectId: string;
  folders?: FolderTreeNode[];
}

/** Flatten tree nodes for folder select dropdown */
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

export function CreateCaseDialog({
  open,
  onOpenChange,
  onSubmit,
  projectId,
  folders = [],
}: CreateCaseDialogProps) {
  const [name, setName] = useState("");
  const [priority, setPriority] = useState<"low" | "medium" | "high" | "critical">("medium");
  const [template, setTemplate] = useState<"test_case" | "test_case_bdd">("test_case");
  const [folderId, setFolderId] = useState<string | null>(null);
  const [description, setDescription] = useState("");
  const [preconditions, setPreconditions] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setName("");
      setPriority("medium");
      setTemplate("test_case");
      setFolderId(null);
      setDescription("");
      setPreconditions("");
      setError(null);
    }
  }, [open]);

  const handleSubmit = () => {
    const result = caseSchema.safeParse({ name, priority, template, folder_id: folderId, description, preconditions });
    if (!result.success) {
      setError(result.error.issues[0].message);
      return;
    }

    onSubmit({
      project_id: projectId,
      name,
      priority,
      template,
      folder_id: folderId,
      description: description || undefined,
      preconditions: preconditions || undefined,
    });
    onOpenChange(false);
  };

  const flatFolders = flattenNodes(folders);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[525px]">
        <DialogHeader>
          <DialogTitle>新建测试用例</DialogTitle>
          <DialogDescription>
            创建一个新的测试用例，可以稍后在编辑器中添加测试步骤。
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="caseName">用例名称</Label>
            <Input
              id="caseName"
              placeholder="请输入用例名称"
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setError(null);
              }}
            />
            {error && <p className="text-sm text-destructive">{error}</p>}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>优先级</Label>
              <Select value={priority} onValueChange={(val) => setPriority(val as typeof priority)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="low">低</SelectItem>
                  <SelectItem value="medium">中</SelectItem>
                  <SelectItem value="high">高</SelectItem>
                  <SelectItem value="critical">严重</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="grid gap-2">
              <Label>用例类型</Label>
              <Select value={template} onValueChange={(val) => setTemplate(val as typeof template)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="test_case">标准用例</SelectItem>
                  <SelectItem value="test_case_bdd">BDD 用例</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid gap-2">
            <Label>所属文件夹</Label>
            <Select value={folderId ?? "none"} onValueChange={(val) => setFolderId(val === "none" ? null : val)}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder="无 (根目录)" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">无 (根目录)</SelectItem>
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
            <Label htmlFor="caseDescription">描述</Label>
            <Textarea
              id="caseDescription"
              placeholder="可选描述"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="casePreconditions">前置条件</Label>
            <Textarea
              id="casePreconditions"
              placeholder="可选前置条件"
              value={preconditions}
              onChange={(e) => setPreconditions(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleSubmit}>创建</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
