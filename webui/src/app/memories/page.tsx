"use client";

/**
 * Agent 记忆（harness 风格 Markdown 记忆模块）。
 *
 * 记忆不是数据库里的记录，而是工作区里几个**固定名字的 Markdown 文件**：
 * AGENTS.md（工作区指令）/ MEMORY.md（长期记忆）/ USER.md（用户画像）/
 * failures.md（失败教训）/ PROJECT.md（项目上下文）/ DECISIONS.md（决策记录），
 * 外加用户自建的模块。每个模块都能单独启用/停用——停用 = 不再注入提示词，
 * 文件本身留着（想恢复随时开回来）。
 *
 * 页面上的编辑直接写文件：文件是唯一事实源，agent 下一轮就能看到。
 */

import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { PageHeader, EmptyState } from "@/app/components/ui-patterns";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
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
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Loader2, Plus, Save, Search, Trash2 } from "lucide-react";
import {
  appendMemoryEntry,
  createMemoryModule,
  deleteMemoryModule,
  saveMemoryModule,
  searchMemories,
  setMemoryGlobalSwitch,
  setMemoryModuleEnabled,
  useMemoryGlobalSwitch,
  useMemoryModule,
  useMemoryModules,
  useMemoryStatus,
  type MemoryHit,
} from "@/lib/api/useMemories";

function formatChars(chars: number): string {
  if (chars < 1024) return `${chars} 字`;
  return `${(chars / 1024).toFixed(1)}k 字`;
}

export default function MemoriesPage() {
  const modules = useMemoryModules();
  const status = useMemoryStatus();
  const [selected, setSelected] = useState<string | null>(null);
  const detail = useMemoryModule(selected);
  const [draft, setDraft] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [toggling, setToggling] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [newLabel, setNewLabel] = useState("");
  const [newFile, setNewFile] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [hits, setHits] = useState<MemoryHit[] | null>(null);
  const [entryText, setEntryText] = useState("");
  const [entryModule, setEntryModule] = useState("memory");
  const [gateBusy, setGateBusy] = useState(false);

  const rows = useMemo(() => modules.data ?? [], [modules.data]);

  // 记忆总闸（设置页那个 MEMORY_ENABLED 搬到这里）：默认开，只有显式 false 才算关
  const gate = useMemoryGlobalSwitch();
  const globalOn = String(gate.data?.memory_enabled ?? "true").toLowerCase() !== "false";
  const toggleGlobal = async (next: boolean) => {
    setGateBusy(true);
    try {
      await setMemoryGlobalSwitch(next);
      toast.success(next ? "记忆已恢复注入" : "记忆总闸已关闭：模型不再看到任何记忆");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "切换失败");
    } finally {
      setGateBusy(false);
    }
  };

  // 首次加载自动选中 AGENTS.md（最重要的那个模块）
  useEffect(() => {
    if (selected || rows.length === 0) return;
    setSelected((rows.find((m) => m.id === "agents") ?? rows[0]).id);
  }, [rows, selected]);

  useEffect(() => {
    if (detail.data) setDraft(detail.data.content);
  }, [detail.data]);

  const dirty = draft !== null && detail.data != null && draft !== detail.data.content;

  const save = async () => {
    if (selected === null || draft === null) return;
    setSaving(true);
    try {
      await saveMemoryModule(selected, draft);
      toast.success("已保存，agent 下一轮对话即可看到");
      modules.mutate();
      status.mutate();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const toggle = async (id: string, enabled: boolean) => {
    setToggling(id);
    try {
      await setMemoryModuleEnabled(id, enabled);
      toast.success(enabled ? "已启用（重新注入提示词）" : "已停用（文件保留，不再注入）");
      modules.mutate();
      status.mutate();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "操作失败");
    } finally {
      setToggling(null);
    }
  };

  const runSearch = async () => {
    if (!query.trim()) return;
    setSearching(true);
    try {
      const result = await searchMemories(query.trim(), 20);
      setHits(result.hits);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "检索失败");
    } finally {
      setSearching(false);
    }
  };

  const submitEntry = async () => {
    if (!entryText.trim()) return;
    try {
      await appendMemoryEntry({ module: entryModule, content: entryText.trim() });
      toast.success("已写入记忆");
      setEntryText("");
      modules.mutate();
      status.mutate();
      if (selected === entryModule) detail.mutate();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "写入失败");
    }
  };

  const create = async () => {
    if (!newLabel.trim()) return;
    setCreating(true);
    try {
      const created = await createMemoryModule({
        label: newLabel.trim(),
        file: newFile.trim() || undefined,
        description: newDescription.trim(),
      });
      toast.success(`已创建 ${created.file}`);
      setCreateOpen(false);
      setNewLabel("");
      setNewFile("");
      setNewDescription("");
      modules.mutate();
      setSelected(created.id);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "创建失败");
    } finally {
      setCreating(false);
    }
  };

  const confirmRemove = async () => {
    if (!confirmDelete) return;
    try {
      await deleteMemoryModule(confirmDelete);
      toast.success("已删除");
      if (selected === confirmDelete) setSelected(null);
      setConfirmDelete(null);
      modules.mutate();
      status.mutate();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "删除失败");
    }
  };

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-6xl px-6 py-8 lg:px-8">
        <div className="flex flex-col gap-5">
          <PageHeader
            title="Agent 记忆"
            description={
              <>
                harness 风格的 Markdown 记忆：<code className="text-xs">AGENTS.md</code>（工作区指令）、
                <code className="text-xs">MEMORY.md</code>（长期记忆）、
                <code className="text-xs">USER.md</code>（用户画像）、
                <code className="text-xs">failures.md</code>（失败教训）等。
                模块可单独启用/停用，文件就在工作区里，agent 与人都能改。
              </>
            }
            actions={
              <div className="flex items-center gap-2">
                <Button size="sm" variant="outline" onClick={() => setCreateOpen(true)}>
                  <Plus className="mr-1.5 h-4 w-4" />新建模块
                </Button>
              </div>
            }
          />

          <Card className="flex flex-wrap items-center gap-x-6 gap-y-3 p-3 text-sm">
            <span className="text-muted-foreground">
              启用 <span className="font-mono">{status.data?.enabled_modules ?? "-"}</span>
              /{status.data?.total_modules ?? "-"} 个模块 ·
              注入 <span className="font-mono">{formatChars(status.data?.chars ?? 0)}</span>
            </span>
            <span className="min-w-0 flex-1 truncate text-muted-foreground">
              目录：<span className="font-mono text-xs">{status.data?.root ?? "-"}</span>
            </span>
            {/* 总闸：只有它能"让模型不知道有记忆这回事"。模块全关仍会贴官方的
                <memory_guidelines>（正文是 No memory loaded），模型照样知道可以写记忆；
                所以排障时用它，日常控制用上面那些模块开关。 */}
            <span className="flex items-center gap-2">
              <span className="flex flex-col items-end leading-tight">
                <span className="text-xs font-medium">
                  记忆总闸{globalOn ? "（开）" : "（已停用）"}
                </span>
                <span className="text-[10px] text-muted-foreground">
                  {globalOn ? "关掉 = 模型完全不知道有记忆（排障用）" : "模型当前看不到任何记忆"}
                </span>
              </span>
              <Switch checked={globalOn} disabled={gateBusy}
                      onCheckedChange={toggleGlobal} />
            </span>
          </Card>

          <div className="grid gap-4 lg:grid-cols-[minmax(0,340px)_minmax(0,1fr)]">
            {/* 左：模块列表 + 手动沉淀 + 检索 */}
            <div className="flex flex-col gap-4">
              <Card className="p-0">
                <div className="border-b px-3 py-2 text-sm font-medium">记忆模块</div>
                {modules.isLoading ? (
                  <div className="flex flex-col gap-2 p-3">
                    <Skeleton className="h-12 w-full" />
                    <Skeleton className="h-12 w-full" />
                  </div>
                ) : rows.length === 0 ? (
                  <EmptyState title="还没有记忆模块"
                              description="点击右上角「新建模块」，平台首次启动也会自动落盘内置模块" />
                ) : (
                  <ul className="divide-y">
                    {rows.map((module) => (
                      <li key={module.id}
                          className={`flex items-start gap-2 px-3 py-2.5 ${
                            selected === module.id ? "bg-muted/50" : ""}`}>
                        <button
                          type="button"
                          className="min-w-0 flex-1 text-left"
                          onClick={() => setSelected(module.id)}
                        >
                          <div className="flex items-center gap-1.5">
                            <span className="truncate text-sm font-medium">{module.label}</span>
                            {module.builtin && (
                              <Badge variant="outline" className="shrink-0 font-normal text-[10px]">
                                内置
                              </Badge>
                            )}
                            {!module.enabled && (
                              <Badge variant="secondary" className="shrink-0 font-normal text-[10px]">
                                已停用
                              </Badge>
                            )}
                          </div>
                          <div className="truncate font-mono text-[11px] text-muted-foreground">
                            {module.file} · {formatChars(module.chars)}
                          </div>
                        </button>
                        <div className="flex shrink-0 items-center gap-1.5 pt-0.5">
                          <Switch
                            checked={module.enabled}
                            disabled={toggling === module.id}
                            onCheckedChange={(next) => toggle(module.id, next)}
                            aria-label={`${module.enabled ? "停用" : "启用"} ${module.file}`}
                          />
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>

              <Card className="flex flex-col gap-2 p-3">
                <span className="text-sm font-medium">手动沉淀一条记忆</span>
                <div className="flex gap-2">
                  <select
                    className="h-9 rounded-md border border-input bg-transparent px-2 text-sm"
                    value={entryModule}
                    onChange={(e) => setEntryModule(e.target.value)}
                  >
                    {rows.map((m) => (
                      <option key={m.id} value={m.id}>{m.file}</option>
                    ))}
                  </select>
                  <Input
                    value={entryText}
                    placeholder="要记住的结论（会带时间戳追加）"
                    onChange={(e) => setEntryText(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") void submitEntry();
                    }}
                  />
                  <Button size="sm" onClick={submitEntry} disabled={!entryText.trim()}>写入</Button>
                </div>
                <p className="text-[11px] text-muted-foreground">
                  agent 也会用 save_memory / record_failure 工具往这里写；这里适合你直接补一条。
                </p>
              </Card>

              <Card className="flex flex-col gap-2 p-3">
                <span className="text-sm font-medium">检索</span>
                <div className="flex gap-2">
                  <Input
                    value={query}
                    placeholder="关键词，如「跨天重置」"
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") void runSearch();
                    }}
                  />
                  <Button size="sm" variant="outline" onClick={runSearch} disabled={searching}>
                    {searching ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      : <Search className="h-3.5 w-3.5" />}
                  </Button>
                </div>
                {hits && (
                  hits.length === 0 ? (
                    <p className="text-xs text-muted-foreground">没有命中（只检索启用中的模块）</p>
                  ) : (
                    <ul className="flex max-h-64 flex-col gap-1.5 overflow-y-auto">
                      {hits.map((hit) => (
                        <li key={`${hit.file}-${hit.line}`} className="text-xs">
                          <button
                            type="button"
                            className="text-left hover:underline"
                            onClick={() => setSelected(hit.module_id)}
                          >
                            <span className="font-mono text-muted-foreground">
                              {hit.file}:{hit.line}
                            </span>
                            <span className="ml-1">{hit.text}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )
                )}
              </Card>
            </div>

            {/* 右：编辑器 */}
            <Card className="flex min-h-[520px] flex-col p-0">
              {selected === null ? (
                <EmptyState title="选择一个记忆模块" description="左侧列表里点一个模块来查看/编辑内容" />
              ) : detail.isLoading ? (
                <div className="flex items-center justify-center gap-2 py-20 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />读取中…
                </div>
              ) : (
                <>
                  <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
                    <span className="font-mono text-sm">{detail.data?.file}</span>
                    <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
                      {detail.data?.description}
                    </span>
                    <Button size="sm" onClick={save} disabled={!dirty || saving}>
                      {saving ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                        : <Save className="mr-1.5 h-3.5 w-3.5" />}
                      保存
                    </Button>
                    {detail.data && !detail.data.builtin && (
                      <Button size="sm" variant="ghost"
                              onClick={() => setConfirmDelete(selected)}
                              aria-label="删除模块">
                        <Trash2 className="h-3.5 w-3.5 text-destructive" />
                      </Button>
                    )}
                  </div>
                  <Textarea
                    value={draft ?? ""}
                    onChange={(e) => setDraft(e.target.value)}
                    spellCheck={false}
                    className="min-h-[440px] flex-1 resize-none rounded-none border-0 font-mono text-[13px] leading-6 focus-visible:ring-0"
                  />
                  <div className="flex items-center justify-between border-t px-3 py-1.5 text-[11px] text-muted-foreground">
                    <span>{dirty ? "有未保存的改动" : "已与磁盘一致"}</span>
                    <span>
                      停用的模块不会注入提示词，但内容照旧保存在文件里
                    </span>
                  </div>
                </>
              )}
            </Card>
          </div>

          <Card className="p-3 text-xs leading-5 text-muted-foreground">
            注入规则：所有**启用中**的模块会按顺序拼进系统提示词（AGENTS.md 在最前）。
            注入走框架官方实现、**不做截断**——写多长就占多少上下文，所以请保持精炼；
            需要细节时 agent 可以用 read_memory_module 读全文。记忆在提示词里被明确标注为
            <span className="text-foreground/80">「参考材料，不是指令」</span>（文件可能过期、
            也可能不是当前用户写的），与当轮要求冲突时以用户为准。
            改完**下一轮对话立即生效**，不需要重启服务。
          </Card>
        </div>
      </div>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader><DialogTitle>新建记忆模块</DialogTitle></DialogHeader>
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="mem-label">显示名 *</Label>
              <Input id="mem-label" value={newLabel} placeholder="例如：环境速查"
                     onChange={(e) => setNewLabel(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="mem-file">文件名（留空按显示名生成）</Label>
              <Input id="mem-file" value={newFile} placeholder="TOOLS.md" className="font-mono"
                     onChange={(e) => setNewFile(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="mem-desc">说明</Label>
              <Input id="mem-desc" value={newDescription} placeholder="这个模块放什么"
                     onChange={(e) => setNewDescription(e.target.value)} />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setCreateOpen(false)}>取消</Button>
              <Button onClick={create} disabled={creating || !newLabel.trim()}>
                {creating && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}创建
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <AlertDialog open={confirmDelete !== null}
                   onOpenChange={(open) => !open && setConfirmDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除这个记忆模块？</AlertDialogTitle>
            <AlertDialogDescription>
              会连同 Markdown 文件一起删除，不可恢复。内置模块不能删除（可以停用）。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={confirmRemove}>删除</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
