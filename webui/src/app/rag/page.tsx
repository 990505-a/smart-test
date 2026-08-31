"use client";

import React, { useRef, useState } from "react";
import { PageHeader, StatusBadge, EmptyState } from "@/app/components/ui-patterns";
import { apiClient, getApiBaseUrl } from "@/lib/api-client";
import { getToken } from "@/lib/auth";
import useSWR from "swr";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { toast } from "sonner";
import { RefreshCw, Loader2, CheckCircle2, XCircle, Upload, ExternalLink, Search } from "lucide-react";

const QUERY_MODES = [
  { value: "hybrid", label: "hybrid（图谱混合，推荐）" },
  { value: "local", label: "local（实体邻域）" },
  { value: "global", label: "global（主题全局）" },
  { value: "naive", label: "naive（纯向量）" },
  { value: "mix", label: "mix（图谱+向量）" },
];

interface RagStatus {
  reachable: boolean;
  health: Record<string, unknown>;
  base_url: string;
  webui_url: string;
}

interface RagDoc {
  id?: string;
  file_path?: string;
  status?: string;
  created_at?: string;
  chunks?: number;
}

export default function RagPage() {
  const status = useSWR("/rag/status", () =>
    apiClient.get<RagStatus>("/rag/status").then((r) => r.data), { refreshInterval: 15000 });
  const docs = useSWR("/rag/documents", () =>
    apiClient.get<{ documents?: RagDoc[]; total_count?: number }>("/rag/documents", { page: "1", page_size: "20" })
      .then((r) => r.data), { refreshInterval: 30000 });

  const st = status.data;

  // 检索测试
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState("hybrid");
  const [querying, setQuerying] = useState(false);
  const [answer, setAnswer] = useState<string>("");

  const runQuery = async () => {
    if (!question.trim()) return;
    setQuerying(true);
    setAnswer("");
    try {
      const res = await apiClient.post<{ response?: string; data?: { response?: string } }>(
        "/rag/query", { question, mode, top_k: 6 });
      setAnswer(res.data?.response ?? res.data?.data?.response ?? JSON.stringify(res.data, null, 2));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "检索失败");
    } finally {
      setQuerying(false);
    }
  };

  // 文本入库
  const [ingestText, setIngestText] = useState("");
  const [ingesting, setIngesting] = useState(false);
  const doIngestText = async () => {
    if (!ingestText.trim()) return;
    setIngesting(true);
    try {
      await apiClient.post("/rag/ingest-text", { text: ingestText });
      toast.success("已入库，正在后台构建索引");
      setIngestText("");
      docs.mutate();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "入库失败");
    } finally {
      setIngesting(false);
    }
  };

  // 文件上传
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const upload = async (file: File) => {
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${getApiBaseUrl()}/api/v2/rag/ingest-file`, {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken()}` },
        body: form,
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.detail || "上传失败");
      toast.success("上传成功，正在解析入库");
      docs.mutate();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "上传失败");
    } finally {
      setUploading(false);
    }
  };

  const docList = docs.data?.documents ?? [];

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-6xl px-6 py-8 lg:px-8">
        <div className="flex flex-col gap-5">
          <PageHeader
            title="知识库（LightRAG）"
            description="RAG 本体管理：需求文档 / 历史用例 / 项目知识的入库与检索。服务本体由启动器（:9000）启动。"
            actions={
              st && (
                <div className="flex items-center gap-2">
                  {st.reachable ? (
                    <span className="flex items-center gap-1 text-xs text-success">
                      <CheckCircle2 className="h-3.5 w-3.5" />服务在线
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-xs text-destructive">
                      <XCircle className="h-3.5 w-3.5" />未启动 / 不可达
                    </span>
                  )}
                  <Button size="sm" variant="outline" onClick={() => status.mutate()}>
                    <RefreshCw className="mr-1 h-3.5 w-3.5" />刷新
                  </Button>
                </div>
              )
            }
          />

          {!st?.reachable && st && (
            <Card className="border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
              LightRAG 服务（{st.base_url}）不可达。请打开启动器 http://localhost:5010 启动
              「LightRAG 知识库」；首次使用需在设置页配置 Embedding API Key。
            </Card>
          )}

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            {/* 检索测试 */}
            <Card className="p-4">
              <h3 className="text-sm font-semibold">检索测试</h3>
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
                  <Button size="sm" onClick={runQuery} disabled={querying || !question.trim()}>
                    {querying ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <Search className="mr-1 h-3.5 w-3.5" />}
                    检索
                  </Button>
                  {st?.webui_url && (
                    <a href={st.webui_url} target="_blank" rel="noreferrer"
                       className="ml-auto flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
                      <ExternalLink className="h-3 w-3" />图谱可视化
                    </a>
                  )}
                </div>
                {answer && (
                  <div className="mt-2 max-h-64 overflow-y-auto whitespace-pre-wrap rounded bg-muted p-3 text-sm leading-relaxed">
                    {answer}
                  </div>
                )}
              </div>
            </Card>

            {/* 入库 */}
            <Card className="p-4">
              <h3 className="text-sm font-semibold">文档入库</h3>
              <div className="mt-3 flex flex-col gap-2">
                <Label htmlFor="rag-text">粘贴文本（需求 / 用例 / 经验）</Label>
                <Textarea
                  id="rag-text"
                  className="min-h-24"
                  placeholder="粘贴 Markdown 或纯文本…"
                  value={ingestText}
                  onChange={(e) => setIngestText(e.target.value)}
                />
                <div className="flex items-center gap-2">
                  <Button size="sm" onClick={doIngestText} disabled={ingesting || !ingestText.trim()}>
                    {ingesting && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
                    文本入库
                  </Button>
                  <input
                    ref={fileRef} type="file" hidden
                    accept=".txt,.md,.pdf,.docx,.json,.csv"
                    onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
                  />
                  <Button size="sm" variant="outline" onClick={() => fileRef.current?.click()} disabled={uploading}>
                    {uploading ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <Upload className="mr-1 h-3.5 w-3.5" />}
                    上传文件
                  </Button>
                </div>
              </div>
            </Card>
          </div>

          {/* 文档列表 */}
          <Card className="p-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold">已入库文档</h3>
              <Button size="sm" variant="outline" onClick={() => docs.mutate()}>
                <RefreshCw className="mr-1 h-3.5 w-3.5" />刷新
              </Button>
            </div>
            <Separator className="my-3" />
            {docs.isLoading ? (
              <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
                加载中…
              </div>
            ) : docList.length === 0 ? (
              <EmptyState
                title="暂无文档"
                description="服务未启动或尚未入库；可在上方粘贴文本或上传文件入库"
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>文档</TableHead>
                    <TableHead>状态</TableHead>
                    <TableHead>创建时间</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {docList.map((d, i) => (
                    <TableRow key={d.id ?? i}>
                      <TableCell className="max-w-96 truncate" title={d.file_path}>
                        {d.file_path ?? d.id}
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={d.status} fallbackLabel="—" />
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">{d.created_at ?? "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
