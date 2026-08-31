"use client";

import React, { useRef, useState } from "react";
import { PageHeader, EmptyState } from "@/app/components/ui-patterns";
import { useSkillTree, SkillTreeNode } from "@/lib/api/useNewModules";
import { apiClient, getApiBaseUrl } from "@/lib/api-client";
import { getToken } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
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
import { toast } from "sonner";
import { Upload, FileText, Folder, ChevronRight, ChevronDown, Trash2 } from "lucide-react";
import { MarkdownContent } from "@/app/components/MarkdownContent";

function TreeNode({ node, depth, onSelect }: {
  node: SkillTreeNode; depth: number; onSelect: (path: string) => void;
}) {
  const [open, setOpen] = useState(depth < 1);
  if (node.type === "dir") {
    return (
      <div>
        <button
          className="flex w-full items-center gap-1 rounded px-1 py-0.5 text-sm hover:bg-accent"
          style={{ paddingLeft: depth * 14 }}
          onClick={() => setOpen(!open)}
        >
          {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
          <Folder className="h-3.5 w-3.5 text-warning" />
          {node.name}
        </button>
        {open && (node.children ?? []).map((c) => (
          <TreeNode key={c.name + depth} node={c} depth={depth + 1} onSelect={onSelect} />
        ))}
      </div>
    );
  }
  return (
    <button
      className="flex w-full items-center gap-1 rounded px-1 py-0.5 text-sm hover:bg-accent"
      style={{ paddingLeft: depth * 14 + 18 }}
      onClick={() => node.path && onSelect(node.path)}
    >
      <FileText className="h-3.5 w-3.5 text-muted-foreground" />
      {node.name}
    </button>
  );
}

export default function SkillsPage() {
  const tree = useSkillTree();
  const [content, setContent] = useState<{ path: string; content: string } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const refresh = () => { tree.mutate(); setContent(null); };

  const viewFile = async (path: string) => {
    try {
      const res = await apiClient.get<{ path: string; content: string }>(
        `/skills/content?path=${encodeURIComponent(path)}`);
      setContent(res.data);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "读取失败");
    }
  };

  const upload = async (file: File) => {
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${getApiBaseUrl()}/api/v2/skills/upload`, {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken()}` },
        body: form,
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.detail || "上传失败");
      toast.success(json.data?.note || "上传成功");
      refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "上传失败");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const remove = async (path: string) => {
    setDeleting(true);
    try {
      await apiClient.delete(`/skills?path=${encodeURIComponent(path)}`);
      toast.success(`已删除 ${path}`);
      setDeleteTarget(null);
      refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "删除失败");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-6xl px-6 py-8 lg:px-8">
        <div className="flex flex-col gap-5">
          <PageHeader
            title="技能库"
            description="上传测试技能（SKILL.md 或打包的技能文件夹 zip），上传后用例生成 / UI 自动化智能体在下次运行时自动加载。技能库当前由你手动维护，平台不会自动生成或修改技能。"
          />

          {/* 上传 */}
          <Card
            className="flex flex-col items-center justify-center gap-2 border-dashed p-8"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const file = e.dataTransfer.files?.[0];
              if (file) upload(file);
            }}
          >
            <Upload className="h-8 w-8 text-muted-foreground" />
            <div className="text-sm">
              {uploading ? "上传中…" : "拖拽技能文件到这里，或"}
            </div>
            <input
              ref={inputRef}
              type="file"
              accept=".md,.zip,.py,.txt,.json,.yaml,.yml"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) upload(file);
              }}
            />
            <Button size="sm" variant="outline" onClick={() => inputRef.current?.click()} disabled={uploading}>
              选择文件
            </Button>
            <p className="text-xs text-muted-foreground">
              单个技能：上传包含 SKILL.md 的文件夹打成的 zip（推荐）；辅助文件（md/py/脚本）可直接上传
            </p>
          </Card>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {/* 技能文件树 */}
            <Card className="p-4">
              <div className="mb-2 text-sm font-medium">技能文件（src/app/skills）</div>
              <div className="max-h-[480px] overflow-y-auto">
                {tree.isLoading ? (
                  <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
                    加载中…
                  </div>
                ) : (tree.data ?? []).length === 0 ? (
                  <EmptyState title="技能库为空" description="上传 SKILL.md 或技能文件夹 zip 后在此管理" />
                ) : (
                  (tree.data ?? []).map((n) => (
                    <TreeNode key={n.name} node={n} depth={0} onSelect={viewFile} />
                  ))
                )}
              </div>
            </Card>

            {/* 文件内容预览 */}
            {content && (
              <Card className="p-4">
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-sm font-medium">{content.path}</span>
                  <div className="flex gap-1.5">
                    <Button size="sm" variant="ghost" onClick={() => setContent(null)}>关闭</Button>
                    <Button size="sm" variant="outline" onClick={() => setDeleteTarget(content.path)}>
                      <Trash2 className="mr-1 h-3.5 w-3.5" />删除
                    </Button>
                  </div>
                </div>
                <div className="max-h-[480px] overflow-y-auto rounded-md border bg-muted/30 p-4">
                  <MarkdownContent content={content.content} />
                </div>
              </Card>
            )}
          </div>
        </div>
      </div>

      {/* 删除确认 */}
      <AlertDialog open={deleteTarget !== null} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除</AlertDialogTitle>
            <AlertDialogDescription>
              确定删除「{deleteTarget}」吗？此操作不可撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              disabled={deleting}
              onClick={() => {
                if (deleteTarget) remove(deleteTarget);
              }}
            >
              {deleting ? "删除中…" : "删除"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
