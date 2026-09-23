"use client";

import React, { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
import { CircleDot, ListTree, Loader2, Square, Trash2, Wand2 } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import {
  useUnityRecordings, useUnityRecordStatus, useUnityStatus,
  type UnityRecording, type UnityRecordingEvent,
} from "@/lib/api/useNewModules";

/** 事件类型 → 中文（前端表格展示用）。 */
const EVENT_LABELS: Record<string, string> = {
  click: "点击", drag: "拖拽", text: "输入文本", key: "按键",
  scene: "场景", play: "Play 状态",
};

function eventSummary(e: UnityRecordingEvent): string {
  switch (e.type) {
    case "click":
      return [e.path, e.label ? `「${e.label}」` : "", e.comp ? `(${e.comp})` : ""]
        .filter(Boolean).join(" ");
    case "drag":
      return `${e.from ?? ""} → ${e.to ?? ""}`;
    case "text":
      return `${e.path ?? ""} = ${JSON.stringify(e.text ?? "")}`;
    case "key":
      return e.key ?? "";
    case "scene":
      return e.path || e.name || "";
    case "play":
      return e.value ? "进入 Play" : "退出 Play";
    default:
      return JSON.stringify(e);
  }
}

/**
 * Unity 手动录制面板：玩家在编辑器里正常玩，平台把操作录成可回放的用例脚本。
 *
 * 交互契约（与后端一致）：
 * - 必须**先在 Unity 里点 Play**，再点「开始录制」——进 Play 会触发域重载，
 *   先录再进 Play 的话钩子会被清掉（平台会自动重挂，但那一小段会丢）。
 * - 录制期间状态每 2 秒轮询一次，顺带做心跳自愈（域重载后自动重挂）。
 */
export function RecordingPanel({ onScriptSaved }: { onScriptSaved?: () => void }) {
  const unity = useUnityStatus();
  const recordings = useUnityRecordings();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  // 本地"正在录"标志：点开始/停止后立刻反映；由状态轮询确认服务端实况。
  // 刷新页面后本地标志会丢 —— 用录制列表里 status=recording 的那条兜底，
  // 否则"正在录"却看不到停止按钮（录制还在 Unity 侧跑着）。
  const [recordingId, setRecordingId] = useState<string | null>(null);
  const listActiveId = (recordings.data ?? []).find((r) => r.status === "recording")?.id ?? null;
  const status = useUnityRecordStatus(!!recordingId || !!listActiveId);
  const activeId = recordingId ?? listActiveId ?? status.data?.active ?? null;
  const liveEvents = status.data?.events ?? 0;

  const [eventsFor, setEventsFor] = useState<{ rec: UnityRecording; events: UnityRecordingEvent[] } | null>(null);
  const [pendingDelete, setPendingDelete] = useState<UnityRecording | null>(null);
  const [scriptFor, setScriptFor] = useState<UnityRecording | null>(null);
  const [scriptPreview, setScriptPreview] = useState("");
  const [scriptName, setScriptName] = useState("");
  const [scriptBusy, setScriptBusy] = useState(false);

  const bridgeReady = !!unity.data?.available && unity.data?.unity_connected !== false;
  const inPlay = !!unity.data?.is_playing;

  const start = async () => {
    setBusy(true);
    try {
      const res = await apiClient.post<{ id: string }>("/unity-auto/record/start", { name });
      setRecordingId(res.data.id);
      recordings.mutate();
      toast.success("已开始录制：现在在 Unity 里正常玩即可（点按/拖拽/输入都会录下来）");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "开始录制失败");
    } finally { setBusy(false); }
  };

  const stop = async () => {
    setBusy(true);
    try {
      const res = await apiClient.post<{ events: number; steps: number; id: string }>(
        "/unity-auto/record/stop", {});
      setRecordingId(null);
      recordings.mutate();
      toast.success(`已停止：录到 ${res.data.events} 条事件（${res.data.steps} 步操作），` +
        "点「生成用例」把操作变成可回放的用例");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "停止录制失败");
    } finally { setBusy(false); }
  };

  const openEvents = async (rec: UnityRecording) => {
    try {
      const res = await apiClient.get<{ events: UnityRecordingEvent[] }>(
        `/unity-auto/recordings/${rec.id}`);
      setEventsFor({ rec, events: res.data.events ?? [] });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "读取事件失败");
    }
  };

  const openScript = async (rec: UnityRecording) => {
    setScriptBusy(true);
    setScriptFor(rec);
    setScriptName(`${rec.name}（录制）`);
    setScriptPreview("");
    try {
      const res = await apiClient.post<{ script: string }>(
        `/unity-auto/recordings/${rec.id}/to-script`, { save: false });
      setScriptPreview(res.data.script);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "生成脚本失败");
      setScriptFor(null);
    } finally { setScriptBusy(false); }
  };

  const saveScript = async () => {
    if (!scriptFor) return;
    setScriptBusy(true);
    try {
      const res = await apiClient.post<{ script_id: string | null }>(
        `/unity-auto/recordings/${scriptFor.id}/to-script`,
        { save: true, name: scriptName.trim() || undefined });
      toast.success(res.data.script_id
        ? "已存入用例库（draft）：跑通一次才会转 active"
        : "已生成");
      setScriptFor(null);
      recordings.mutate();
      onScriptSaved?.();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "保存失败");
    } finally { setScriptBusy(false); }
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    try {
      await apiClient.delete(`/unity-auto/recordings/${pendingDelete.id}`);
      toast.success("录制已删除");
      setPendingDelete(null);
      recordings.mutate();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "删除失败");
    }
  };

  return (
    <Card className="p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-sm font-medium">
          <CircleDot className={`h-4 w-4 ${activeId ? "text-destructive" : ""}`} />
          手动录制
          <span className="text-xs font-normal text-muted-foreground">
            （你在 Unity 里点游戏，平台把操作录成可回放的用例）
          </span>
        </span>
        {activeId && (
          <Badge variant="destructive" className="font-normal">
            录制中 · 已录 {liveEvents} 条
            {status.data?.rearmed ? " · 钩子已自动重挂" : ""}
          </Badge>
        )}
      </div>

      {!bridgeReady && (
        <p className="mb-2 text-xs text-warning">
          {unity.data?.error ?? "Unity MCP 桥未连接"}：先让桥与 Unity 编辑器连上，再开始录制。
        </p>
      )}
      {bridgeReady && !inPlay && !activeId && (
        <p className="mb-2 text-xs text-warning">
          现在不在 Play Mode：请**先在 Unity 里点 Play**（平台不代管 Play），再回来点「开始录制」——
          进 Play 会触发域重载，先录后 Play 的话前面那段会丢。
        </p>
      )}

      <div className="flex flex-wrap items-end gap-2">
        <div className="flex min-w-[220px] flex-1 flex-col gap-1.5">
          <Label className="text-xs">录制名（可留空）</Label>
          <Input value={name} onChange={(e) => setName(e.target.value)}
                 placeholder="如：背包打开流程"
                 disabled={!!activeId || busy} />
        </div>
        {activeId ? (
          <Button variant="destructive" onClick={stop} disabled={busy}>
            {busy ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                  : <Square className="mr-1.5 h-4 w-4" />}
            停止并保存
          </Button>
        ) : (
          <Button onClick={start} disabled={busy || !bridgeReady}>
            {busy ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                  : <CircleDot className="mr-1.5 h-4 w-4" />}
            开始录制
          </Button>
        )}
      </div>

      <p className="mt-2 text-[11px] leading-4 text-muted-foreground">
        录制的是**语义目标**（对象路径）而不是坐标：点击记「点了哪个控件」、拖拽记起止对象、
        输入框只记最终文本。停止后可「生成用例」——平台会顺手播种断言（点开的面板 = 应有断言），
        生成的脚本先存 draft，跑通一次才算 active。
      </p>

      {(recordings.data ?? []).length > 0 && (
        <div className="mt-4 border-t pt-3">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>录制</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>事件</TableHead>
                <TableHead>时长</TableHead>
                <TableHead>场景</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(recordings.data ?? []).map((rec) => (
                <TableRow key={rec.id}>
                  <TableCell className="font-medium">
                    {rec.name}
                    <span className="ml-2 text-[11px] text-muted-foreground">
                      {rec.created_at ? new Date(rec.created_at).toLocaleString("zh-CN") : ""}
                    </span>
                  </TableCell>
                  <TableCell>
                    {rec.status === "recording"
                      ? <Badge variant="destructive" className="font-normal">录制中</Badge>
                      : <Badge variant="secondary" className="font-normal">已录制</Badge>}
                  </TableCell>
                  <TableCell>
                    {rec.events} 条 / {rec.steps} 步
                    {rec.stopped_reason ? (
                      <span className="ml-1 text-[10px] text-muted-foreground">
                        （{rec.stopped_reason}）
                      </span>
                    ) : null}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {rec.duration_s != null ? `${rec.duration_s}s` : "-"}
                  </TableCell>
                  <TableCell className="max-w-[16rem] truncate text-muted-foreground"
                             title={rec.scene}>
                    {rec.scene || "-"}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1.5">
                      <Button size="sm" variant="outline"
                              disabled={rec.status === "recording" || rec.events === 0}
                              onClick={() => openScript(rec)}>
                        <Wand2 className="mr-1 h-3.5 w-3.5" />生成用例
                      </Button>
                      <Button size="sm" variant="ghost" disabled={rec.events === 0}
                              onClick={() => openEvents(rec)}>
                        <ListTree className="mr-1 h-3.5 w-3.5" />事件
                      </Button>
                      <Button size="sm" variant="ghost" title="删除这条录制"
                              disabled={rec.status === "recording"}
                              onClick={() => setPendingDelete(rec)}>
                        <Trash2 className="h-3.5 w-3.5 text-destructive" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* 事件查看 */}
      <Dialog open={eventsFor !== null} onOpenChange={(o) => !o && setEventsFor(null)}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>{eventsFor?.rec.name} · 原始事件（{eventsFor?.events.length ?? 0}）</DialogTitle>
          </DialogHeader>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-16">#</TableHead>
                <TableHead className="w-20">时间</TableHead>
                <TableHead className="w-20">类型</TableHead>
                <TableHead>内容</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(eventsFor?.events ?? []).map((e, i) => (
                <TableRow key={i}>
                  <TableCell className="text-muted-foreground">{i + 1}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {typeof e.t === "number" ? `${e.t.toFixed(1)}s` : "-"}
                  </TableCell>
                  <TableCell>{EVENT_LABELS[e.type] ?? e.type}</TableCell>
                  <TableCell className="break-all font-mono text-[11px]">
                    {eventSummary(e)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <p className="text-[11px] text-muted-foreground">
            这里是被录下来的原始事件；「生成用例」会把它们翻译成平台风格的 Python 用例
            （点击 → u.click、拖拽 → u.drag、输入 → u.set_text、按键 → u.key）。
          </p>
        </DialogContent>
      </Dialog>

      {/* 生成用例（预览 + 存入用例库） */}
      <Dialog open={scriptFor !== null} onOpenChange={(o) => !o && setScriptFor(null)}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>{scriptFor?.name} · 生成用例脚本</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <Label className="text-xs">用例名</Label>
              <Input value={scriptName} onChange={(e) => setScriptName(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label className="text-xs">脚本预览（平台风格；断言为自动播种，标 [自动播种]）</Label>
              <pre className="max-h-[45vh] overflow-auto rounded bg-muted p-3 font-mono text-[11px] leading-5">
                {scriptBusy && !scriptPreview ? "生成中…" : scriptPreview}
              </pre>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setScriptFor(null)} disabled={scriptBusy}>
                取消
              </Button>
              <Button onClick={saveScript} disabled={scriptBusy || !scriptPreview}>
                {scriptBusy ? "处理中…" : "存入用例库（draft）"}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* 删除确认 */}
      <AlertDialog open={pendingDelete !== null}
                   onOpenChange={(o) => { if (!o) setPendingDelete(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除录制「{pendingDelete?.name}」？</AlertDialogTitle>
            <AlertDialogDescription>
              会删掉这条录制的事件数据与已生成的脚本文件（用例库里单独保存过的用例不受影响）。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete}>删除</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
