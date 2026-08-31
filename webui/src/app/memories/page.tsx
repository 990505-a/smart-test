"use client";

import { useState } from "react";
import { toast } from "sonner";
import { PageHeader, EmptyState } from "@/app/components/ui-patterns";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Search, Save, Trash2, Loader2, FileText, Plus } from "lucide-react";
import {
  useMemoryStatus,
  useMemoryFiles,
  useReadMemoryFile,
  useWriteMemoryFile,
  useDeleteMemoryFile,
  searchMemories,
  saveMemory,
  type MemoryHit,
} from "@/lib/api/useMemories";

function formatSize(size: number): string {
  if (size < 1024) return `${size} B`;
  return `${(size / 1024).toFixed(1)} KB`;
}

export default function MemoriesPage() {
  const status = useMemoryStatus();
  const files = useMemoryFiles();
  const [selected, setSelected] = useState<string | null>(null);
  const file = useReadMemoryFile(selected);
  const { trigger: writeTrigger, isMutating: writingFile } = useWriteMemoryFile();
  const { trigger: deleteTrigger } = useDeleteMemoryFile();
  const [draft, setDraft] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [hits, setHits] = useState<MemoryHit[] | null>(null);

  const [newKey, setNewKey] = useState("");
  const [newContent, setNewContent] = useState("");
  const [newCategory, setNewCategory] = useState<string>("");
  const [saving, setSaving] = useState(false);

  const embedEnabled = status.data?.capabilities?.embed === true;

  const onSearch = async () => {
    if (!query.trim()) return;
    setSearching(true);
    try {
      setHits(await searchMemories(query.trim()));
    } catch (e) {
      toast.error(`检索失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setSearching(false);
    }
  };

  const onSaveFile = async () => {
    if (!selected || draft === null) return;
    try {
      await writeTrigger({ path: selected, content: draft });
      setDraft(null);
      toast.success("已保存，索引将由 EverOS 自动更新");
    } catch (e) {
      toast.error(`保存失败：${e instanceof Error ? e.message : e}`);
    }
  };

  const onDeleteFile = async () => {
    if (!confirmDelete) return;
    try {
      await deleteTrigger(confirmDelete);
      if (selected === confirmDelete) {
        setSelected(null);
        setDraft(null);
      }
      setConfirmDelete(null);
      toast.success("已删除");
    } catch (e) {
      toast.error(`删除失败：${e instanceof Error ? e.message : e}`);
      setConfirmDelete(null);
    }
  };

  const onSaveMemory = async () => {
    if (!newKey.trim() || !newContent.trim()) {
      toast.error("标识和内容都不能为空");
      return;
    }
    setSaving(true);
    try {
      const result = await saveMemory(
        newKey.trim(),
        newContent.trim(),
        newCategory || undefined
      );
      setNewKey("");
      setNewContent("");
      toast.success(
        result?.flush_status === "extracted"
          ? "已写入并蒸馏为长期记忆"
          : "已写入记忆"
      );
    } catch (e) {
      toast.error(`写入失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setSaving(false);
    }
  };

  const editorValue = draft ?? file.data?.content ?? "";

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <PageHeader
        title="Agent 记忆"
        description={`EverOS 本地记忆服务${status.data?.version ? ` v${status.data.version}` : ""} — Markdown 单一事实源，人工可直接编辑`}
      />

      {status.data && !status.data.up && (
        <div className="mx-6 mb-2 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-[13px] text-destructive">
          EverOS 服务不可用：{status.data.error ?? "未知原因"}（保存/检索会在使用时自动尝试拉起）
        </div>
      )}
      {status.data?.up && !embedEnabled && (
        <div className="mx-6 mb-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-[13px] text-amber-600 dark:text-amber-400">
          关键词检索模式：在「设置」页填写记忆 Embedding Key 后可解锁向量/混合检索、反思与技能蒸馏（离线进化）。
        </div>
      )}

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 overflow-hidden px-6 pb-6 lg:grid-cols-[380px_1fr]">
        {/* 左列：检索 + 文件列表 + 手动写入 */}
        <div className="flex min-h-0 flex-col gap-4 overflow-y-auto">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm">
                <Search className="h-4 w-4" /> 记忆检索
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex gap-2">
                <Input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && onSearch()}
                  placeholder="关键词，如：联赛 结算 边界"
                />
                <Button size="sm" onClick={onSearch} disabled={searching}>
                  {searching ? <Loader2 className="h-4 w-4 animate-spin" /> : "检索"}
                </Button>
              </div>
              {hits && (
                <div className="space-y-2">
                  {hits.length === 0 && (
                    <p className="text-[13px] text-muted-foreground">没有命中的记忆</p>
                  )}
                  {hits.map((h) => (
                    <div key={h.id ?? h.subject} className="rounded-lg border px-3 py-2">
                      <p className="text-[13px] font-medium">{h.subject}</p>
                      {h.summary && (
                        <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                          {h.summary}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm">
                <FileText className="h-4 w-4" /> 记忆文件（{files.data?.length ?? "…"}）
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-1.5">
              {files.isLoading && <Skeleton className="h-40 w-full" />}
              {files.data?.length === 0 && (
                <p className="text-[13px] text-muted-foreground">
                  暂无记忆文件：与 Agent 对话中让它「记住…」，或用下方表单手动写入
                </p>
              )}
              {files.data?.map((f) => (
                <button
                  key={f.path}
                  onClick={() => {
                    setSelected(f.path);
                    setDraft(null);
                    setHits(null);
                  }}
                  className={`w-full rounded-lg border px-3 py-2 text-left transition-colors hover:bg-accent ${
                    selected === f.path ? "border-primary bg-accent" : ""
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-[13px] font-medium">
                      {f.path.split("/").pop()}
                    </span>
                    <Badge variant={f.track === "agent" ? "secondary" : "outline"}>
                      {f.track === "agent" ? "技能" : "经历"}
                    </Badge>
                  </div>
                  <p className="mt-0.5 truncate text-xs text-muted-foreground">
                    {f.path} · {formatSize(f.size)} · {f.modified_at}
                  </p>
                </button>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm">
                <Plus className="h-4 w-4" /> 手动写入长期记忆
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex gap-2">
                <Input
                  value={newKey}
                  onChange={(e) => setNewKey(e.target.value)}
                  placeholder="标识，如 settlement_rule"
                />
                <Select value={newCategory} onValueChange={(v) => setNewCategory(v ?? "")}>
                  <SelectTrigger className="w-32">
                    <SelectValue placeholder="分类" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="preference">偏好</SelectItem>
                    <SelectItem value="domain_knowledge">领域知识</SelectItem>
                    <SelectItem value="project_context">项目上下文</SelectItem>
                    <SelectItem value="convention">约定</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Textarea
                value={newContent}
                onChange={(e) => setNewContent(e.target.value)}
                placeholder="要长期记住的内容（将经 LLM 蒸馏固化为 episode）"
                rows={3}
              />
              <Button size="sm" onClick={onSaveMemory} disabled={saving}>
                {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : "写入"}
              </Button>
            </CardContent>
          </Card>
        </div>

        {/* 右列：文件查看/编辑器 */}
        <Card className="flex min-h-0 flex-col">
          <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
            <CardTitle className="truncate text-sm">
              {selected ?? "选择左侧文件查看 / 编辑"}
            </CardTitle>
            {selected && (
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={onSaveFile}
                  disabled={draft === null || writingFile}
                >
                  {writingFile ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Save className="h-4 w-4" />
                  )}
                  保存
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="text-destructive hover:text-destructive"
                  onClick={() => setConfirmDelete(selected)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            )}
          </CardHeader>
          <CardContent className="min-h-0 flex-1">
            {!selected ? (
              <EmptyState
                title="未选择文件"
                description="记忆以 Markdown 文件存储（episodes=经历、user.md=画像、agents/=技能）。编辑保存后 EverOS 会自动重建索引。"
              />
            ) : file.isLoading ? (
              <Skeleton className="h-full w-full" />
            ) : file.error ? (
              <p className="text-[13px] text-destructive">
                读取失败：{file.error instanceof Error ? file.error.message : "未知错误"}
              </p>
            ) : (
              <Textarea
                value={editorValue}
                onChange={(e) => setDraft(e.target.value)}
                className="h-full min-h-[420px] resize-none font-mono text-xs"
              />
            )}
          </CardContent>
        </Card>
      </div>

      <AlertDialog open={!!confirmDelete} onOpenChange={(v) => !v && setConfirmDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除记忆文件？</AlertDialogTitle>
            <AlertDialogDescription>
              {confirmDelete}
              <br />
              删除后不可恢复（如需保留请先复制内容），索引会自动同步。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={onDeleteFile}>删除</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
