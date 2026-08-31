"use client";

/**
 * 代码图谱页 — 主从布局(master-detail):
 * 左侧仓库列表(状态点 + 点选切换) + 右侧选中仓库的功能区。
 * - 图谱:选中已建库仓库即自动加载,工具条(搜索/上限/结构节点/边过滤)内聚
 * - 索引与规则:该仓库的索引动作、文件类型规则、实际 .cbmignore、运行历史
 * - 定时任务(全局):间隔配置 + 立即执行 + 全部历史
 */

import React, { useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/app/components/ui-patterns";
import { apiClient } from "@/lib/api-client";
import {
  useCbmRepos, useCbmRuns, useCbmSchedule, useCbmStatus,
  fetchCbmGraphData, fetchCbmIgnore, fetchCbmSubgraph, type CbmGraphData, type CbmRepo,
} from "@/lib/api/useNewModules";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "sonner";
import GraphView, { NODE_PALETTE, type GraphNodeInfo } from "@/app/components/GraphView";
import {
  CheckCircle2, Database, FileCode2, Loader2, Play, Plus, RefreshCw,
  Timer, Trash2, XCircle,
} from "lucide-react";

const COMMON_EXTS = [".gs", ".lua", ".cs", ".py", ".go", ".ts", ".java", ".cpp"];

const EDGE_LEGEND: Record<string, string> = {
  CALLS: "#94a3b8",
  DEFINES: "#a78bfa",
  CONTAINS_FILE: "#cbd5e1",
  IMPORTS: "#34d399",
  USAGE: "#fbbf24",
  INHERITS: "#f472b6",
};

export default function CodebasePage() {
  const repos = useCbmRepos(8000);
  const runs = useCbmRuns(50);
  const repoList = useMemo(() => repos.data?.repos ?? [], [repos.data]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [addOpen, setAddOpen] = useState(false);

  const selected = repoList.find((r) => r.id === selectedId) ?? null;
  const progress = runs.data?.progress ?? null;
  const indexingRepo = runs.data?.indexing ?? null;

  // 默认选中第一个仓库
  useEffect(() => {
    if (!selectedId && repoList.length > 0) setSelectedId(repoList[0].id);
  }, [repoList, selectedId]);

  return (
    <div className="flex-1 overflow-hidden">
      <div className="mx-auto flex h-full w-full max-w-[1600px] flex-col px-6 py-6 lg:px-8">
        <PageHeader
          title="代码图谱"
          description="多仓库代码知识图谱:索引管理、文件类型控制、节点连线可视化、定时增量索引。"
        />
        <div className="mt-4 flex min-h-0 flex-1 gap-4">
          {/* ============ 左侧:仓库列表 ============ */}
          <aside className="flex w-72 shrink-0 flex-col gap-3">
            <Card className="flex min-h-0 flex-1 flex-col p-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold">仓库</span>
                <Button size="sm" variant="ghost" onClick={() => setAddOpen(true)}
                        title="添加仓库"><Plus className="h-4 w-4" /></Button>
              </div>
              <Separator className="my-2" />
              <div className="min-h-0 flex-1 space-y-1 overflow-y-auto">
                {repoList.map((repo) => {
                  const isSel = repo.id === selectedId;
                  const isIndexing = indexingRepo === repo.repo_path;
                  return (
                    <button key={repo.id} type="button" onClick={() => setSelectedId(repo.id)}
                            className={`w-full rounded-lg border px-2.5 py-2 text-left transition
                              ${isSel ? "border-primary/50 bg-muted/70" : "border-transparent hover:bg-muted/40"}`}>
                      <div className="flex items-center gap-2">
                        {isIndexing ? (
                          <Loader2 className="h-3 w-3 shrink-0 animate-spin text-warning" />
                        ) : repo.indexed ? (
                          <CheckCircle2 className="h-3 w-3 shrink-0 text-success" />
                        ) : (
                          <XCircle className="h-3 w-3 shrink-0 text-muted-foreground" />
                        )}
                        <span className="min-w-0 flex-1 truncate text-sm">
                          {repo.display_name || repo.repo_path}
                        </span>
                        {repo.auto_increment && (
                          <span title="参与定时增量"><Timer className="h-3 w-3 shrink-0 text-muted-foreground" /></span>
                        )}
                      </div>
                      <div className="mt-0.5 flex items-center gap-1.5 pl-5 text-[11px] text-muted-foreground">
                        {repo.indexed ? `${repo.nodes ?? "?"} 节点 · ${repo.edges ?? "?"} 边` : "未建库"}
                        <RuleChip repo={repo} />
                      </div>
                    </button>
                  );
                })}
                {repoList.length === 0 && (
                  <div className="rounded-lg border border-dashed p-4 text-center text-xs text-muted-foreground">
                    还没有仓库
                    <Button size="sm" variant="outline" className="mt-2 w-full"
                            onClick={() => setAddOpen(true)}>
                      <Plus className="mr-1 h-3.5 w-3.5" />添加第一个仓库
                    </Button>
                  </div>
                )}
              </div>
            </Card>
            <ServiceFooter />
          </aside>

          {/* ============ 右侧:功能区 ============ */}
          <main className="min-w-0 flex-1">
            <Tabs defaultValue="graph" className="flex h-full flex-col">
              <TabsList className="shrink-0">
                <TabsTrigger value="graph"><Database className="mr-1 h-3.5 w-3.5" />图谱</TabsTrigger>
                <TabsTrigger value="manage"><FileCode2 className="mr-1 h-3.5 w-3.5" />索引与规则</TabsTrigger>
                <TabsTrigger value="schedule"><Timer className="mr-1 h-3.5 w-3.5" />定时任务</TabsTrigger>
              </TabsList>
              <div className="mt-3 min-h-0 flex-1 overflow-y-auto pr-1">
                <TabsContent value="graph" className="mt-0">
                  <GraphTab repo={selected} indexing={!!indexingRepo} />
                </TabsContent>
                <TabsContent value="manage" className="mt-0">
                  <ManageTab repo={selected} progress={progress}
                             indexing={!!indexingRepo} onChanged={() => repos.mutate()} />
                </TabsContent>
                <TabsContent value="schedule" className="mt-0">
                  <ScheduleTab progress={progress} />
                </TabsContent>
              </div>
            </Tabs>
          </main>
        </div>
        <AddRepoDialog open={addOpen} onOpenChange={setAddOpen}
                       onAdded={(id) => { setSelectedId(id); repos.mutate(); }} />
      </div>
    </div>
  );
}

// ===========================================================================
// 左侧部件
// ===========================================================================

function ServiceFooter() {
  const status = useCbmStatus();
  const st = status.data;
  return (
    <Card className="shrink-0 space-y-1 p-3 text-xs">
      <div className="flex items-center justify-between">
        <span className="text-muted-foreground">索引服务</span>
        {st?.available
          ? <span className="flex items-center gap-1 text-success"><CheckCircle2 className="h-3 w-3" />可用</span>
          : <span className="flex items-center gap-1 text-destructive"><XCircle className="h-3 w-3" />不可用</span>}
      </div>
      <div className="flex items-center justify-between">
        <span className="text-muted-foreground">图数据服务</span>
        <span className={st?.graph_daemon?.up ? "text-success" : "text-muted-foreground"}>
          {st?.graph_daemon?.up ? "运行中" : "自动拉起"}
        </span>
      </div>
      <div className="flex items-center justify-between">
        <span className="text-muted-foreground">已建库项目</span>
        <span>{st?.projects?.length ?? 0}</span>
      </div>
    </Card>
  );
}

function AddRepoDialog({ open, onOpenChange, onAdded }: {
  open: boolean; onOpenChange: (v: boolean) => void; onAdded: (id: string) => void;
}) {
  const [path, setPath] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (!path.trim() || busy) return;
    setBusy(true);
    try {
      const res = await apiClient.post<{ success: boolean; error?: string; repo?: { id: string } }>(
        "/codebase/repos", { repo_path: path.trim(), display_name: name.trim() || null });
      if (res.data?.success === false) {
        toast.error(res.data.error ?? "添加失败");
      } else {
        toast.success("仓库已添加,去「索引与规则」建立图谱");
        onAdded(res.data?.repo?.id ?? "");
        setPath(""); setName("");
        onOpenChange(false);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "添加失败");
    } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[440px]">
        <DialogHeader><DialogTitle>添加仓库</DialogTitle></DialogHeader>
        <div className="grid gap-3 py-1">
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">仓库绝对路径</Label>
            <Input className="font-mono text-xs" placeholder="如 E:/m72-publish/m72"
                   value={path} onChange={(e) => setPath(e.target.value)}
                   onKeyDown={(e) => e.key === "Enter" && submit()} />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">别名（可选）</Label>
            <Input className="text-xs" placeholder="如 游戏服务端"
                   value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <Button size="sm" onClick={submit} disabled={busy || !path.trim()}>
            {busy && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}添加
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function RuleChip({ repo }: { repo: CbmRepo }) {
  if (repo.file_type_mode === "all") return null;
  return (
    <span className="truncate rounded bg-muted px-1 font-mono text-[10px]"
          title={repo.file_type_mode === "include" ? "仅索引" : "排除"}>
      {repo.file_type_mode === "include" ? "仅" : "除"} {repo.file_types.join(" ")}
    </span>
  );
}

// ===========================================================================
// Tab: 图谱(小图自动全量,大图走范围视图)
// ===========================================================================

/** 超过该节点数的大图不再全量采样(/api/layout 随机采样会得到无边的孤点),改用范围视图 */
const BIG_GRAPH_THRESHOLD = 30000;

function GraphTab({ repo, indexing }: { repo: CbmRepo | null; indexing: boolean }) {
  const [maxNodes, setMaxNodes] = useState(2000);
  const [data, setData] = useState<CbmGraphData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<GraphNodeInfo | null>(null);
  const [search, setSearch] = useState("");
  const [edgeFilter, setEdgeFilter] = useState<Set<string>>(new Set());
  const [showStructural, setShowStructural] = useState(false);
  // 范围视图状态(大图)
  const [scopeMode, setScopeMode] = useState<"dir" | "symbol">("dir");
  const [scopeValue, setScopeValue] = useState("");
  const project = repo?.project ?? "";
  const isBig = (repo?.nodes ?? 0) > BIG_GRAPH_THRESHOLD;
  const loadKey = `${project}:${maxNodes}`;

  const applyResult = (res: unknown) => {
    if (res && Array.isArray((res as CbmGraphData).nodes)) {
      setData(res as CbmGraphData);
      setEdgeFilter(new Set());
      setSelected(null);
    } else {
      setError(String((res as { error?: string })?.error ?? "图数据为空或格式异常"));
    }
  };

  // 小图:选中已建库仓库 → 自动全量加载
  useEffect(() => {
    if (isBig || !project || !repo?.indexed) return;
    let cancelled = false;
    setLoading(true); setError("");
    fetchCbmGraphData(project, maxNodes)
      .then((res) => { if (!cancelled) applyResult(res); })
      .catch((err) => { if (!cancelled) setError(err instanceof Error ? err.message : "加载失败"); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadKey, repo?.indexed, isBig]);

  const reload = async () => {
    if (!project || loading) return;
    setLoading(true); setError("");
    try {
      applyResult(await fetchCbmGraphData(project, maxNodes));
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally { setLoading(false); }
  };

  const loadScope = async () => {
    if (!project || !scopeValue.trim() || loading) return;
    setLoading(true); setError(""); setSelected(null);
    try {
      applyResult(await fetchCbmSubgraph(project, scopeMode, scopeValue.trim()));
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally { setLoading(false); }
  };

  const presentTypes = useMemo(() => {
    const set = new Set<string>();
    data?.edges.forEach((e) => set.add(e.type));
    return [...set].sort();
  }, [data]);

  const presentLabels = useMemo(() => {
    const set = new Set<string>();
    data?.nodes.forEach((n) => set.add(n.label));
    return [...set].sort();
  }, [data]);

  const toggleEdge = (type: string) => {
    setEdgeFilter((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type); else next.add(type);
      return next;
    });
  };

  if (!repo) {
    return <EmptyHint text="左侧选择或添加一个仓库后,这里展示它的代码图谱。" />;
  }
  if (!repo.indexed) {
    return <EmptyHint text={`「${repo.display_name || repo.repo_path}」还没有建库:去「索引与规则」点一次全量索引,再来这里看图。`} />;
  }

  return (
    <div className="space-y-3">
      {/* 工具条:小图一行常规控制;大图一行范围视图控制 */}
      <Card className="flex flex-row flex-wrap items-center gap-x-4 gap-y-2 p-2.5">
        <span className="max-w-52 truncate text-sm font-medium" title={repo.repo_path}>
          {repo.display_name || repo.repo_path}
        </span>
        <Badge variant="secondary">
          {data ? `${data.nodes.length} 节点 · ${data.edges.length} 边` : `${repo.nodes} 节点`}
        </Badge>
        {isBig ? (
          <>
            <div className="flex min-w-72 items-center gap-1.5">
              <Select value={scopeMode} onValueChange={(v) => setScopeMode(v as "dir" | "symbol")}>
                <SelectTrigger className="h-7 w-24 text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="dir">目录范围</SelectItem>
                  <SelectItem value="symbol">符号邻域</SelectItem>
                </SelectContent>
              </Select>
              <Input className="h-7 font-mono text-xs"
                     placeholder={scopeMode === "dir"
                       ? "目录前缀,如 server/pkg(留空=仓库根,取前200节点)"
                       : "精确符号名,如 create / start(展示直接上下游)"}
                     value={scopeValue}
                     onChange={(e) => setScopeValue(e.target.value)}
                     onKeyDown={(e) => e.key === "Enter" && loadScope()} />
            </div>
            <Button size="sm" className="h-7" onClick={loadScope} disabled={loading}>
              {loading ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <Play className="mr-1 h-3.5 w-3.5" />}
              加载范围
            </Button>
            <span className="text-[11px] text-muted-foreground">
              大图({repo.nodes} 节点)按范围查看更有意义
            </span>
          </>
        ) : (
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            上限
            <Select value={String(maxNodes)} onValueChange={(v) => setMaxNodes(Number(v))}>
              <SelectTrigger className="h-7 w-20 text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                {[1000, 2000, 5000].map((n) => <SelectItem key={n} value={String(n)}>{n}</SelectItem>)}
              </SelectContent>
            </Select>
          </label>
        )}
        <div className="flex min-w-40 items-center gap-1.5">
          <RefreshCw className="h-3.5 w-3.5 text-muted-foreground" />
          <Input className="h-7 text-xs" placeholder="搜索符号/文件,实时高亮"
                 value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Switch checked={showStructural} onCheckedChange={setShowStructural} />
          结构节点
        </label>
        {!isBig && (
          <Button size="sm" variant="outline" className="ml-auto h-7" onClick={reload} disabled={loading}>
            {loading ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="mr-1 h-3.5 w-3.5" />}
            刷新
          </Button>
        )}
      </Card>

      {error && (
        <Card className="border-destructive/30 bg-destructive/5 p-3 text-xs text-destructive">{error}</Card>
      )}

      {/* 图例 + 过滤(一行) */}
      {data && (
        <Card className="flex flex-row flex-wrap items-center gap-x-3 gap-y-1.5 p-2.5 text-[11px]">
          <span className="text-xs text-muted-foreground">节点</span>
          {presentLabels.map((label) => (
            <span key={label} className="flex items-center gap-1">
              <span className="inline-block h-2.5 w-2.5 rounded-full"
                    style={{ background: NODE_PALETTE[label] ?? "#64748b" }} />
              {label}
            </span>
          ))}
          <Separator className="mx-1 h-4" orientation="vertical" />
          <span className="text-xs text-muted-foreground">连线</span>
          {presentTypes.map((type) => {
            const active = edgeFilter.size === 0 || edgeFilter.has(type);
            return (
              <button key={type} type="button" onClick={() => toggleEdge(type)}
                      className={`flex items-center gap-1 rounded border px-1.5 py-0.5 transition
                        ${active ? "border-border bg-muted/60" : "opacity-40"}`}
                      title={active ? "点击隐藏此类边" : "点击显示此类边"}>
                <svg width="16" height="4">
                  <line x1="0" y1="2" x2="16" y2="2" stroke={EDGE_LEGEND[type] ?? "#94a3b8"} strokeWidth="2" />
                </svg>
                {type}
              </button>
            );
          })}
          <span className="ml-auto text-muted-foreground">滚轮缩放 · 拖拽平移 · 悬停看邻居 · 点击看详情</span>
        </Card>
      )}

      <div className={selected ? "grid grid-cols-1 gap-3 xl:grid-cols-4" : ""}>
        <div className={selected ? "xl:col-span-3" : ""}>
          {indexing && (
            <div className="mb-2 flex items-center gap-2 text-xs text-warning">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />正在索引,完成后点「刷新」可看最新图
            </div>
          )}
          <GraphView data={data} edgeFilter={edgeFilter} search={search}
                     showStructural={showStructural} onNodeClick={setSelected} />
        </div>
        {selected && (
          <Card className="h-fit p-4 text-sm">
            <div className="mb-2 flex items-center justify-between">
              <span className="font-medium">{selected.name}</span>
              <button className="text-xs text-muted-foreground hover:text-destructive"
                      onClick={() => setSelected(null)}>关闭</button>
            </div>
            <Separator className="my-2" />
            <dl className="space-y-1.5 text-xs">
              <div className="flex gap-2"><dt className="w-16 shrink-0 text-muted-foreground">类型</dt>
                <dd className="flex items-center gap-1.5">
                  <span className="inline-block h-2.5 w-2.5 rounded-full"
                        style={{ background: NODE_PALETTE[selected.label] ?? "#64748b" }} />
                  {selected.label}{selected.status ? ` · ${selected.status}` : ""}
                </dd></div>
              {selected.qualified_name && (
                <div className="flex gap-2"><dt className="w-16 shrink-0 text-muted-foreground">全名</dt>
                  <dd className="min-w-0 break-all font-mono">{selected.qualified_name}</dd></div>
              )}
              {selected.file_path && (
                <div className="flex gap-2"><dt className="w-16 shrink-0 text-muted-foreground">文件</dt>
                  <dd className="min-w-0 break-all font-mono">
                    {selected.file_path}
                    {selected.start_line ? `:${selected.start_line}-${selected.end_line ?? ""}` : ""}
                  </dd></div>
              )}
              <div className="flex gap-2"><dt className="w-16 shrink-0 text-muted-foreground">入度</dt>
                <dd>{selected.in_calls ?? 0}</dd></div>
            </dl>
          </Card>
        )}
      </div>
    </div>
  );
}

function EmptyHint({ text }: { text: string }) {
  return (
    <Card className="p-8 text-center text-sm text-muted-foreground">{text}</Card>
  );
}

// ===========================================================================
// Tab: 索引与规则(选中仓库)
// ===========================================================================

function ManageTab({ repo, progress, indexing, onChanged }: {
  repo: CbmRepo | null;
  progress: { phase: string; last_line: string; elapsed_s: number; live: boolean } | null;
  indexing: boolean; onChanged: () => void;
}) {
  const runs = useCbmRuns(30);
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<string | null>(null);
  const [exts, setExts] = useState<string | null>(null);
  const [autoInc, setAutoInc] = useState<boolean | null>(null);
  const [showIgnore, setShowIgnore] = useState(false);
  const [ignoreContent, setIgnoreContent] = useState<string | null>(null);

  if (!repo) return <EmptyHint text="左侧选择或添加一个仓库后,在这里管理索引和文件类型规则。" />;

  const effMode = mode ?? repo.file_type_mode;
  const effExts = exts ?? repo.file_types.join(" ");
  const effAuto = autoInc ?? repo.auto_increment;
  const dirty = effMode !== repo.file_type_mode
    || effExts !== repo.file_types.join(" ") || effAuto !== repo.auto_increment;

  const parseExts = () => effExts.split(/[\s,;]+/).map((e) => e.trim().toLowerCase())
    .filter(Boolean).map((e) => (e.startsWith(".") ? e : `.${e}`));

  const save = async () => {
    setBusy(true);
    try {
      const res = await apiClient.patch<{ success: boolean; error?: string }>(
        `/codebase/repos/${repo.id}`,
        { file_type_mode: effMode, file_types: parseExts(), auto_increment: effAuto });
      if (res.data?.success === false) toast.error(res.data.error ?? "保存失败");
      else { toast.success("已保存（规则在下次索引时生效）"); setMode(null); setExts(null); setAutoInc(null); onChanged(); }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "保存失败");
    } finally { setBusy(false); }
  };

  const startIndex = async (indexMode: "fast" | "moderate" | "full") => {
    setBusy(true);
    try {
      const res = await apiClient.post<{ success: boolean; error?: string }>(
        `/codebase/repos/${repo.id}/index`, { mode: indexMode });
      if (res.data?.success === false) toast.error(res.data.error ?? "启动失败");
      else toast.success(`已开始${indexMode === "full" ? "全量" : indexMode === "fast" ? "快速" : "标准"}索引,下方可见实时进度`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "启动失败");
    } finally { setBusy(false); }
  };

  const remove = async () => {
    setBusy(true);
    try {
      await apiClient.delete(`/codebase/repos/${repo.id}`);
      toast.success("已移除（图谱索引保留）");
      onChanged();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "删除失败");
    } finally { setBusy(false); }
  };

  const loadIgnore = async () => {
    if (showIgnore) { setShowIgnore(false); return; }
    try {
      const res = await fetchCbmIgnore(repo.id);
      setIgnoreContent(res.exists && res.content ? res.content : "(.cbmignore 不存在 = 索引全部文件)");
      setShowIgnore(true);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "读取失败");
    }
  };

  const repoRuns = (runs.data?.runs ?? []).filter((r) => r.repo_id === repo.id);

  return (
    <div className="space-y-4">
      {/* 状态 + 索引动作 */}
      <Card className="flex flex-row flex-wrap items-center gap-3 p-4">
        <div className="min-w-0 flex-1">
          <div className="truncate font-mono text-sm" title={repo.repo_path}>
            {repo.display_name || repo.repo_path}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            {repo.indexed
              ? <Badge className="bg-success/15 text-success">已建库 · {repo.nodes} 节点 / {repo.edges} 边</Badge>
              : <Badge variant="outline">未建库</Badge>}
            {repo.last_index_at && (
              <span>上次索引 {new Date(repo.last_index_at).toLocaleString("zh-CN")}（{repo.last_index_mode}）</span>
            )}
          </div>
        </div>
        <div className="flex gap-1.5">
          <Button size="sm" variant="outline" disabled={busy || indexing} onClick={() => startIndex("fast")}>
            快速索引
          </Button>
          <Button size="sm" disabled={busy || indexing} onClick={() => startIndex("full")}>
            <Database className="mr-1 h-3.5 w-3.5" />全量索引
          </Button>
          <Button size="sm" variant="ghost" disabled={busy} onClick={remove} title="移除受管（不删图谱索引）">
            <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
          </Button>
        </div>
      </Card>

      {/* 实时进度(仅本仓库索引中显示) */}
      {indexing && progress && (
        <Card className="p-4">
          <div className="flex items-center gap-2 text-sm text-warning">
            <Loader2 className="h-4 w-4 animate-spin" />
            索引进行中 <span className="text-xs text-muted-foreground">已运行 {progress.elapsed_s}s</span>
          </div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
            <div className="h-full w-1/3 rounded-full bg-warning"
                 style={{ animation: "slide 1.2s ease-in-out infinite alternate" }} />
          </div>
          <div className="mt-2 truncate font-mono text-xs text-muted-foreground" title={progress.last_line}>
            阶段 {progress.phase || "…"} {progress.last_line ? `· ${progress.last_line}` : ""}
          </div>
          <style>{`@keyframes slide { from { transform: translateX(-40%); } to { transform: translateX(260%); } }`}</style>
        </Card>
      )}

      {/* 文件类型规则 */}
      <Card className="p-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold">索引文件类型</h3>
          <span className="text-xs text-muted-foreground">
            当前生效:{effMode === "all" ? "全部类型" : (effMode === "include" ? `仅索引 ${parseExts().join(" ") || "—"}` : `排除 ${parseExts().join(" ") || "—"}`)}
          </span>
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">模式</Label>
            <Select value={effMode} onValueChange={(v) => setMode(v)}>
              <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部类型</SelectItem>
                <SelectItem value="include">仅索引指定类型</SelectItem>
                <SelectItem value="exclude">排除指定类型</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">扩展名（空格分隔）</Label>
            <Input className="h-8 font-mono text-xs" placeholder=".gs .lua .cs"
                   value={effMode === "all" ? "" : effExts}
                   disabled={effMode === "all"}
                   onChange={(e) => setExts(e.target.value)} />
            <div className="flex flex-wrap gap-1">
              {COMMON_EXTS.map((ext) => (
                <button key={ext} type="button"
                        className="rounded border px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground hover:bg-muted"
                        onClick={() => setExts((prev) => ((prev ?? repo.file_types.join(" ")) ? `${prev ?? repo.file_types.join(" ")} ${ext}` : ext))}>
                  {ext}
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="mt-3 flex items-center justify-between">
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <Switch checked={effAuto} onCheckedChange={setAutoInc} />
            参与定时增量索引（仅对已建库仓库生效）
          </label>
          <div className="flex gap-1.5">
            <Button size="sm" variant="ghost" onClick={loadIgnore}>
              {showIgnore ? "收起规则文件" : "查看 .cbmignore"}
            </Button>
            <Button size="sm" disabled={busy || !dirty} onClick={save}>
              {busy && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}保存配置
            </Button>
          </div>
        </div>
        {showIgnore && (
          <pre className="mt-3 max-h-48 overflow-auto whitespace-pre-wrap rounded-lg border bg-muted/50 p-3 font-mono text-xs">
            {ignoreContent ?? "加载中…"}
          </pre>
        )}
      </Card>

      {/* 本仓库运行历史 */}
      <Card className="p-4">
        <h3 className="mb-2 text-sm font-semibold">运行历史</h3>
        <RunsTable runs={repoRuns} />
      </Card>
    </div>
  );
}

// ===========================================================================
// Tab: 定时任务(全局)
// ===========================================================================

function ScheduleTab({ progress }: {
  progress: { phase: string; last_line: string; elapsed_s: number; repo_path: string; live: boolean } | null;
}) {
  const schedule = useCbmSchedule();
  const runs = useCbmRuns(30);
  const [enabled, setEnabled] = useState(false);
  const [hours, setHours] = useState(24);
  const [busy, setBusy] = useState(false);
  const [initialized, setInitialized] = useState(false);

  if (schedule.data && !initialized) {
    setEnabled(schedule.data.enabled);
    setHours(schedule.data.interval_hours);
    setInitialized(true);
  }

  const save = async () => {
    setBusy(true);
    try {
      const res = await apiClient.put<{ success: boolean; error?: string }>(
        "/codebase/schedule", { enabled, interval_hours: hours });
      if (res.data?.success === false) toast.error(res.data.error ?? "保存失败");
      else { toast.success(enabled ? `已开启：每 ${hours} 小时增量索引一轮` : "已关闭定时增量"); schedule.mutate(); }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "保存失败");
    } finally { setBusy(false); }
  };

  const trigger = async () => {
    setBusy(true);
    try {
      await apiClient.post("/codebase/schedule/trigger", {});
      toast.success("已开始一轮增量索引（左侧仓库列表可见转圈,进度见「索引与规则」）");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "触发失败");
    } finally { setBusy(false); }
  };

  const st = schedule.data;
  const dirty = initialized && st && (enabled !== st.enabled || hours !== st.interval_hours);

  return (
    <div className="space-y-4">
      <Card className="p-4">
        <div className="flex flex-wrap items-end gap-4">
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={enabled} onCheckedChange={setEnabled} />
            启用定时增量索引
          </label>
          <div className="w-40 space-y-1">
            <Label className="text-xs text-muted-foreground">间隔（小时）</Label>
            <Input type="number" min={1} max={720} className="h-8 text-xs"
                   value={hours} disabled={!enabled}
                   onChange={(e) => setHours(Number(e.target.value) || 1)} />
          </div>
          <Button size="sm" disabled={busy || !dirty} onClick={save}>保存</Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={trigger}>
            <Play className="mr-1 h-3.5 w-3.5" />立即执行一轮
          </Button>
          <span className="ml-auto text-xs text-muted-foreground">
            {st?.enabled && st.next_run
              ? `下次执行：${new Date(st.next_run).toLocaleString("zh-CN")}`
              : st?.enabled ? "等待调度器计算下次执行时间" : "未启用"}
          </span>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          规则：只对「已建库且开启参与」的仓库做增量索引（内容哈希，仅重解析变更文件）；从未全量索引的仓库自动跳过。
        </p>
      </Card>

      {progress?.live && (
        <Card className="p-3">
          <div className="flex items-center gap-2 text-sm text-warning">
            <Loader2 className="h-4 w-4 animate-spin" />
            正在索引 <span className="font-mono text-xs">{progress.repo_path}</span>
            <span className="text-xs text-muted-foreground">已运行 {progress.elapsed_s}s · 阶段 {progress.phase}</span>
          </div>
        </Card>
      )}

      <Card className="p-4">
        <h3 className="mb-2 text-sm font-semibold">全部运行历史</h3>
        <RunsTable runs={runs.data?.runs ?? []} />
      </Card>
    </div>
  );
}

function RunsTable({ runs }: { runs: import("@/lib/api/useNewModules").CbmIndexRun[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-36">时间</TableHead>
          <TableHead>仓库</TableHead>
          <TableHead className="w-20">触发</TableHead>
          <TableHead className="w-20">模式</TableHead>
          <TableHead className="w-20">状态</TableHead>
          <TableHead>说明</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {runs.map((run) => (
          <TableRow key={run.id}>
            <TableCell className="text-xs">
              {run.started_at ? new Date(run.started_at).toLocaleString("zh-CN") : "—"}
            </TableCell>
            <TableCell className="max-w-56 truncate font-mono text-xs" title={run.repo_path}>
              {run.display_name || run.repo_path}
            </TableCell>
            <TableCell>
              <Badge variant={run.trigger === "scheduled" ? "secondary" : "outline"} className="text-[10px]">
                {run.trigger === "scheduled" ? "定时" : "手动"}
              </Badge>
            </TableCell>
            <TableCell className="text-xs">{run.mode}</TableCell>
            <TableCell><RunStatusBadge status={run.status} /></TableCell>
            <TableCell className="max-w-72 truncate text-xs text-muted-foreground" title={run.error ?? ""}>
              {run.error
                ? run.error
                : (run.detail as { reason?: string; duration_s?: number })?.reason
                  ? `跳过：${(run.detail as { reason?: string }).reason}`
                  : (run.detail as { duration_s?: number })?.duration_s != null
                    ? `耗时 ${(run.detail as { duration_s: number }).duration_s}s` : "—"}
            </TableCell>
          </TableRow>
        ))}
        {runs.length === 0 && (
          <TableRow>
            <TableCell colSpan={6} className="py-6 text-center text-xs text-muted-foreground">
              暂无记录
            </TableCell>
          </TableRow>
        )}
      </TableBody>
    </Table>
  );
}

function RunStatusBadge({ status }: { status: string }) {
  if (status === "success") return <Badge className="bg-success/15 text-[10px] text-success">成功</Badge>;
  if (status === "failed") return <Badge className="bg-destructive/15 text-[10px] text-destructive">失败</Badge>;
  if (status === "running") return <Badge className="bg-warning/15 text-[10px] text-warning">进行中</Badge>;
  return <Badge variant="outline" className="text-[10px] text-muted-foreground">跳过</Badge>;
}
