"use client";

/**
 * 评测集列表（页面上的增删改入口）。
 *
 * 起因：评测集原本只能手写 `datasets/*.yaml`，缩进/块标量/字段名全靠记，
 * 写错一个缩进要等跑批次才发现。这里把列表与编辑搬到页面上——文件仍是唯一
 * 事实源（保存即写盘、下拉立刻可选），列表里同时显示每个集子能拉起哪条推荐门禁。
 */

import React, { useState } from "react";
import {
  useEvalDatasets, deleteEvalDataset, type EvalDatasetInfo, type EvalDatasetDetail,
} from "@/lib/api/useNewModules";
import { apiClient } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import { Copy, Loader2, Pencil, Plus, Sparkles, Trash2 } from "lucide-react";
import { DatasetEditor } from "./DatasetEditor";
import { AiDatasetDialog } from "./AiDatasetDialog";
import type { EvalGenerateResult } from "@/lib/api/useNewModules";

export function DatasetManager() {
  const datasets = useEvalDatasets();
  const [editing, setEditing] = useState<{
    file: string | null;
    seed?: EvalDatasetDetail | null;
    seedFileName?: string;
  } | null>(null);
  const [aiOpen, setAiOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<EvalDatasetInfo | null>(null);
  const [busy, setBusy] = useState(false);

  const rows = datasets.data ?? [];

  const copyFrom = async (row: EvalDatasetInfo) => {
    try {
      const response = await apiClient.get<EvalDatasetDetail>(
        `/eval/datasets/${encodeURIComponent(row.file)}`);
      setEditing({ file: null, seed: response.data });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "读取失败");
    }
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setBusy(true);
    try {
      await deleteEvalDataset(pendingDelete.file);
      toast.success(`已删除 ${pendingDelete.file}`);
      setPendingDelete(null);
      datasets.mutate();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "删除失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="p-0">
      <div className="flex items-center justify-between border-b px-4 py-2.5">
        <span className="flex items-center gap-1.5 text-sm font-medium">
          <Copy className="h-4 w-4" />评测集（datasets/*.yaml）
        </span>
        <div className="flex items-center gap-1">
          <Button size="sm" variant="ghost" onClick={() => datasets.mutate()}>刷新</Button>
          <Button size="sm" variant="outline" onClick={() => setAiOpen(true)}>
            <Sparkles className="mr-1 h-3.5 w-3.5" />AI 生成测评集
          </Button>
          <Button size="sm" variant="outline" onClick={() => setEditing({ file: null })}>
            <Plus className="mr-1 h-3.5 w-3.5" />新建评测集
          </Button>
        </div>
      </div>

      {datasets.isLoading ? (
        <div className="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />加载中…
        </div>
      ) : rows.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground">
          还没有评测集。点右上角「新建评测集」写第一条用例——填完保存就能直接起批次。
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>名称</TableHead><TableHead>文件</TableHead>
              <TableHead>用例</TableHead><TableHead>裁判</TableHead>
              <TableHead>推荐门禁</TableHead>
              <TableHead className="text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.file}>
                <TableCell className="font-medium">
                  {row.error
                    ? <span className="flex items-center gap-1.5">
                        {row.file}
                        <Badge variant="destructive" className="font-normal">解析失败</Badge>
                      </span>
                    : (row.name ?? row.file)}
                </TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">{row.file}</TableCell>
                <TableCell className="text-muted-foreground">
                  {row.error ? "-" : `${row.items ?? 0} 条`}
                </TableCell>
                <TableCell>
                  {row.error ? <span className="text-xs text-destructive">{row.error.slice(0, 40)}…</span>
                    : row.has_judge
                      ? <Badge variant="secondary" className="font-normal">有</Badge>
                      : <span className="text-xs text-muted-foreground">无</span>}
                </TableCell>
                <TableCell className="max-w-[320px]">
                  <span className="block truncate font-mono text-[11px] text-muted-foreground"
                        title={row.gate_hint ?? ""}>
                    {row.gate_hint ?? "-"}
                  </span>
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex items-center justify-end gap-1">
                    <Button size="sm" variant="ghost" onClick={() => setEditing({ file: row.file })}
                            aria-label={`编辑 ${row.file}`}>
                      <Pencil className="mr-1 h-3.5 w-3.5" />编辑
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => copyFrom(row)}
                            aria-label={`复制 ${row.file}`}>
                      <Copy className="h-3.5 w-3.5" />
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setPendingDelete(row)}
                            aria-label={`删除 ${row.file}`}>
                      <Trash2 className="h-3.5 w-3.5 text-destructive" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <p className="border-t px-4 py-2 text-[11px] text-muted-foreground">
        保存即写回 <code className="font-mono">datasets/</code> 下的 YAML 文件（同一个文件也可以直接手改，
        页面会读回）。改动立刻对「启动测评」的评测集下拉生效，不需要重建镜像。
      </p>

      {editing && (
        <DatasetEditor
          file={editing.file}
          seed={editing.seed}
          seedFileName={editing.seedFileName}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); datasets.mutate(); }}
        />
      )}

      {aiOpen && (
        <AiDatasetDialog
          onClose={() => setAiOpen(false)}
          onGenerated={(result: EvalGenerateResult) => {
            setAiOpen(false);
            // 草稿进编辑器：人微调后才保存（生成质量不必一次到位，可编辑是关键）
            setEditing({
              file: null,
              seed: { ...result.dataset, raw: "", gate_hint: null } as EvalDatasetDetail,
              seedFileName: result.dataset.file,
            });
          }}
        />
      )}

      <AlertDialog open={pendingDelete !== null}
                   onOpenChange={(open) => !open && setPendingDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除「{pendingDelete?.file}」？</AlertDialogTitle>
            <AlertDialogDescription>
              会把这个评测集文件从 datasets/ 目录删除，且不可恢复。已经跑过的批次记录不受影响
              （它们保存的是执行结论，不依赖这个文件）。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>取消</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete} disabled={busy}>删除</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}

export type { EvalDatasetInfo };
