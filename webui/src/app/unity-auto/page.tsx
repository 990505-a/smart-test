"use client";

import React, { useState } from "react";
import Link from "next/link";
import { PageHeader, StatusBadge, EmptyState } from "@/app/components/ui-patterns";
import {
  useUnityScripts, useUnityScriptRuns, useUnityStatus, useUnityTools, UnityScript,
  deleteUnityScript,
} from "@/lib/api/useNewModules";
import { apiClient } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import { Camera, Play, Plus, TerminalSquare, Trash2, Wrench } from "lucide-react";
import { EvidenceHint, UnityRunDetailDialog } from "@/app/components/unity-auto/RunDetail";

/** 删掉多少东西要说清楚：磁盘上那些截图/录像才是"删干净了没"的答案。 */
function deletedHint(r: { runs: number; files: number; bytes: number }): string {
  const mb = r.bytes > 0 ? `，${(r.bytes / 1024 / 1024).toFixed(1)} MB` : "";
  return `已删除：${r.runs} 条执行记录 + ${r.files} 个产物文件${mb}`;
}

function CreateScriptDialog({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [module, setModule] = useState("");
  const [content, setContent] = useState(
`# Unity 用例脚本（prelude 已注入 u = Unity() 客户端，不需要 import）
# 例：打开背包并校验标题
u.expect_exists("MainHud", timeout=20)      # 等主界面
u.click("MainHud/BottomBar/BagButton")      # 操作
u.expect_exists("BagWindow", timeout=10)    # 等窗口
u.expect_text("BagWindow/Title", "背包")     # 断言
u.screenshot("bag_open.png")                # 存证
print("PASS: 背包窗口打开且标题正确")
`);
  const [saving, setSaving] = useState(false);

  const create = async () => {
    if (!name.trim() || !content.trim()) { toast.error("请填写名称和脚本内容"); return; }
    setSaving(true);
    try {
      await apiClient.post("/unity-auto/scripts", {
        name: name.trim(), module: module || null, content,
      });
      toast.success("脚本已创建");
      setOpen(false);
      onCreated();
    } catch (err) { toast.error(err instanceof Error ? err.message : "创建失败"); }
    finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button size="sm" onClick={() => setOpen(true)}>
        <Plus className="mr-1.5 h-4 w-4" />新建脚本
      </Button>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader><DialogTitle>新建 Unity 用例脚本</DialogTitle></DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>脚本名 *</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="背包窗口冒烟" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>游戏模块</Label>
              <Input value={module} onChange={(e) => setModule(e.target.value)} placeholder="背包" />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>脚本内容（python，已注入 u = Unity() 客户端）*</Label>
            <Textarea value={content} onChange={(e) => setContent(e.target.value)}
                      className="min-h-[280px] font-mono text-xs" />
          </div>
          <Button onClick={create} disabled={saving}>{saving ? "创建中…" : "创建"}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function RunsDialog({
  script, onClose, onOpenRun,
}: {
  script: UnityScript;
  onClose: () => void;
  onOpenRun: (runId: string) => void;
}) {
  const runs = useUnityScriptRuns(script.id);
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader><DialogTitle>{script.name} · 执行历史</DialogTitle></DialogHeader>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>时间</TableHead><TableHead>结果</TableHead>
              <TableHead>存证</TableHead>
              <TableHead>耗时</TableHead><TableHead className="text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(runs.data ?? []).map((r) => (
              <TableRow key={r.id}>
                <TableCell className="whitespace-nowrap text-muted-foreground">
                  {r.created_at ? new Date(r.created_at).toLocaleString("zh-CN") : "-"}
                </TableCell>
                <TableCell><StatusBadge status={r.status} /></TableCell>
                <TableCell><EvidenceHint run={r} /></TableCell>
                <TableCell>{r.duration_ms != null ? `${(r.duration_ms / 1000).toFixed(1)}s` : "-"}</TableCell>
                <TableCell className="text-right">
                  <Button size="sm" variant="outline" onClick={() => onOpenRun(r.id)}>
                    看详情
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <p className="text-[11px] text-muted-foreground">
          每次执行都会留下步骤轨迹、截图与录像（默认开录）：点「看详情」看失败在哪一步、
          现场长什么样。用例脚本不需要自己写截图代码。
        </p>
      </DialogContent>
    </Dialog>
  );
}

export default function UnityAutoPage() {
  const unity = useUnityStatus();
  const tools = useUnityTools();
  const scripts = useUnityScripts();
  const [csCode, setCsCode] = useState("");
  const [csOutput, setCsOutput] = useState<string | null>(null);
  const [runsFor, setRunsFor] = useState<UnityScript | null>(null);
  const [detail, setDetail] = useState<{ id: string; name: string } | null>(null);
  const [showTools, setShowTools] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<UnityScript | null>(null);
  const [deleting, setDeleting] = useState(false);

  const statusBadge = unity.data === undefined && !unity.error ? (
    // 首屏还没拿到状态时别先喊"未连接"：加载那一下的红标会让人以为环境挂了
    <Badge variant="secondary" className="font-normal text-muted-foreground">桥状态检查中…</Badge>
  ) : !unity.data?.available ? (
    <Badge variant="destructive">Unity 桥未连接</Badge>
  ) : (
    <Badge className="bg-success/12 font-normal text-success">
      桥在线{unity.data.unity_connected === false ? " · Unity 未连" : ""}
      {unity.data.is_playing ? " · Play Mode" : ""}
      {unity.data.tool_count ? ` · ${unity.data.tool_count} 工具` : ""}
    </Badge>
  );

  const screenshot = async () => {
    try {
      const res = await apiClient.post<{ path: string }>("/unity-auto/screenshot", {});
      toast.success(`截图已保存：${res.data.path}`);
    } catch (err) { toast.error(err instanceof Error ? err.message : "截图失败"); }
  };

  const execCSharp = async () => {
    if (!csCode.trim()) return;
    try {
      const res = await apiClient.post<{ success: boolean; text?: string; error?: string; result?: unknown }>(
        "/unity-auto/exec-csharp", { code: csCode });
      setCsOutput(res.data.success
        ? (res.data.result ? JSON.stringify(res.data.result, null, 2) : res.data.text ?? "(无输出)")
        : `错误: ${res.data.error}`);
    } catch (err) { setCsOutput(err instanceof Error ? err.message : "执行失败"); }
  };

  const runScript = async (script: UnityScript) => {
    try {
      // 后端在入队前就把执行记录建好了，所以这里拿得到 run_id：
      // 直接打开详情看步骤轨迹一条条冒出来，而不是"等 3 秒再刷新列表"。
      const res = await apiClient.post<{ started: boolean; run_id?: string }>(
        `/unity-auto/scripts/${script.id}/run`, {});
      if (res.data.run_id) setDetail({ id: res.data.run_id, name: script.name });
      toast.success("脚本已在后台执行");
      setTimeout(() => scripts.mutate(), 2000);
    } catch (err) { toast.error(err instanceof Error ? err.message : "启动失败"); }
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      const out = await deleteUnityScript(pendingDelete.id);
      toast.success(deletedHint(out));
      setPendingDelete(null);
      scripts.mutate();
    } catch (err) {
      // 正在执行中会回 409：把后端那句话原样给出来（比"删除失败"有用）
      toast.error(err instanceof Error ? err.message : "删除失败");
    } finally { setDeleting(false); }
  };

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-6xl px-6 py-8 lg:px-8">
        <div className="flex flex-col gap-5">
          <PageHeader
            title="Unity 自动化"
            description={
              <>
                经**标准 MCP** 操作 Unity（对象查询 / 控件操作 / 任意 C# / 截图），与具体游戏无关：
                探索出来的流程沉淀成可回归的用例脚本。也可以去
                <Link href="/chat" className="text-primary hover:underline">聊天页</Link>
                让通用测试助手自己探索并生成用例。
              </>
            }
            actions={
              <div className="flex items-center gap-2">
                {statusBadge}
                <Button size="sm" variant="outline" onClick={screenshot}>
                  <Camera className="mr-1.5 h-4 w-4" />截图
                </Button>
              </div>
            }
          />

          {!unity.data?.available && unity.data && (
            <Card className="border-warning/40 bg-warning/10 p-3 text-sm text-warning">
              {unity.data.error ?? "Unity MCP 桥未连接"}。
              {unity.data.hint ?? "在启动器启动 unity-mcp（:5016，需 uv）；Unity 工程里装「MCP for Unity」包并指向本机 5016。"}
            </Card>
          )}

        {/* C# 快捷执行（通用逃逸口） */}
        <Card className="p-4">
          <div className="mb-2 flex items-center gap-1.5 text-sm font-medium">
            <TerminalSquare className="h-4 w-4" />C# 快捷执行
            <span className="text-xs font-normal text-muted-foreground">
              （通用逃逸口：点不动、查不到的都能自己写两行；结果用
              Debug.Log(&quot;UNITY_BRIDGE:&#123;...&#125;&quot;) 回传）
            </span>
          </div>
          <div className="flex gap-2">
            <Input
              value={csCode}
              onChange={(e) => setCsCode(e.target.value)}
              placeholder='如: UnityEngine.Debug.Log("UNITY_BRIDGE:{\"ok\":true}")'
              onKeyDown={(e) => e.key === "Enter" && execCSharp()}
            />
            <Button variant="outline" onClick={execCSharp} className="shrink-0">执行</Button>
          </div>
          {csOutput && (
            <pre className="mt-2 max-h-40 overflow-y-auto rounded bg-muted p-2 text-xs">{csOutput}</pre>
          )}
        </Card>

        {/* MCP 工具清单：换服务器/升级后"到底有什么工具"的第一现场 */}
        <Card className="p-0">
          <button
            className="flex w-full items-center justify-between px-4 py-2.5 text-sm font-medium"
            onClick={() => setShowTools((v) => !v)}
          >
            <span className="flex items-center gap-1.5">
              <Wrench className="h-4 w-4" />MCP 服务器工具
              <span className="text-xs font-normal text-muted-foreground">
                {tools.data?.count != null
                  ? `${tools.data.count} 个 · ${tools.data.server?.name ?? ""}`
                  : "（桥未连接时为空）"}
              </span>
            </span>
            <span className="text-xs text-muted-foreground">{showTools ? "收起" : "展开"}</span>
          </button>
          {showTools && (
            <div className="border-t p-3">
              {(tools.data?.tools ?? []).length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  {tools.data?.error ?? "读不到工具清单：桥没起，或服务器还没连上 Unity。"}
                </p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {(tools.data?.tools ?? []).map((t) => (
                    <Badge key={t.name} variant="outline" className="font-mono text-[10px] font-normal"
                           title={t.description}>
                      {t.name}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          )}
        </Card>

        {/* 脚本列表 */}
        <Card className="p-0">
          <div className="flex items-center justify-between border-b px-4 py-2.5">
            <span className="text-sm font-medium">Unity 用例脚本</span>
            <CreateScriptDialog onCreated={() => scripts.mutate()} />
          </div>
          {scripts.isLoading ? (
            <div className="flex items-center justify-center py-16 text-sm text-muted-foreground">
              加载中…
            </div>
          ) : (scripts.data ?? []).length === 0 ? (
            <EmptyState
              title="暂无脚本"
              description="可点击「新建脚本」，或到聊天页让通用助手探索后生成"
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>名称</TableHead><TableHead>模块</TableHead><TableHead>状态</TableHead>
                  <TableHead>版本</TableHead><TableHead>更新时间</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(scripts.data ?? []).map((s) => (
                  <TableRow key={s.id}>
                    <TableCell className="font-medium">{s.name}</TableCell>
                    <TableCell>{s.module ?? "-"}</TableCell>
                    <TableCell>
                      <StatusBadge status={s.status} />
                    </TableCell>
                    <TableCell>v{s.version}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {s.updated_at ? new Date(s.updated_at).toLocaleString("zh-CN") : "-"}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1.5">
                        <Button size="sm" variant="outline" onClick={() => runScript(s)}>
                          <Play className="mr-1 h-3.5 w-3.5" />执行
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setRunsFor(s)}>历史</Button>
                        <Button size="sm" variant="ghost" title="删除这条用例"
                                onClick={() => setPendingDelete(s)}>
                          <Trash2 className="h-3.5 w-3.5 text-destructive" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Card>
        </div>
      </div>

      {runsFor && (
        <RunsDialog
          script={runsFor}
          onClose={() => setRunsFor(null)}
          onOpenRun={(runId) => setDetail({ id: runId, name: runsFor.name })}
        />
      )}
      {detail && (
        <UnityRunDetailDialog
          runId={detail.id}
          scriptName={detail.name}
          onClose={() => { setDetail(null); scripts.mutate(); }}
        />
      )}

      <AlertDialog open={pendingDelete !== null}
                   onOpenChange={(open) => { if (!open) setPendingDelete(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除「{pendingDelete?.name}」？</AlertDialogTitle>
            <AlertDialogDescription>
              会连同它的全部执行记录与磁盘上的产物（截图、录像、步骤轨迹、起跑线）一起删除，
              且不可恢复。正在执行的用例删不掉 —— 等它跑完再来。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>取消</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete} disabled={deleting}>
              {deleting ? "删除中…" : "删除"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
