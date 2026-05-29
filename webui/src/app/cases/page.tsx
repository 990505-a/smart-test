"use client";

import { useState, useCallback, useMemo } from "react";
import { ManagementLayout } from "@/app/components/ManagementLayout";
import { DataTable } from "@/app/components/DataTable";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Plus, ChevronLeft, ChevronRight, FileSpreadsheet, FileText, Loader2 } from "lucide-react";
import { useProjects } from "@/lib/api/useProjects";
import { useFolderTree } from "@/lib/api/useFolders";
import { useTestCases, useCreateTestCase, useDeleteTestCase } from "@/lib/api/useTestCases";
import { createCaseColumns } from "./components/CaseColumns";
import { CreateCaseDialog } from "./components/CreateCaseDialog";
import type { TestCaseInfo, TestCaseCreate } from "@/app/types/api";
import { apiClient } from "@/lib/api-client";
import { getConfig } from "@/lib/config";

export default function CasesPage() {
  // Project selector state
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const { data: projectsData } = useProjects(1, 100);
  const projects = projectsData?.data ?? [];

  // Folder filter
  const [selectedFolderId, setSelectedFolderId] = useState<string | null>(null);
  const { data: folderTreeResponse } = useFolderTree(selectedProjectId);
  const folderTree = folderTreeResponse?.data ?? [];

  // Pagination
  const [page, setPage] = useState(1);
  const pageSize = 30;

  // Test case data
  const { data: casesData, isLoading, error } = useTestCases(page, pageSize, selectedProjectId ?? undefined, selectedFolderId ?? undefined);
  const testCases = casesData?.data ?? [];
  const info = casesData?.info;

  // Mutations
  const { trigger: createCase, isMutating: isCreating } = useCreateTestCase();
  const { trigger: deleteCase, isMutating: isDeleting } = useDeleteTestCase();

  // Dialog states
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [selectedCase, setSelectedCase] = useState<TestCaseInfo | null>(null);

  const handleCreateCase = useCallback(
    async (data: TestCaseCreate) => {
      await createCase(data);
    },
    [createCase]
  );

  const handleDeleteCase = useCallback(async () => {
    if (selectedCase) {
      await deleteCase(selectedCase.id);
      setDeleteDialogOpen(false);
      setSelectedCase(null);
    }
  }, [selectedCase, deleteCase]);

  const handleEdit = useCallback((testCase: TestCaseInfo) => {
    // Navigate to edit page via Link in column definition
    window.location.href = `/cases/${testCase.id}`;
  }, []);

  const handleDelete = useCallback((testCase: TestCaseInfo) => {
    setSelectedCase(testCase);
    setDeleteDialogOpen(true);
  }, []);

  const columns = useMemo(
    () => createCaseColumns(handleEdit, handleDelete),
    [handleEdit, handleDelete]
  );

  // Reset page when project/folder changes
  const handleProjectChange = (val: string | null) => {
    setSelectedProjectId(val);
    setSelectedFolderId(null);
    setPage(1);
  };

  const [exporting, setExporting] = useState(false);

  // Export: fetch all cases page by page, then generate file
  const handleExport = useCallback(async (format: "markdown" | "excel") => {
    if (!selectedProjectId) return;
    setExporting(true);
    try {
      const pageSize = 300;
      let page = 1;
      let allCases: TestCaseInfo[] = [];
      // eslint-disable-next-line no-constant-condition
      while (true) {
        const res = await apiClient.getPaginated<TestCaseInfo>("/test-cases", {
          p: page, page_size: pageSize, project_id: selectedProjectId,
          ...(selectedFolderId ? { folder_id: selectedFolderId } : {}),
        });
        allCases = allCases.concat(res.data);
        if (!res.info?.next || res.data.length < pageSize) break;
        page++;
      }
      if (allCases.length === 0) { alert("没有可导出的用例"); return; }

      if (format === "markdown") {
        // Call AI organize endpoint first
        const config = getConfig();
        const apiBase = config?.fastapiUrl || "http://localhost:8000";
        const casesPayload = allCases.map(c => ({
          name: c.name,
          steps: (c.steps ?? []).map(s => ({ action: s.action, expected_result: s.expected_result })),
          preconditions: c.preconditions,
          priority: c.priority,
        }));

        const organizeRes = await fetch(`${apiBase}/api/v2/test-cases/organize`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ cases: casesPayload }),
        });

        if (!organizeRes.ok) throw new Error("AI整理失败");
        const { organized } = await organizeRes.json();

        const md = exportOrganizedAsMarkdown(organized);
        downloadFile(md, `test-cases-${Date.now()}.md`, "text/markdown");
      } else {
        const csv = exportAsCSV(allCases);
        downloadFile(csv, `test-cases-${Date.now()}.csv`, "text/csv");
      }
    } catch (e) {
      console.error("Export failed:", e);
      alert("导出失败");
    } finally {
      setExporting(false);
    }
  }, [selectedProjectId, selectedFolderId]);

  return (
    <ManagementLayout>
      <div className="space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <h2 className="text-2xl font-bold">测试用例</h2>
            <Select value={selectedProjectId ?? null} onValueChange={handleProjectChange}>
              <SelectTrigger className="w-[200px]">
                <SelectValue placeholder="选择项目" />
              </SelectTrigger>
              <SelectContent>
                {projects.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {selectedProjectId && (
              <Select value={selectedFolderId ?? "all"} onValueChange={(val) => { setSelectedFolderId(val === "all" ? null : val); setPage(1); }}>
                <SelectTrigger className="w-[180px]">
                  <SelectValue placeholder="所有文件夹" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">所有文件夹</SelectItem>
                  {flattenForSelect(folderTree).map((f) => (
                    <SelectItem key={f.id} value={f.id}>
                      {"  ".repeat(f.depth)} {f.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => handleExport("markdown")}
              disabled={!selectedProjectId || exporting}
            >
              {exporting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FileText className="mr-2 h-4 w-4" />}
              {exporting ? "AI整理中..." : "导出 Markdown"}
            </Button>
            <Button
              variant="outline"
              onClick={() => handleExport("excel")}
              disabled={!selectedProjectId || exporting}
            >
              <FileSpreadsheet className="mr-2 h-4 w-4" />
              导出 Excel
            </Button>
            <Button
              onClick={() => setCreateDialogOpen(true)}
              disabled={!selectedProjectId || isCreating}
            >
              <Plus className="mr-2 h-4 w-4" />
              新建用例
            </Button>
          </div>
        </div>

        {/* Table content */}
        {!selectedProjectId ? (
          <div className="py-8 text-center text-muted-foreground">
            请先选择一个项目
          </div>
        ) : isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : error ? (
          <div className="py-8 text-center">
            <p className="text-destructive">加载失败</p>
            <Button variant="outline" className="mt-2" onClick={() => window.location.reload()}>
              重试
            </Button>
          </div>
        ) : testCases.length === 0 ? (
          <div className="py-8 text-center text-muted-foreground">
            暂无用例，点击新建用例按钮创建
          </div>
        ) : (
          <>
            <DataTable columns={columns} data={testCases} />

            {/* Pagination */}
            {info && (
              <div className="flex items-center justify-between">
                <p className="text-sm text-muted-foreground">
                  共 {info.total} 条，第 {info.page} / {Math.ceil(info.total / info.page_size)} 页
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!info.prev}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                  >
                    <ChevronLeft className="mr-1 h-4 w-4" />
                    上一页
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!info.next}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    下一页
                    <ChevronRight className="ml-1 h-4 w-4" />
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Create dialog */}
      <CreateCaseDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
        onSubmit={handleCreateCase}
        projectId={selectedProjectId ?? ""}
        folders={folderTree}
      />

      {/* Delete confirmation */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除</AlertDialogTitle>
            <AlertDialogDescription>
              确定要删除用例 &quot;{selectedCase?.name}&quot; 吗？此操作不可撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteCase} disabled={isDeleting}>
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </ManagementLayout>
  );
}

/** Helper to flatten folder tree for select dropdown */
function flattenForSelect(nodes: Array<{ id: string; name: string; children?: Array<{ id: string; name: string; children?: unknown[] }> }>, depth = 0): Array<{ id: string; name: string; depth: number }> {
  const result: Array<{ id: string; name: string; depth: number }> = [];
  for (const node of nodes) {
    result.push({ id: node.id, name: node.name, depth });
    if (node.children?.length) {
      result.push(...flattenForSelect(node.children as Array<{ id: string; name: string; children?: Array<{ id: string; name: string; children?: unknown[] }> }>, depth + 1));
    }
  }
  return result;
}

// --- Export helpers ---

const HEADERS = ["用例编号", "用例标题", "所属模块", "用例类型", "优先级", "前置条件", "测试步骤", "预期结果", "备注"];

function getRow(c: TestCaseInfo): string[] {
  const steps = (c.steps ?? []).map((s, i) => `${i + 1}. ${s.action ?? ""}`).join("\n");
  const expected = (c.steps ?? []).map((s, i) => `${i + 1}. ${s.expected_result ?? ""}`).join("\n");
  return [
    c.identifier,
    c.name,
    c.feature ?? "",
    c.test_case_type ?? "",
    c.priority,
    c.preconditions ?? "",
    steps,
    expected,
    c.description ?? "",
  ];
}

/** Extract module name from description like "模块: xxx | 类型: yyy" */
function extractModule(desc: string | null): string {
  if (!desc) return "未分类";
  const m = desc.match(/模块[：:]\s*(.+?)(?:\s*[|｜]|$)/);
  return m ? m[1].trim() : "未分类";
}

/** Strip TC-M72-XXX-NNN： prefix from case name */
function stripPrefix(name: string): string {
  return name.replace(/^TC-[A-Z0-9]+-[A-Z0-9]+-\d+[：:]\s*/, "")
    .replace(/^TC-[A-Z0-9]+-\d+[：:]\s*/, "");
}

/** Indent helper: N levels of 4 spaces */
function pad(n: number): string {
  return "    ".repeat(n);
}

function exportAsMarkdown(cases: TestCaseInfo[]): string {
  const lines: string[] = ["# 测试用例\n"];

  // Group by module extracted from description
  const groups = new Map<string, TestCaseInfo[]>();
  for (const c of cases) {
    const mod = extractModule(c.description);
    if (!groups.has(mod)) groups.set(mod, []);
    groups.get(mod)!.push(c);
  }

  for (const [mod, groupCases] of groups) {
    lines.push(`- ${mod}`);
    for (const c of groupCases) {
      const title = stripPrefix(c.name);
      lines.push(`${pad(1)}- ${title}`);

      // Operation steps — each step on its own line
      const steps = (c.steps ?? []).filter(s => s.action?.trim());
      if (steps.length > 0) {
        lines.push(`${pad(2)}- 操作步骤：`);
        steps.forEach((s, i) => {
          lines.push(`${pad(3)}- ${s.action!.replace(/\n/g, `；`)}`);
        });
      }

      // Expected result — each step's result on its own line
      const expected = (c.steps ?? []).filter(s => s.expected_result?.trim());
      if (expected.length > 0) {
        lines.push(`${pad(2)}- 预期结果：`);
        expected.forEach(s => {
          const items = s.expected_result!.split(/\n/).filter(l => l.trim());
          items.forEach(item => {
            lines.push(`${pad(3)}- ${item}`);
          });
        });
      }

      // Test data (preconditions) — each line separate
      if (c.preconditions?.trim()) {
        lines.push(`${pad(2)}- 测试数据：`);
        c.preconditions.split(/\n/).filter(l => l.trim()).forEach(item => {
          lines.push(`${pad(3)}- ${item.trim()}`);
        });
      }

      // Priority & Status
      const pMap: Record<string, string> = { critical: "P0-严重", high: "P1-高", medium: "P2-中", low: "P3-低" };
      lines.push(`${pad(2)}- 优先级：${pMap[c.priority] ?? c.priority} | 状态：⏳`);
      lines.push("");
    }
  }

  lines.push(`\n> 共 ${cases.length} 条用例`);
  return lines.join("\n");
}

/** Export AI-organized hierarchical structure as Markdown */
function exportOrganizedAsMarkdown(organized: Array<{
  module: string;
  sub_modules: Array<{
    name: string;
    cases: Array<{
      title: string;
      steps: string;
      expected: string;
      data: string;
      priority: string;
    }>;
  }>;
}>): string {
  const lines: string[] = ["# 测试用例\n"];
  let totalCases = 0;

  for (let mi = 0; mi < organized.length; mi++) {
    const mod = organized[mi];
    lines.push(`${mi + 1}. ${mod.module}`);

    for (let si = 0; si < mod.sub_modules.length; si++) {
      const sub = mod.sub_modules[si];
      lines.push(`${pad(1)}${mi + 1}.${si + 1} ${sub.name}`);

      for (let ci = 0; ci < sub.cases.length; ci++) {
        const c = sub.cases[ci];
        totalCases++;
        lines.push(`${pad(2)}${mi + 1}.${si + 1}.${ci + 1} ${c.title}`);
        lines.push(`${pad(3)}操作步骤：${c.steps}`);
        lines.push(`${pad(3)}预期结果：${c.expected}`);
        lines.push(`${pad(3)}测试数据：${c.data}`);
        lines.push(`${pad(3)}状态：⏳`);
        lines.push("");
      }
    }
  }

  lines.push(`> 共 ${totalCases} 条用例`);
  return lines.join("\n");
}

function exportAsCSV(cases: TestCaseInfo[]): string {
  const rows = [HEADERS];
  for (const c of cases) {
    rows.push(getRow(c));
  }
  const csv = rows.map(r => r.map(v => `"${v.replace(/"/g, '""')}"`).join(",")).join("\n");
  return "﻿" + csv; // UTF-8 BOM for Excel
}

function downloadFile(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: `${mimeType};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
