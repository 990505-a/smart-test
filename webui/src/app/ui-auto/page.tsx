"use client";

import React, { useState } from "react";
import Link from "next/link";
import { PageHeader, StatusBadge, EmptyState } from "@/app/components/ui-patterns";
import {
  useUiScripts, useUiScriptRuns, useUnityStatus, UiScript,
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
import { toast } from "sonner";
import { Camera, Play, Plus, TerminalSquare } from "lucide-react";

function CreateScriptDialog({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [module, setModule] = useState("");
  const [content, setContent] = useState(
`# UI 自动化脚本示例（prelude 已注入 client/ui/text/inspector/gm）
# 例：打开背包窗口并断言标题
ui.open_window("BaggageWindow")
assert ui.wait_for_window("BaggageWindow", timeout=5), "背包窗口未打开"
ui.screenshot("baggage.png")
ui.close_window("BaggageWindow")
print("OK: 背包窗口测试通过")
`);
  const [saving, setSaving] = useState(false);

  const create = async () => {
    if (!name.trim() || !content.trim()) { toast.error("请填写名称和脚本内容"); return; }
    setSaving(true);
    try {
      await apiClient.post("/ui-auto/scripts", {
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
      <DialogContent className="max-w-3xl">
        <DialogHeader><DialogTitle>新建 UI 自动化脚本</DialogTitle></DialogHeader>
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
            <Label>脚本内容（python，已注入 ui/text/inspector/gm 对象）*</Label>
            <Textarea value={content} onChange={(e) => setContent(e.target.value)}
                      className="min-h-[280px] font-mono text-xs" />
          </div>
          <Button onClick={create} disabled={saving}>{saving ? "创建中…" : "创建"}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function RunsDialog({ script, onClose }: { script: UiScript; onClose: () => void }) {
  const runs = useUiScriptRuns(script.id);
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
        <DialogHeader><DialogTitle>{script.name} · 执行历史</DialogTitle></DialogHeader>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>时间</TableHead><TableHead>结果</TableHead>
              <TableHead>退出码</TableHead><TableHead>耗时</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(runs.data ?? []).map((r) => (
              <TableRow key={r.id}>
                <TableCell>{r.created_at ? new Date(r.created_at).toLocaleString("zh-CN") : "-"}</TableCell>
                <TableCell>
                  <StatusBadge status={r.status} />
                </TableCell>
                <TableCell>{r.exit_code}</TableCell>
                <TableCell>{r.duration_ms != null ? `${(r.duration_ms / 1000).toFixed(1)}s` : "-"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {(runs.data ?? []).some((r) => r.output) && (
          <pre className="max-h-64 overflow-y-auto rounded bg-muted p-3 text-xs">
            {runs.data!.find((r) => r.output)?.output}
          </pre>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default function UiAutoPage() {
  const unity = useUnityStatus();
  const scripts = useUiScripts();
  const [luaCode, setLuaCode] = useState("");
  const [luaOutput, setLuaOutput] = useState<string | null>(null);
  const [runsFor, setRunsFor] = useState<UiScript | null>(null);

  const statusBadge = unity.data?.available ? (
    <Badge className="bg-success/12 font-normal text-success">Unity 已连接{unity.data.is_playing ? " · Play Mode" : " · 未运行"}</Badge>
  ) : (
    <Badge variant="destructive">Unity 未连接</Badge>
  );

  const screenshot = async () => {
    try {
      const res = await apiClient.post<{ path: string }>("/ui-auto/screenshot", {});
      toast.success(`截图已保存：${res.data.path}`);
    } catch (err) { toast.error(err instanceof Error ? err.message : "截图失败"); }
  };

  const execLua = async () => {
    if (!luaCode.trim()) return;
    try {
      const res = await apiClient.post<{ success: boolean; output?: string; error?: string }>(
        "/ui-auto/exec-lua", { code: luaCode });
      setLuaOutput(res.data.success ? res.data.output ?? "(无输出)" : `错误: ${res.data.error}`);
    } catch (err) { setLuaOutput(err instanceof Error ? err.message : "执行失败"); }
  };

  const runScript = async (id: string) => {
    try {
      await apiClient.post(`/ui-auto/scripts/${id}/run`, {});
      toast.success("脚本已在后台执行，稍后查看执行历史");
      setTimeout(() => scripts.mutate(), 3000);
    } catch (err) { toast.error(err instanceof Error ? err.message : "启动失败"); }
  };

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-6xl px-6 py-8 lg:px-8">
        <div className="flex flex-col gap-5">
          <PageHeader
            title="UI 自动化（Unity Lua 控件）"
            description={
              <>
                Playwright 式思想操作游戏 UI：定位 → 操作 → 断言 → 截图存证；GM 命令构造前置数据。
                在<Link href="/chat?agent=unity" className="text-primary hover:underline">聊天页「UI自动化」</Link>
                可与智能体对话式编排测试。
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
              {unity.data.error ?? "无法连接 LuaRemoteServer"}。
              {unity.data.hint ?? "请在 Unity Editor 中通过 Tools > LuaTestTool 启动 Server（端口 16666）。"}
            </Card>
          )}

        {/* 快捷 Lua 控制台 */}
        <Card className="p-4">
          <div className="mb-2 flex items-center gap-1.5 text-sm font-medium">
            <TerminalSquare className="h-4 w-4" />Lua 快捷控制台
          </div>
          <div className="flex gap-2">
            <Input
              value={luaCode}
              onChange={(e) => setLuaCode(e.target.value)}
              placeholder='如: print(UI and "ok" or "no") 或 GameServer:gm("add_exp", 100)'
              onKeyDown={(e) => e.key === "Enter" && execLua()}
            />
            <Button variant="outline" onClick={execLua} className="shrink-0">执行</Button>
          </div>
          {luaOutput && (
            <pre className="mt-2 max-h-40 overflow-y-auto rounded bg-muted p-2 text-xs">{luaOutput}</pre>
          )}
        </Card>

        {/* 脚本列表 */}
        <Card className="p-0">
          <div className="flex items-center justify-between border-b px-4 py-2.5">
            <span className="text-sm font-medium">UI 测试脚本</span>
            <CreateScriptDialog onCreated={() => scripts.mutate()} />
          </div>
          {scripts.isLoading ? (
            <div className="flex items-center justify-center py-16 text-sm text-muted-foreground">
              加载中…
            </div>
          ) : (scripts.data ?? []).length === 0 ? (
            <EmptyState
              title="暂无脚本"
              description="可点击「新建脚本」，或到聊天页让 UI 自动化智能体生成"
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
                        <Button size="sm" variant="outline" onClick={() => runScript(s.id)}>
                          <Play className="mr-1 h-3.5 w-3.5" />执行
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setRunsFor(s)}>历史</Button>
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

      {runsFor && <RunsDialog script={runsFor} onClose={() => setRunsFor(null)} />}
    </div>
  );
}
