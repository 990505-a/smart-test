"use client";

import React, { useState } from "react";
import { PageHeader, EmptyState } from "@/app/components/ui-patterns";
import { apiClient } from "@/lib/api-client";
import useSWR from "swr";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { toast } from "sonner";
import { Plug, RefreshCw, Loader2, CheckCircle2, XCircle } from "lucide-react";

interface McpServer {
  name: string;
  transport: string;
  endpoint: string;
  purpose: string;
}

interface CheckResult {
  name: string;
  ok: boolean;
  tool_count: number;
  tools: string[];
  error: string | null;
  endpoint?: string;
}

function ServerCard({ server, onChecked }: {
  server: McpServer; onChecked: (r: CheckResult) => void;
}) {
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState<CheckResult | null>(null);

  const check = async () => {
    setChecking(true);
    try {
      const res = await apiClient.get<CheckResult>(`/mcp/servers/${server.name}/check`);
      setResult(res.data);
      onChecked(res.data);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "检测失败");
    } finally {
      setChecking(false);
    }
  };

  return (
    <Card className="p-4">
      <div className="flex items-center gap-2">
        <Plug className="h-4 w-4 text-muted-foreground" />
        <span className="font-medium">{server.name}</span>
        <Badge variant="outline">{server.transport}</Badge>
        <div className="ml-auto flex items-center gap-2">
          {checking ? (
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />检测中…
            </span>
          ) : result ? (
            result.ok ? (
              <span className="flex items-center gap-1 text-xs text-success">
                <CheckCircle2 className="h-3.5 w-3.5" />可用 · {result.tool_count} 个工具
              </span>
            ) : (
              <span className="flex items-center gap-1 text-xs text-destructive">
                <XCircle className="h-3.5 w-3.5" />不可用
              </span>
            )
          ) : null}
          <Button size="sm" variant="outline" onClick={check} disabled={checking}>
            <RefreshCw className="mr-1 h-3.5 w-3.5" />检测
          </Button>
        </div>
      </div>
      <div className="mt-2 text-xs text-muted-foreground">{server.purpose}</div>
      <div className="mt-1 truncate font-mono text-xs text-muted-foreground" title={server.endpoint}>
        {server.endpoint}
      </div>
      {result && !result.ok && result.error && (
        <div className="mt-2 rounded-lg border border-destructive/30 bg-destructive/5 p-2 text-xs text-destructive">
          {result.error}
        </div>
      )}
      {result && result.ok && result.tools.length > 0 && (
        <div className="mt-2 flex max-h-28 flex-wrap gap-1 overflow-y-auto">
          {result.tools.map((t) => (
            <Badge key={t} variant="secondary" className="font-mono text-[10px]">{t}</Badge>
          ))}
        </div>
      )}
    </Card>
  );
}

export default function McpPage() {
  const { data, isLoading } = useSWR("/mcp/servers", () =>
    apiClient.get<McpServer[]>("/mcp/servers").then((r) => r.data));

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-6xl px-6 py-8 lg:px-8">
        <div className="flex flex-col gap-5">
          <PageHeader
            title="MCP 服务"
            description="平台的 MCP 服务器是智能体的工具基础设施（用例生成 / 代码分析等智能体按需连接）。在这里检测各服务连通性并查看其提供的工具清单。"
          />
          {isLoading ? (
            <div className="flex flex-1 items-center justify-center py-16 text-sm text-muted-foreground">
              加载中…
            </div>
          ) : (data ?? []).length === 0 ? (
            <EmptyState
              title="暂无 MCP 服务"
              description="后端未注册任何 MCP 服务器；启动相关服务后刷新查看"
            />
          ) : (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              {(data ?? []).map((s) => (
                <ServerCard key={s.name} server={s} onChecked={() => {}} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
