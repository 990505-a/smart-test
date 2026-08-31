"use client";

import React, { useState } from "react";
import { PageHeader, StatusBadge, EmptyState } from "@/app/components/ui-patterns";
import {
  useApiDocs, useApiScripts, useApiScriptRuns, ApiScript,
} from "@/lib/api/useNewModules";
import { apiClient } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { CloudDownload, FileCode2, Play, Wrench } from "lucide-react";

function ScriptDetail({ script, onClose, onChanged }: {
  script: ApiScript; onClose: () => void; onChanged: () => void;
}) {
  const [content, setContent] = useState(script.content ?? "");
  const [baseUrl, setBaseUrl] = useState("");
  const [autoRepair, setAutoRepair] = useState(true);
  const [running, setRunning] = useState(false);
  const [lastOutput, setLastOutput] = useState<string | null>(null);
  const runs = useApiScriptRuns(script.id);

  const save = async () => {
    try {
      await apiClient.put(`/api-auto/scripts/${script.id}`, { content });
      toast.success("已保存（版本+1）");
      onChanged();
    } catch (err) { toast.error(err instanceof Error ? err.message : "保存失败"); }
  };

  const run = async () => {
    setRunning(true);
    setLastOutput(null);
    try {
      const res = await apiClient.post<{
        status: string; repair_attempts: number; script_version: number; output_tail: string;
      }>(`/api-auto/scripts/${script.id}/run`, {
        base_url: baseUrl || null, auto_repair: autoRepair,
      });
      setLastOutput(res.data.output_tail);
      if (res.data.status === "passed") {
        toast.success(`执行通过${res.data.repair_attempts > 0 ? `（AI 自修复 ${res.data.repair_attempts} 次 → v${res.data.script_version}）` : ""}`);
      } else {
        toast.warning(`执行未通过（${res.data.status}），已尝试自修复 ${res.data.repair_attempts} 次`);
      }
      runs.mutate();
      onChanged();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "执行失败");
    } finally {
      setRunning(false);
    }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {script.name}
            <StatusBadge status={script.status} />
            <Badge variant="outline">v{script.version}</Badge>
          </DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          <div className="text-xs text-muted-foreground">
            接口文档：{script.doc_url ?? "-"} · 覆盖 {script.endpoints.length} 个接口
          </div>

          <Textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className="min-h-[320px] font-mono text-xs"
          />

          <div className="flex flex-wrap items-center gap-3">
            <div className="flex flex-col gap-1">
              <Label className="text-xs">Base URL（留空用脚本默认）</Label>
              <Input className="w-64" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)}
                     placeholder="http://localhost:8080" />
            </div>
            <div className="flex items-center gap-2 pt-4">
              <Switch checked={autoRepair} onCheckedChange={setAutoRepair} id="auto-repair" />
              <Label htmlFor="auto-repair" className="text-sm">失败时 AI 自修复</Label>
            </div>
            <div className="ml-auto flex gap-2 pt-4">
              <Button variant="outline" size="sm" onClick={save}>保存修改</Button>
              <Button size="sm" onClick={run} disabled={running}>
                <Play className="mr-1 h-3.5 w-3.5" />{running ? "执行+自修复中…" : "执行脚本"}
              </Button>
            </div>
          </div>

          {lastOutput && (
            <pre className="max-h-56 overflow-y-auto rounded bg-muted p-3 text-xs">{lastOutput}</pre>
          )}

          {/* 修复历史 */}
          {script.repair_history.length > 0 && (
            <div>
              <div className="mb-1 flex items-center gap-1 text-sm font-medium">
                <Wrench className="h-4 w-4" />AI 自修复历史
              </div>
              <div className="flex flex-col gap-1 text-xs text-muted-foreground">
                {script.repair_history.map((h, i) => (
                  <div key={i} className="rounded bg-muted/50 px-2 py-1">
                    v{h.version} · {h.at} · {h.fix_summary}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 执行历史 */}
          <div>
            <div className="mb-1 text-sm font-medium">执行历史</div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>时间</TableHead><TableHead>结果</TableHead>
                  <TableHead>触发</TableHead><TableHead>耗时</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(runs.data ?? []).map((r) => (
                  <TableRow key={r.id}>
                    <TableCell>{r.created_at ? new Date(r.created_at).toLocaleString("zh-CN") : "-"}</TableCell>
                    <TableCell>
                      <StatusBadge status={r.status} />
                    </TableCell>
                    <TableCell>{r.triggered_by}{r.repair_attempt > 0 ? ` #${r.repair_attempt}` : ""}</TableCell>
                    <TableCell>{r.duration_ms != null ? `${(r.duration_ms / 1000).toFixed(1)}s` : "-"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function ApiAutoPage() {
  const docs = useApiDocs();
  const scripts = useApiScripts();
  const [docUrl, setDocUrl] = useState("");
  const [importing, setImporting] = useState(false);
  const [genName, setGenName] = useState("");
  const [genBaseUrl, setGenBaseUrl] = useState("http://localhost:8080");
  const [genDocId, setGenDocId] = useState("");
  const [generating, setGenerating] = useState(false);
  const [selected, setSelected] = useState<ApiScript | null>(null);

  const importDoc = async () => {
    if (!docUrl.trim()) { toast.error("请输入飞书文档链接"); return; }
    setImporting(true);
    try {
      const res = await apiClient.post<{ title: string; endpoint_count: number }>(
        "/api-auto/docs/import", { doc_url: docUrl.trim() });
      toast.success(`解析出 ${res.data.endpoint_count} 个接口：${res.data.title}`);
      setDocUrl("");
      docs.mutate();
    } catch (err) { toast.error(err instanceof Error ? err.message : "导入失败"); }
    finally { setImporting(false); }
  };

  const generate = async () => {
    if (!genDocId || !genName.trim()) { toast.error("请选择文档并输入脚本名"); return; }
    setGenerating(true);
    try {
      await apiClient.post("/api-auto/scripts/generate", {
        import_id: genDocId, name: genName.trim(), base_url: genBaseUrl,
      });
      toast.success("第一版脚本已生成");
      setGenName("");
      scripts.mutate();
    } catch (err) { toast.error(err instanceof Error ? err.message : "生成失败"); }
    finally { setGenerating(false); }
  };

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-6xl px-6 py-8 lg:px-8">
        <div className="flex flex-col gap-5">
          <PageHeader
            title="接口自动化"
            description="飞书接口文档 → AI 初始化 pytest 脚本 → 执行；脚本异常时 AI 对照接口文档自修复"
          />

          {/* 导入飞书文档 */}
          <Card className="p-4">
            <div className="mb-2 text-sm font-medium">第一步：从飞书导入接口文档</div>
            <div className="flex gap-2">
              <Input
                value={docUrl}
                onChange={(e) => setDocUrl(e.target.value)}
                placeholder="https://xxx.feishu.cn/docx/... 或 wiki 链接"
              />
              <Button onClick={importDoc} disabled={importing} className="shrink-0">
                <CloudDownload className="mr-1.5 h-4 w-4" />{importing ? "解析中…" : "导入并解析"}
              </Button>
            </div>
            {(docs.data ?? []).length > 0 && (
              <div className="mt-3 flex flex-col gap-1">
                {docs.data!.map((d) => {
                  const selectedDoc = genDocId === d.id;
                  return (
                    <label
                      key={d.id}
                      className={cn(
                        "flex cursor-pointer items-center gap-2 rounded-lg border px-2 py-1.5 text-sm transition-colors",
                        selectedDoc ? "border-brand bg-brand-soft" : "border-transparent hover:bg-accent",
                      )}
                    >
                      <input
                        type="radio" name="doc" checked={selectedDoc}
                        onChange={() => setGenDocId(d.id)}
                        className="sr-only"
                      />
                      <span className={cn("flex h-4 w-4 shrink-0 items-center justify-center rounded-full border", selectedDoc ? "border-brand" : "border-input")}>
                        {selectedDoc && <span className="h-2 w-2 rounded-full bg-brand" />}
                      </span>
                      <span className="flex-1 truncate">{d.title}</span>
                      <Badge variant={d.status === "parsed" ? "default" : "destructive"}>
                        {d.endpoint_count} 接口
                      </Badge>
                    </label>
                  );
                })}
              </div>
            )}
          </Card>

          {/* 生成脚本 */}
          <Card className="p-4">
            <div className="mb-2 text-sm font-medium">第二步：AI 生成第一版脚本</div>
            <div className="flex flex-wrap gap-2">
              <Input
                className="w-64" value={genName} onChange={(e) => setGenName(e.target.value)}
                placeholder="脚本名，如：赛季系统接口测试"
              />
              <Input
                className="w-64" value={genBaseUrl} onChange={(e) => setGenBaseUrl(e.target.value)}
                placeholder="Base URL"
              />
              <Button onClick={generate} disabled={generating || !genDocId} variant="outline">
                <FileCode2 className="mr-1.5 h-4 w-4" />{generating ? "生成中…" : "生成脚本"}
              </Button>
            </div>
          </Card>

          {/* 脚本列表 */}
          <Card className="p-0">
            <div className="border-b px-4 py-2.5 text-sm font-medium">脚本</div>
            {scripts.isLoading ? (
              <div className="flex items-center justify-center py-16 text-sm text-muted-foreground">
                加载中…
              </div>
            ) : (scripts.data ?? []).length === 0 ? (
              <EmptyState
                title="暂无脚本"
                description="先从飞书导入接口文档，再由 AI 生成第一版脚本"
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>名称</TableHead><TableHead>状态</TableHead><TableHead>版本</TableHead>
                    <TableHead>接口数</TableHead><TableHead>自修复</TableHead><TableHead>更新时间</TableHead>
                    <TableHead></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(scripts.data ?? []).map((s) => (
                    <TableRow key={s.id}>
                      <TableCell className="font-medium">{s.name}</TableCell>
                      <TableCell>
                        <StatusBadge status={s.status} />
                      </TableCell>
                      <TableCell>v{s.version}</TableCell>
                      <TableCell>{s.endpoints.length}</TableCell>
                      <TableCell>{s.repair_history.length} 次</TableCell>
                      <TableCell className="text-muted-foreground">
                        {s.updated_at ? new Date(s.updated_at).toLocaleString("zh-CN") : "-"}
                      </TableCell>
                      <TableCell>
                        <Button size="sm" variant="ghost" onClick={() => setSelected(s)}>打开</Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Card>
        </div>
      </div>

      {selected && (
        <ScriptDetail
          script={selected}
          onClose={() => setSelected(null)}
          onChanged={() => scripts.mutate()}
        />
      )}
    </div>
  );
}
