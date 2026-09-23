"use client";

import React, { useState } from "react";
import { useQueryState, parseAsString } from "nuqs";
import { PageHeader, StatusBadge, EmptyState, Pagination } from "@/app/components/ui-patterns";
import { apiClient } from "@/lib/api-client";
import useSWR from "swr";
import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { toast } from "sonner";
import {
  RefreshCw, Loader2, CheckCircle2, XCircle, ExternalLink, Search, Play,
  RotateCcw, Square, Settings2,
} from "lucide-react";

/** LightRAG 的检索模式（与服务端 QUERY_MODES 一致，1.5.x 起有 bypass）。 */
const QUERY_MODES = [
  { value: "hybrid", label: "hybrid（图谱混合，推荐）" },
  { value: "local", label: "local（实体邻域）" },
  { value: "global", label: "global（主题全局）" },
  { value: "naive", label: "naive（纯向量）" },
  { value: "mix", label: "mix（图谱+向量）" },
  { value: "bypass", label: "bypass（不检索，直接问模型）" },
];

/** 文档状态筛选（服务端 DocStatus）。空 = 全部。 */
const DOC_STATUSES = [
  { value: "processed", label: "已处理" },
  { value: "pending", label: "待处理" },
  { value: "processing", label: "处理中" },
  { value: "failed", label: "失败" },
];

interface KbInfo {
  key: string;
  label: string;
  port: number;
  description: string;
  workspace: string;
  base_url: string;
  webui_url: string;
  settings_url: string;
  data_dir: string;
  reachable?: boolean;
  error?: string | null;
  documents?: number | null;
}

interface RagOverview {
  kb: KbInfo;
  reachable: boolean;
  error?: string | null;
  health: {
    core_version?: string;
    api_version?: string;
    working_directory?: string;
    workspace?: string;
    llm_model?: string;
    llm_binding_host?: string;
    llm_upstream?: string;
    embedding_model?: string;
    embedding_binding_host?: string;
    kv_storage?: string;
    graph_storage?: string;
    vector_storage?: string;
    pipeline_busy?: boolean;
  } | null;
  status_counts: Record<string, number> | null;
  counts_error?: string | null;
  pipeline: {
    busy?: boolean;
    job_name?: string;
    docs?: number;
    batchs?: number;
    cur_batch?: number;
    latest_message?: string;
    recovery_required?: boolean;
  } | null;
  pipeline_error?: string | null;
  graph: { entities?: number; relations?: number; truncated?: boolean } | null;
  graph_error?: string | null;
}

interface RagDoc {
  id?: string;
  file_path?: string;
  status?: string;
  created_at?: string;
  updated_at?: string;
  chunks_count?: number;
  content_length?: number;
  error_msg?: string;
}

interface DocsResponse {
  documents?: RagDoc[];
  pagination?: { page: number; page_size: number; total_count: number; total_pages: number };
  status_counts?: Record<string, number>;
  error?: string;
}

const PAGE_SIZE = 20;

/** 数字展示：不传/未知时给一个占位符，别显示 NaN。 */
function num(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : value.toLocaleString();
}

function StatTile({ label, value, hint, tone }: {
  label: string; value: string; hint?: string; tone?: "danger" | "success";
}) {
  return (
    <div className="rounded-lg border bg-card px-3 py-2.5">
      <div className="text-[11px] leading-4 text-muted-foreground">{label}</div>
      <div className={cn("mt-0.5 text-xl font-semibold tabular-nums",
                         tone === "danger" && "text-destructive",
                         tone === "success" && "text-success")}>
        {value}
      </div>
      {hint && <div className="text-[11px] leading-4 text-muted-foreground">{hint}</div>}
    </div>
  );
}

function InfoRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline gap-3 text-xs">
      <span className="w-20 shrink-0 text-muted-foreground">{label}</span>
      <span className="min-w-0 break-all">{children}</span>
    </div>
  );
}

function RagPageInner() {
  // 选哪个库放在 URL 上：刷新/分享链接不会跳回默认库（多项目环境里这很要紧）
  const [kbKey, setKbKey] = useQueryState("kb", parseAsString.withDefault(""));
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("");
  const [busy, setBusy] = useState(false);

  const kbs = useSWR("/rag/kbs", () =>
    apiClient.get<KbInfo[]>("/rag/kbs").then((r) => r.data), { refreshInterval: 20000 });

  const list = kbs.data ?? [];
  const current = list.find((k) => k.key === kbKey) ?? list[0];
  const key = current?.key ?? "";
  const reachable = current?.reachable ?? false;

  const overview = useSWR(key ? `${key}/overview` : null, () =>
    apiClient.get<RagOverview>("/rag/overview", { kb: key }).then((r) => r.data),
  { refreshInterval: 30000 });

  const docs = useSWR(key ? `${key}/documents/${page}/${statusFilter}` : null, () =>
    apiClient.get<DocsResponse>("/rag/documents", {
      kb: key, page: String(page), page_size: String(PAGE_SIZE),
      ...(statusFilter ? { status: statusFilter } : {}),
    }).then((r) => r.data), { refreshInterval: 30000 });

  const ov = overview.data;
  const health = ov?.health;
  const counts = ov?.status_counts ?? {};
  const docList = docs.data?.documents ?? [];
  const total = docs.data?.pagination?.total_count ?? 0;

  // 检索测试
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState("hybrid");
  const [querying, setQuerying] = useState(false);
  const [answer, setAnswer] = useState("");

  const serviceAction = async (action: "start" | "restart" | "stop") => {
    if (!key) return;
    setBusy(true);
    try {
      await apiClient.post(`/rag/service/${key}/${action}`, {});
      toast.success(action === "stop"
        ? `已停止「${current?.label}」`
        : `已下发${action === "start" ? "启动" : "重启"}，约 10-30 秒就绪`);
      setTimeout(() => { kbs.mutate(); overview.mutate(); }, 6000);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "操作失败（本机模式才有启动器）");
    } finally {
      setBusy(false);
    }
  };

  const runQuery = async () => {
    if (!question.trim() || !key) return;
    setQuerying(true);
    setAnswer("");
    try {
      const res = await apiClient.post<{ response?: string }>("/rag/query",
        { question, mode, top_k: 6, kb: key });
      setAnswer(res.data?.response ?? JSON.stringify(res.data, null, 2));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "检索失败");
    } finally {
      setQuerying(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-6xl px-6 py-8 lg:px-8">
        <div className="flex flex-col gap-5">
          <PageHeader
            title="知识库（LightRAG）"
            description="本页只做展示与检索验证。入库、删除文档、重新解析、图谱可视化与实体/关系编辑，都在 LightRAG 自带界面里做——每个知识库的地址在下方「服务」卡里。"
            actions={
              <div className="flex items-center gap-2">
                {current && (reachable ? (
                  <span className="flex items-center gap-1 text-xs text-success">
                    <CheckCircle2 className="h-3.5 w-3.5" />服务在线
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-xs text-destructive">
                    <XCircle className="h-3.5 w-3.5" />未启动 / 不可达
                  </span>
                ))}
                <Button size="sm" variant="outline"
                        onClick={() => { kbs.mutate(); overview.mutate(); docs.mutate(); }}>
                  <RefreshCw className="mr-1 h-3.5 w-3.5" />刷新
                </Button>
              </div>
            }
          />

          {/* 选库：一个知识库 = 一个独立实例（独立端口 + 独立 workspace），
              数据互不可见。清单在 LightRAG 界面的「RAG 设置」页里维护。 */}
          <div className="flex flex-wrap items-center gap-2">
            {list.map((kb) => {
              const active = kb.key === key;
              return (
                <button
                  key={kb.key}
                  onClick={() => { setKbKey(kb.key); setPage(1); setAnswer(""); }}
                  className={cn(
                    "flex items-center gap-2 rounded-lg border px-3 py-1.5 text-left text-xs transition-colors",
                    active ? "border-primary bg-primary/5" : "hover:bg-muted/60",
                  )}
                >
                  <span className={cn("h-1.5 w-1.5 rounded-full",
                                      kb.reachable ? "bg-success" : "bg-muted-foreground/40")} />
                  <span className="font-medium">{kb.label}</span>
                  <span className="text-muted-foreground">:{kb.port}</span>
                  {kb.documents !== null && kb.documents !== undefined && (
                    <span className="text-muted-foreground">{kb.documents} 篇</span>
                  )}
                </button>
              );
            })}
            {list.length <= 1 && (
              <span className="text-xs text-muted-foreground">
                只有一个知识库。多个项目要分开时，在 LightRAG 界面的「RAG 设置」页里新增。
              </span>
            )}
          </div>

          {/* 服务控制 + 本体入口 */}
          {current && (
            <Card className="p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="text-sm font-semibold">{current.label}</h3>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {current.description ||
                      "知识库本体：图谱 + 向量检索。一个库一个实例，数据与其它库互不可见。"}
                  </p>
                  <dl className="mt-2 flex flex-col gap-1">
                    <InfoRow label="界面">
                      <code className="select-all rounded bg-muted px-1.5 py-0.5 font-mono">
                        {current.webui_url}
                      </code>
                      <span className="ml-2 text-muted-foreground">（入库 / 删文档 / 重解析 / 图谱）</span>
                    </InfoRow>
                    <InfoRow label="RAG 设置">
                      <code className="select-all rounded bg-muted px-1.5 py-0.5 font-mono">
                        {current.settings_url}
                      </code>
                      <span className="ml-2 text-muted-foreground">（模型 / Embedding / 知识库清单）</span>
                    </InfoRow>
                    <InfoRow label="API">
                      <code className="select-all rounded bg-muted px-1.5 py-0.5 font-mono">
                        {current.base_url}
                      </code>
                    </InfoRow>
                  </dl>
                </div>
                <div className="flex shrink-0 flex-wrap items-center gap-2">
                  <a
                    href={current.webui_url}
                    target="_blank"
                    rel="noreferrer"
                    className={cn(buttonVariants({ variant: "outline", size: "sm" }),
                                  "no-underline", !reachable && "pointer-events-none opacity-50")}
                    aria-disabled={!reachable}
                  >
                    <ExternalLink className="mr-1 h-3.5 w-3.5" />LightRAG 界面
                  </a>
                  <a
                    href={current.settings_url}
                    target="_blank"
                    rel="noreferrer"
                    className={cn(buttonVariants({ variant: "outline", size: "sm" }),
                                  "no-underline", !reachable && "pointer-events-none opacity-50")}
                    aria-disabled={!reachable}
                  >
                    <Settings2 className="mr-1 h-3.5 w-3.5" />RAG 设置
                  </a>
                  {reachable ? (
                    <>
                      <Button size="sm" variant="outline" disabled={busy}
                              onClick={() => serviceAction("restart")}>
                        {busy ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                              : <RotateCcw className="mr-1 h-3.5 w-3.5" />}重启
                      </Button>
                      <Button size="sm" variant="outline" disabled={busy}
                              onClick={() => serviceAction("stop")}>
                        <Square className="mr-1 h-3.5 w-3.5" />停止
                      </Button>
                    </>
                  ) : (
                    <Button size="sm" disabled={busy} onClick={() => serviceAction("start")}>
                      {busy ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                            : <Play className="mr-1 h-3.5 w-3.5" />}启动服务
                    </Button>
                  )}
                </div>
              </div>
              {!reachable && (
                <p className="mt-2 rounded bg-destructive/5 p-2 text-xs text-destructive">
                  {current.error || "服务不可达"}
                </p>
              )}
            </Card>
          )}

          {/* 概览：文档 / 图谱 / 管道 */}
          {reachable && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
              <StatTile label="已入库文档" value={num(counts.all)} />
              <StatTile label="已处理" value={num(counts.processed)} tone="success" />
              <StatTile label="处理失败" value={num(counts.failed)}
                        tone={(counts.failed ?? 0) > 0 ? "danger" : undefined}
                        hint={(counts.failed ?? 0) > 0 ? "去 LightRAG 界面重跑" : undefined} />
              <StatTile label="待处理" value={num((counts.pending ?? 0) + (counts.processing ?? 0))}
                        hint="管道忙时会自己往下走" />
              <StatTile
                label="图谱规模"
                value={num(ov?.graph?.entities)}
                hint={ov?.graph
                  ? `${num(ov.graph.relations)} 条关系${ov.graph.truncated ? "（取样，非全量）" : ""}`
                  : (ov?.graph_error ? "取不到图谱数据" : "—")}
              />
            </div>
          )}

          {/* 服务详情 */}
          {reachable && health && (
            <Card className="p-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold">服务详情</h3>
                {ov?.pipeline && (
                  <span className="text-xs text-muted-foreground">
                    管道：
                    {ov.pipeline.busy
                      ? `运行中（${ov.pipeline.job_name || "任务"}，${ov.pipeline.docs ?? 0} 篇）`
                      : "空闲"}
                    {ov.pipeline.recovery_required ? " · 需要恢复（去 LightRAG 界面处理）" : ""}
                  </span>
                )}
              </div>
              <Separator className="my-3" />
              <div className="grid grid-cols-1 gap-x-6 gap-y-2 md:grid-cols-2">
                <InfoRow label="版本">
                  {health.core_version || "—"}
                  <span className="ml-2 text-muted-foreground">api {health.api_version || "—"}</span>
                </InfoRow>
                <InfoRow label="工作区">
                  <code className="rounded bg-muted px-1.5 py-0.5 font-mono">
                    {health.workspace || "(全局)"}
                  </code>
                  <span className="ml-2 text-muted-foreground">
                    数据目录 {current?.data_dir}
                  </span>
                </InfoRow>
                <InfoRow label="LLM">{health.llm_model || "—"}
                  <span className="ml-2 text-muted-foreground">
                    {health.llm_upstream
                      ? `经控制台代转 → ${health.llm_upstream}`
                      : health.llm_binding_host || ""}
                  </span>
                </InfoRow>
                <InfoRow label="Embedding">{health.embedding_model || "—"}
                  <span className="ml-2 text-muted-foreground">{health.embedding_binding_host || ""}</span>
                </InfoRow>
                <InfoRow label="存储">
                  {[health.kv_storage, health.graph_storage, health.vector_storage]
                    .filter(Boolean).join(" / ") || "—"}
                </InfoRow>
                <InfoRow label="工作目录">
                  <span className="font-mono text-[11px]">{health.working_directory || "—"}</span>
                </InfoRow>
              </div>
            </Card>
          )}

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            {/* 检索测试 */}
            <Card className="p-4">
              <h3 className="text-sm font-semibold">检索测试</h3>
              <p className="mt-1 text-xs text-muted-foreground">
                在「{current?.label ?? "—"}」里检索，验证资料真的能查到。
              </p>
              <div className="mt-3 flex flex-col gap-2">
                <Input
                  placeholder="例如：帮派玩法有哪些测试关注点？"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && runQuery()}
                />
                <div className="flex items-center gap-2">
                  <Select value={mode} onValueChange={(v) => setMode(v ?? "hybrid")}>
                    <SelectTrigger className="w-[220px]">
                      <SelectValue placeholder="检索模式" />
                    </SelectTrigger>
                    <SelectContent>
                      {QUERY_MODES.map((m) => (
                        <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Button size="sm" onClick={runQuery}
                          disabled={querying || !question.trim() || !reachable}>
                    {querying ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                              : <Search className="mr-1 h-3.5 w-3.5" />}
                    检索
                  </Button>
                </div>
                {answer && (
                  <div className="mt-2 max-h-72 overflow-y-auto whitespace-pre-wrap rounded bg-muted p-3 text-sm leading-relaxed">
                    {answer}
                  </div>
                )}
              </div>
            </Card>

            {/* 文档列表 */}
            <Card className="p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-sm font-semibold">已入库文档</h3>
                <div className="flex items-center gap-2">
                  <Select value={statusFilter || "all"}
                          onValueChange={(v) => { setStatusFilter(v === "all" ? "" : (v ?? "")); setPage(1); }}>
                    <SelectTrigger className="h-8 w-[120px] text-xs">
                      <SelectValue placeholder="全部状态" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">全部状态</SelectItem>
                      {DOC_STATUSES.map((s) => (
                        <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Button size="sm" variant="outline" onClick={() => docs.mutate()}>
                    <RefreshCw className="mr-1 h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
              <Separator className="my-3" />
              {docs.isLoading ? (
                <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
                  加载中…
                </div>
              ) : !reachable ? (
                <EmptyState title="服务未启动" description="启动后这里显示已入库的文档与解析状态" />
              ) : docs.data?.error ? (
                <EmptyState title="取不到文档列表" description={docs.data.error} />
              ) : docList.length === 0 ? (
                <EmptyState
                  title={statusFilter ? "该状态下没有文档" : "还没有入库的文档"}
                  description="在 LightRAG 界面里上传/粘贴资料，或让智能体用知识库工具入库"
                />
              ) : (
                <>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>文档</TableHead>
                        <TableHead className="w-24">状态</TableHead>
                        <TableHead className="w-16 text-right">分块</TableHead>
                        <TableHead className="w-40">更新时间</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {docList.map((d, i) => (
                        <TableRow key={d.id ?? i}>
                          <TableCell className="max-w-72 truncate" title={d.error_msg || d.file_path}>
                            {d.file_path ?? d.id}
                          </TableCell>
                          <TableCell>
                            <StatusBadge status={d.status} fallbackLabel="—" />
                          </TableCell>
                          <TableCell className="text-right text-xs tabular-nums text-muted-foreground">
                            {d.chunks_count ?? "—"}
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {(d.updated_at ?? d.created_at ?? "—").replace("T", " ").slice(0, 19)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                  <Pagination page={page} pageSize={PAGE_SIZE} total={total}
                              onPageChange={setPage} className="mt-3" />
                </>
              )}
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}

// useQueryState（nuqs 底层是 useSearchParams）在静态预渲染时必须包 Suspense，
// 否则 next build 在 /rag 直接失败（平台平时跑 next dev 不触发，一跑 build 就炸）。
export default function RagPage() {
  return (
    <React.Suspense fallback={null}>
      <RagPageInner />
    </React.Suspense>
  );
}
