"use client";

import { useState, useCallback } from "react";
import { ManagementLayout } from "@/app/components/ManagementLayout";
import { PassRateChart } from "./components/PassRateChart";
import { RunStatusChart } from "./components/RunStatusChart";
import { RunList } from "./components/RunList";
import { RunDetailDialog } from "./components/RunDetailDialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Plus, ChevronLeft, ChevronRight } from "lucide-react";
import { useProjects } from "@/lib/api/useProjects";
import { useTestCases } from "@/lib/api/useTestCases";
import { useTestRuns, useCreateTestRun, useDeleteTestRun } from "@/lib/api/useTestRuns";
import type { TestRunInfo, TestRunCreate } from "@/app/types/api";

export default function RunsPage() {
  // Project selector state
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const { data: projectsData } = useProjects(1, 100);
  const projects = projectsData?.data ?? [];

  // Pagination
  const [page, setPage] = useState(1);
  const pageSize = 30;

  // Test runs data
  const { data: runsData, isLoading, error } = useTestRuns(page, pageSize, selectedProjectId ?? undefined);
  const runs = runsData?.data ?? [];
  const info = runsData?.info;

  // Mutations
  const { trigger: createRun, isMutating: isCreating } = useCreateTestRun();
  const { trigger: deleteRun, isMutating: isDeleting } = useDeleteTestRun();

  // Dialog states
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [detailDialogOpen, setDetailDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [selectedRun, setSelectedRun] = useState<TestRunInfo | null>(null);

  // Create form state
  const [createFormProjectId, setCreateFormProjectId] = useState<string>("");
  const [createName, setCreateName] = useState("");
  const [createDescription, setCreateDescription] = useState("");
  const [selectedCaseIds, setSelectedCaseIds] = useState<string[]>([]);

  // Fetch test cases for the selected project in create form
  const { data: casesData } = useTestCases(1, 100, createFormProjectId || undefined);
  const availableCases = casesData?.data ?? [];

  // Reset page when project changes
  const handleProjectChange = (val: string | null) => {
    setSelectedProjectId(val);
    setPage(1);
  };

  // Handlers
  const handleViewDetail = useCallback((run: TestRunInfo) => {
    setSelectedRun(run);
    setDetailDialogOpen(true);
  }, []);

  const handleDelete = useCallback((run: TestRunInfo) => {
    setSelectedRun(run);
    setDeleteDialogOpen(true);
  }, []);

  const handleConfirmDelete = useCallback(async () => {
    if (selectedRun) {
      await deleteRun(selectedRun.id);
      setDeleteDialogOpen(false);
      setSelectedRun(null);
    }
  }, [selectedRun, deleteRun]);

  const handleOpenCreate = useCallback(() => {
    setCreateName("");
    setCreateDescription("");
    setCreateFormProjectId(selectedProjectId || "");
    setSelectedCaseIds([]);
    setCreateDialogOpen(true);
  }, [selectedProjectId]);

  const handleCreateSubmit = useCallback(async () => {
    if (!createFormProjectId || !createName.trim()) return;
    const data: TestRunCreate = {
      project_id: createFormProjectId,
      name: createName.trim(),
      description: createDescription || undefined,
      test_case_ids: selectedCaseIds.length > 0 ? selectedCaseIds : undefined,
    };
    await createRun(data);
    setCreateDialogOpen(false);
  }, [createFormProjectId, createName, createDescription, selectedCaseIds, createRun]);

  const toggleCaseSelection = useCallback((caseId: string) => {
    setSelectedCaseIds((prev) =>
      prev.includes(caseId) ? prev.filter((id) => id !== caseId) : [...prev, caseId]
    );
  }, []);

  return (
    <ManagementLayout>
      <div className="space-y-6">
        {/* Header section */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <h2 className="text-2xl font-bold">测试执行仪表盘</h2>
            <Select value={selectedProjectId ?? ""} onValueChange={handleProjectChange}>
              <SelectTrigger>
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
          </div>
          <Button
            onClick={handleOpenCreate}
            disabled={isCreating}
          >
            <Plus className="mr-2 h-4 w-4" />
            新建测试执行
          </Button>
        </div>

        {/* Charts section */}
        <div className="grid grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <CardTitle>通过率分布</CardTitle>
            </CardHeader>
            <CardContent>
              <PassRateChart runs={runs} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>状态分布</CardTitle>
            </CardHeader>
            <CardContent>
              <RunStatusChart runs={runs} />
            </CardContent>
          </Card>
        </div>

        {/* Run list section */}
        <Card>
          <CardHeader>
            <CardTitle>执行历史</CardTitle>
          </CardHeader>
          <CardContent>
            {error ? (
              <div className="py-8 text-center">
                <p className="text-destructive">加载失败</p>
                <Button variant="outline" className="mt-2" onClick={() => window.location.reload()}>
                  重试
                </Button>
              </div>
            ) : (
              <>
                <RunList
                  runs={runs}
                  onViewDetail={handleViewDetail}
                  onDelete={handleDelete}
                  isLoading={isLoading}
                />

                {/* Pagination */}
                {info && info.total > 0 && (
                  <div className="flex items-center justify-between mt-4">
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
          </CardContent>
        </Card>
      </div>

      {/* Create test run dialog */}
      <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
        <DialogContent className="sm:max-w-[600px] max-h-[80vh] overflow-auto">
          <DialogHeader>
            <DialogTitle>新建测试执行</DialogTitle>
            <DialogDescription>
              创建一个新的测试执行，选择项目和要包含的测试用例。
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label>所属项目</Label>
              <Select value={createFormProjectId} onValueChange={(val) => { if (val) { setCreateFormProjectId(val); setSelectedCaseIds([]); } }}>
                <SelectTrigger className="w-full">
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
            </div>

            <div className="grid gap-2">
              <Label htmlFor="runName">执行名称</Label>
              <Input
                id="runName"
                placeholder="请输入执行名称"
                value={createName}
                onChange={(e) => setCreateName(e.target.value)}
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="runDescription">描述</Label>
              <Textarea
                id="runDescription"
                placeholder="可选描述"
                value={createDescription}
                onChange={(e) => setCreateDescription(e.target.value)}
              />
            </div>

            {/* Test case selector */}
            {createFormProjectId && availableCases.length > 0 && (
              <div className="grid gap-2">
                <Label>选择测试用例</Label>
                <div className="max-h-[200px] overflow-auto rounded-md border p-2 space-y-1">
                  {availableCases.map((tc) => (
                    <label
                      key={tc.id}
                      className="flex items-center gap-2 rounded px-2 py-1 hover:bg-accent cursor-pointer text-sm"
                    >
                      <input
                        type="checkbox"
                        checked={selectedCaseIds.includes(tc.id)}
                        onChange={() => toggleCaseSelection(tc.id)}
                        className="rounded border-gray-300"
                      />
                      <span className="font-mono text-xs text-muted-foreground">{tc.identifier}</span>
                      <span>{tc.name}</span>
                    </label>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground">
                  已选择 {selectedCaseIds.length} / {availableCases.length} 个用例
                </p>
              </div>
            )}

            {createFormProjectId && availableCases.length === 0 && (
              <div className="text-sm text-muted-foreground py-2">
                该项目暂无测试用例，创建后将生成空执行。
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateDialogOpen(false)}>
              取消
            </Button>
            <Button
              onClick={handleCreateSubmit}
              disabled={!createFormProjectId || !createName.trim() || isCreating}
            >
              创建
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Run detail dialog */}
      <RunDetailDialog
        open={detailDialogOpen}
        onOpenChange={setDetailDialogOpen}
        run={selectedRun}
      />

      {/* Delete confirmation */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除</AlertDialogTitle>
            <AlertDialogDescription>
              确定要删除测试执行 &quot;{selectedRun?.name}&quot; 吗？此操作不可撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleConfirmDelete} disabled={isDeleting}>
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </ManagementLayout>
  );
}
