"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { PageHeader, StatusBadge, EmptyState } from "@/app/components/ui-patterns";
import {
  useEvalStatus, useEvalDatasets, useEvalBatches, useEvalBatch, useEvalDatasetDetail,
  type EvalBatch, type EvalCase, type EvalScore,
} from "@/lib/api/useNewModules";
import { apiClient } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { Play, Loader2, ExternalLink, GitCompare } from "lucide-react";
import { BatchLivePanel } from "@/app/components/eval/BatchLivePanel";
import { DatasetManager } from "@/app/components/eval/DatasetManager";

/**
 * Langfuse 的界面路由是 `/project/<projectId>/traces/<traceId>`，项目 id 从
 * 状态接口取。**少了这段就是 404** —— 之前这里硬编码了空项目 id 再把
 * `/project//` 替换掉，生成的正是一个打不开的链接；宁可只显示 trace id，
 * 也不要给用户一个错误地址。
 */
function langfuseTraceUrl(
  host: string | null, traceId: string | null, projectId: string | null | undefined,
): string | null {
  if (!host || !traceId || !projectId) return null;
  // 容器内的地址（host.docker.internal）在浏览器里指不到，换成 localhost
  const base = host.replace("host.docker.internal", "localhost").replace(/\/$/, "");
  return `${base}/project/${encodeURIComponent(projectId)}/traces/${traceId}`;
}

function scoreBadge(s: EvalScore) {
  if (typeof s.value === "boolean" || s.data_type === "BOOLEAN") {
    const ok = s.value === true || s.value === 1;
    return <Badge key={s.name} variant={ok ? "secondary" : "destructive"} className="font-normal">{s.name} {ok ? "✓" : "✗"}</Badge>;
  }
  if (typeof s.value === "number") {
    const ok = s.value >= 0.6;
    return <Badge key={s.name} variant="outline" className={`font-normal ${ok ? "text-success" : "text-destructive"}`}>{s.name} {s.value.toFixed(2)}</Badge>;
  }
  return <Badge key={s.name} variant="outline" className="font-normal">{s.name} {String(s.value)}</Badge>;
}

function StartDialog({ onStarted }: { onStarted: () => void }) {
  const datasets = useEvalDatasets();
  const [open, setOpen] = useState(false);
  // 多选数据集：批次是一数据集一 agent 的，多选 = 起多个批次（可以一次把几个
  // 集子都跑起来），但每个批次的结论各自独立。
  const [files, setFiles] = useState<string[]>([]);
  const [agent, setAgent] = useState("");
  const [concurrency, setConcurrency] = useState("1");
  const [release, setRelease] = useState("");
  const [gate, setGate] = useState("");
  const [running, setRunning] = useState(false);
  // 数据集内自定义选择用例（只在选中单个数据集时提供——多选时"哪条用例属于谁"
  // 会变得难以表达，而冒烟几条的诉求本来就是针对某一个集子的）
  const [pickedItems, setPickedItems] = useState<string[] | null>(null);
  const detail = useEvalDatasetDetail(files.length === 1 ? files[0] : null, files.length === 1);

  const rows = useMemo(() => datasets.data ?? [], [datasets.data]);

  // 选中数据集时自动填上推荐门禁与 agent
  useEffect(() => {
    const picked = rows.find((d) => d.file === files[0]);
    if (!picked) return;
    if (picked.gate_hint) setGate(picked.gate_hint);
    if (picked.agent) setAgent(picked.agent);
  }, [files, rows]);

  // 换数据集后重置用例选择（默认全选）
  const soloFile = files.length === 1 ? files[0] : "";
  useEffect(() => {
    setPickedItems(null);
  }, [soloFile]);

  const toggleFile = (file: string) => {
    setFiles((prev) => prev.includes(file) ? prev.filter((f) => f !== file) : [...prev, file]);
  };

  const allItems = detail.data?.items ?? [];
  const selectedItems = pickedItems ?? allItems.map((item) => item.id);

  const start = async () => {
    if (files.length === 0) { toast.error("请选择至少一个评测集"); return; }
    const onlyOne = files.length === 1;
    const itemIds = onlyOne && pickedItems !== null && pickedItems.length < allItems.length
      ? pickedItems : [];
    if (onlyOne && pickedItems !== null && pickedItems.length === 0) {
      toast.error("至少要勾选一条用例，或者点「全选」");
      return;
    }
    setRunning(true);
    try {
      await apiClient.post("/eval/run", {
        datasets: files,
        agent: agent || null,
        concurrency: Number(concurrency) || 1,
        release: release || null,
        gate: gate || null,
        item_ids: itemIds,
      });
      toast.success(files.length > 1
        ? `已启动 ${files.length} 个批次，可在下方列表查看进度`
        : `测评批次已启动${itemIds.length ? `（${itemIds.length} 条用例）` : ""}`);
      setOpen(false);
      onStarted();
    } catch (err) { toast.error(err instanceof Error ? err.message : "启动失败"); }
    finally { setRunning(false); }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button size="sm" onClick={() => setOpen(true)}>
        <Play className="mr-1.5 h-4 w-4" />启动测评
      </Button>
      <DialogContent className="sm:max-w-2xl max-h-[88vh] overflow-y-auto">
        <DialogHeader><DialogTitle>启动测评批次</DialogTitle></DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label>评测集 * （可多选，每个集子起一个批次）</Label>
            <div className="rounded border">
              {rows.length === 0 ? (
                <p className="px-3 py-4 text-sm text-muted-foreground">还没有评测集，先在上面新建或用 AI 生成</p>
              ) : (
                <ul className="max-h-56 divide-y overflow-y-auto">
                  {rows.map((d) => (
                    <li key={d.file}>
                      <label className={`flex cursor-pointer items-start gap-2 px-3 py-2 hover:bg-muted/40 ${d.error ? "opacity-60" : ""}`}>
                        <input type="checkbox" className="mt-1" disabled={Boolean(d.error)}
                               checked={files.includes(d.file)}
                               onChange={() => toggleFile(d.file)} />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm">
                            {d.name ?? d.file}
                            {d.error ? "（加载失败）" : ""}
                          </span>
                          <span className="font-mono text-[11px] text-muted-foreground">
                            {d.file} · {d.items ?? 0} 条 · {d.agent}
                          </span>
                        </span>
                      </label>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          {/* 单个数据集时：选具体跑哪几条（先冒烟 2 条再全量是常用做法） */}
          {files.length === 1 && (
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between">
                <Label>
                  用例选择
                  <span className="ml-1 text-xs font-normal text-muted-foreground">
                    已选 {selectedItems.length}/{allItems.length}
                  </span>
                </Label>
                <div className="flex gap-1">
                  <Button size="sm" variant="ghost"
                          onClick={() => setPickedItems(allItems.map((i) => i.id))}>全选</Button>
                  <Button size="sm" variant="ghost"
                          onClick={() => setPickedItems([])}>全不选</Button>
                </div>
              </div>
              {detail.isLoading ? (
                <p className="text-xs text-muted-foreground">读取用例…</p>
              ) : allItems.length === 0 ? (
                <p className="text-xs text-muted-foreground">这个集子解析不出用例</p>
              ) : (
                <ul className="max-h-56 divide-y overflow-y-auto rounded border">
                  {allItems.map((item) => (
                    <li key={item.id}>
                      <label className="flex cursor-pointer items-start gap-2 px-3 py-1.5 hover:bg-muted/40">
                        <input type="checkbox" className="mt-1"
                               checked={selectedItems.includes(item.id)}
                               onChange={() => setPickedItems(
                                 selectedItems.includes(item.id)
                                   ? selectedItems.filter((id) => id !== item.id)
                                   : [...selectedItems, item.id])} />
                        <span className="min-w-0 flex-1">
                          <span className="font-mono text-xs">{item.id}</span>
                          <span className="ml-2 text-xs text-muted-foreground">
                            {item.input.slice(0, 80)}{item.input.length > 80 ? "…" : ""}
                          </span>
                        </span>
                      </label>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          <div className="grid grid-cols-3 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>被测 agent</Label>
              <Input value={agent} onChange={(e) => setAgent(e.target.value)} placeholder="webui_agent" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>并发</Label>
              <Input type="number" min={1} value={concurrency} onChange={(e) => setConcurrency(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>批次标签</Label>
              <Input value={release} onChange={(e) => setRelease(e.target.value)} placeholder="v1" />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>门禁表达式（留空则不设门禁）</Label>
            <Input value={gate} onChange={(e) => setGate(e.target.value)}
                   className="font-mono text-xs" placeholder="avg(task_output_match)>=0.8 && all(tool_sequence)" />
            <p className="text-xs text-muted-foreground">
              语法：avg/min/max(分数名)比较值，或 all(布尔分数名)。门禁里写了没人产出的分数会直接判失败。
            </p>
          </div>
          <Button onClick={start} disabled={running || files.length === 0}>
            {running && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
            启动{files.length > 1 ? `（${files.length} 个批次）` : ""}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function CaseRow({ c, host, projectId }: {
  c: EvalCase; host: string | null; projectId?: string | null;
}) {
  const url = langfuseTraceUrl(host, c.trace_id, projectId);
  return (
    <>
      <TableRow>
        <TableCell className="font-medium">{c.item_id}</TableCell>
        <TableCell><StatusBadge status={c.status === "ok" ? "passed" : "failed"} /></TableCell>
        <TableCell>
          <div className="flex flex-wrap gap-1">{c.scores.map(scoreBadge)}</div>
        </TableCell>
        <TableCell className="text-xs text-muted-foreground">
          {c.tool_names.length ? c.tool_names.join(", ") : "-"}
        </TableCell>
        <TableCell className="text-muted-foreground">
          {c.duration_ms != null ? `${(c.duration_ms / 1000).toFixed(1)}s` : "-"}
        </TableCell>
        <TableCell>
          {url && (
            <a href={url} target="_blank" rel="noreferrer"
               className="inline-flex items-center gap-1 text-xs text-primary hover:underline">
              trace<ExternalLink className="h-3 w-3" />
            </a>
          )}
        </TableCell>
      </TableRow>
      {(c.error || c.evidence.length > 0 || c.scores.some((s) => s.comment)) && (
        <TableRow>
          <TableCell colSpan={6} className="bg-muted/30">
            {c.error && <p className="text-xs text-destructive">错误：{c.error}</p>}
            {c.evidence.length > 0 && (
              <p className="mt-1 font-mono text-[11px] text-muted-foreground">
                存证：{c.evidence.slice(0, 6).map((e) => e.name).join(" · ")}
              </p>
            )}
            <ul className="mt-1 space-y-0.5 text-[11px] text-muted-foreground">
              {c.scores.filter((s) => s.comment).map((s) => (
                <li key={s.name}><span className="font-mono">{s.name}</span>：{s.comment}</li>
              ))}
            </ul>
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

function BatchDialog({ batch, onClose, onFinished }: {
  batch: EvalBatch; onClose: () => void; onFinished?: () => void;
}) {
  const detail = useEvalBatch(batch.id);
  const status = useEvalStatus();
  const cases = detail.data?.cases ?? [];
  const host = detail.data?.langfuse_host ?? batch.langfuse_host;
  const projectId = status.data?.langfuse?.project_id;
  const live = detail.data ?? batch;
  const running = live.status === "running";
  const outputText = detail.data?.output ?? batch.output ?? "";
  // 跑完那一刻补一次详情刷新：detail 的轮询在状态翻成终态后就停了
  // （refreshInterval 返回 0），不主动拉一次的话表头会永远停在"运行中 / 0/N"。
  const handleFinished = useCallback(() => {
    detail.mutate();
    onFinished?.();
  }, [detail, onFinished]);
  // 追踪链路断了却看起来一切正常，是最难查的故障——所以在标题栏直接标出来，
  // 而不是把一句警告埋在下面的日志块里。
  const reportingBroken = /一条都没上报成功|上报：未启用/.test(outputText);
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="sm:max-w-5xl max-h-[88vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {batch.run_name}
            {running && !live.stale && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
            {live.stale && <Badge variant="destructive" className="font-normal">疑似中断</Badge>}
            {reportingBroken && (
              <Badge variant="destructive" className="font-normal">
                Langfuse 未上报
              </Badge>
            )}
          </DialogTitle>
        </DialogHeader>

        <div className="flex flex-wrap items-center gap-3 text-sm">
          <StatusBadge status={live.status} />
          <span className="text-muted-foreground">agent={live.agent}</span>
          <span className="text-muted-foreground">
            用例 {live.done_cases}/{live.total_cases}
            {live.scored_cases < live.done_cases ? ` · 有分数 ${live.scored_cases}` : ""}
          </span>
          {live.failed_cases > 0 && (
            <Badge variant="destructive" className="font-normal">
              执行异常 {live.failed_cases}
            </Badge>
          )}
        </div>

        {/* 执行中（或没跑完的记录）显示实时现场：这次执行到哪一步、agent 正在调
            什么工具、输出到哪里。跑完就收起来——那时表头与用例表才是答案。 */}
        {(running || live.done_cases < live.total_cases) && (
          <BatchLivePanel batch={batch} onFinished={handleFinished} />
        )}

        {Object.keys(live.averages ?? {}).length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(live.averages).map(([name, value]) => (
              <Badge key={name} variant="outline" className="font-normal">
                {name} <span className="ml-1 font-mono">{value.toFixed(3)}</span>
              </Badge>
            ))}
          </div>
        )}

        {(live.gate_output) && (
          <pre className="rounded bg-muted p-3 text-xs leading-5">{live.gate_output}</pre>
        )}

        {cases.length === 0 ? (
          running
            ? <p className="py-6 text-center text-sm text-muted-foreground">
                还没有用例跑完。第一条跑完会立刻出现在这里。
              </p>
            : <p className="py-6 text-center text-sm text-muted-foreground">暂无用例结果</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>用例</TableHead><TableHead>状态</TableHead><TableHead>分数</TableHead>
                <TableHead>工具</TableHead><TableHead>耗时</TableHead><TableHead>链路</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {cases.map((c) => <CaseRow key={c.id} c={c} host={host} projectId={projectId} />)}
            </TableBody>
          </Table>
        )}

        {running && cases.length > 0 && (
          <p className="text-[11px] text-muted-foreground">
            表格每 2 秒刷新一次：用例是跑一条落一条的，上面的进度与列表都是实时值。
          </p>
        )}

        {outputText && (
          <pre className="max-h-48 overflow-y-auto rounded bg-muted p-3 text-[11px]">
            {outputText}
          </pre>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default function EvalPage() {
  const status = useEvalStatus();
  const batches = useEvalBatches();
  const [openBatch, setOpenBatch] = useState<EvalBatch | null>(null);
  const lf = status.data?.langfuse;

  const langfuseBadge = lf?.enabled && lf.reachable ? (
    <a href={lf.host.replace("host.docker.internal", "localhost")} target="_blank" rel="noreferrer"
       className="text-sm text-primary hover:underline">
      Langfuse 已连接
    </a>
  ) : (
    <Badge variant="destructive">Langfuse 不可达</Badge>
  );

  const rows = batches.data ?? [];

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-6xl px-6 py-8 lg:px-8">
        <div className="flex flex-col gap-5">
          <PageHeader
            title="智能体测评（Eval）"
            description={
              <>
                观测(Trace) → 沉淀(Dataset) → 实验(Runner + Scorer) → 回归(Gate)：
                跑评测集、按确定性打分器与 LLM-as-judge 评分、分数上报 Langfuse，最后用门禁表达式判定。
                设计说明见 <code className="text-xs">EVAL.md</code>。
              </>
            }
            actions={
              <div className="flex items-center gap-2">
                {langfuseBadge}
                <StartDialog onStarted={() => batches.mutate()} />
              </div>
            }
          />

          <Card className="flex flex-wrap items-center gap-x-6 gap-y-2 p-3 text-sm">
            <span className="text-muted-foreground">
              judge：<span className="font-mono">{status.data?.judge.model ?? "-"}</span>
              {/* 只显示模型名会被误读成"我配过"——这里必须说明它从哪来 */}
              {status.data?.judge.source && status.data.judge.source !== "judge" && (
                <span className="ml-1 text-xs">（继承主 LLM，可在设置页配置独立裁判）</span>
              )}
              {status.data?.judge.source === "judge" && (
                <span className="ml-1 text-xs">（独立配置）</span>
              )}
              {status.data?.judge.configured ? "" : "（未配置 API Key）"}
            </span>
            <span className="text-muted-foreground">
              Langfuse：<span className="font-mono">{(lf?.host ?? "-").replace("host.docker.internal", "localhost")}</span>
            </span>
            <span className="text-muted-foreground">
              评测集目录：<span className="font-mono">{status.data?.datasets_dir ?? "-"}</span>
            </span>
          </Card>

          <DatasetManager />

          <Card className="p-0">
            <div className="flex items-center justify-between border-b px-4 py-2.5">
              <span className="flex items-center gap-1.5 text-sm font-medium">
                <GitCompare className="h-4 w-4" />测评批次
              </span>
              <Button size="sm" variant="ghost" onClick={() => batches.mutate()}>刷新</Button>
            </div>
            {batches.isLoading ? (
              <div className="flex items-center justify-center py-16 text-sm text-muted-foreground">加载中…</div>
            ) : rows.length === 0 ? (
              <EmptyState
                title="暂无测评批次"
                description="点击右上角「启动测评」选择评测集；也可在命令行用 python -m src.app.eval.cli 跑"
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>批次</TableHead><TableHead>被测 agent</TableHead>
                    <TableHead>状态</TableHead><TableHead>门禁</TableHead>
                    <TableHead>用例</TableHead><TableHead>均分</TableHead>
                    <TableHead>时间</TableHead><TableHead className="text-right">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((b) => (
                    <TableRow key={b.id}>
                      <TableCell className="font-medium">{b.run_name}</TableCell>
                      <TableCell className="font-mono text-xs">{b.agent}</TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1.5">
                          <StatusBadge status={b.status} />
                          {b.status === "running" && !b.stale
                            && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
                          {b.status === "running" && b.stale && (
                            <Badge variant="destructive" className="font-normal">疑似中断</Badge>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        {b.gate_passed === null ? <span className="text-muted-foreground">-</span>
                          : b.gate_passed
                            ? <Badge variant="secondary" className="font-normal">通过</Badge>
                            : <Badge variant="destructive" className="font-normal">未通过</Badge>}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {b.status === "running"
                          ? <span className="font-mono">{b.done_cases}/{b.total_cases} 跑完</span>
                          : `${b.done_cases}/${b.total_cases}`}
                        {b.failed_cases > 0 && <span className="ml-1 text-destructive">({b.failed_cases} 异常)</span>}
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {Object.entries(b.averages).slice(0, 2).map(([k, v]) => `${k}=${v.toFixed(2)}`).join(" ")}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {b.created_at ? new Date(b.created_at).toLocaleString("zh-CN") : "-"}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button size="sm" variant="outline" onClick={() => setOpenBatch(b)}>详情</Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Card>

          <Card className="p-3 text-xs leading-5 text-muted-foreground">
            命令行等价用法：
            <code className="ml-1 font-mono">
              .venv/bin/python -m src.app.eval.cli --dataset datasets/douban-webui.yaml --concurrency 2
              --release v1 --gate &quot;avg(task_output_match)&gt;=0.8 &amp;&amp; all(tool_sequence)&quot; --verify-trace
            </code>
            （退出码 0/1 可直接做 CI 回归门禁）
          </Card>
        </div>
      </div>

      {openBatch && (
        <BatchDialog
          batch={openBatch}
          onClose={() => setOpenBatch(null)}
          onFinished={() => batches.mutate()}
        />
      )}
    </div>
  );
}
