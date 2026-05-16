"use client";

import { useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
  ArrowLeft,
  Play,
  Plus,
  Trash2,
  GripVertical,
  Save,
  History,
} from "lucide-react";
import {
  useScenario,
  useScenarioRuns,
  useUpdateScenario,
} from "@/lib/api/useScenarios";
import {
  addScenarioStep,
  updateScenarioStep,
  deleteScenarioStep,
  executeScenario,
} from "@/lib/api/useScenarios";
import type { ScenarioInfo, ScenarioStepInfo, ScenarioRunInfo } from "@/app/types/api";

interface ScenarioEditorProps {
  scenario: ScenarioInfo;
  onBack: () => void;
}

export function ScenarioEditor({ scenario, onBack }: ScenarioEditorProps) {
  const [activeTab, setActiveTab] = useState("steps");

  // Refresh scenario data (includes steps)
  const { data: scenarioData, isLoading, mutate } = useScenario(scenario.id);
  const currentScenario = scenarioData?.data ?? scenario;
  const steps: ScenarioStepInfo[] = currentScenario.steps ?? [];

  // Runs
  const { data: runsData } = useScenarioRuns(scenario.id, 20);
  const runs: ScenarioRunInfo[] = (runsData?.data as ScenarioRunInfo[]) ?? [];

  // Update mutation
  const { trigger: updateScenario } = useUpdateScenario();

  // Edit form for scenario name/description
  const [editName, setEditName] = useState(scenario.name);
  const [editDesc, setEditDesc] = useState(scenario.description ?? "");
  const [isSaving, setIsSaving] = useState(false);

  // Step dialog
  const [stepDialogOpen, setStepDialogOpen] = useState(false);
  const [editingStep, setEditingStep] = useState<ScenarioStepInfo | null>(null);
  const [stepName, setStepName] = useState("");
  const [stepDesc, setStepDesc] = useState("");

  // Delete step
  const [deleteStepId, setDeleteStepId] = useState<string | null>(null);

  // Execution
  const [isExecuting, setIsExecuting] = useState(false);

  const handleSaveScenario = useCallback(async () => {
    setIsSaving(true);
    try {
      await updateScenario({
        scenarioId: scenario.id,
        data: { name: editName, description: editDesc },
      });
      mutate();
    } finally {
      setIsSaving(false);
    }
  }, [editName, editDesc, scenario.id, updateScenario, mutate]);

  const handleAddStep = useCallback(async () => {
    if (!stepName.trim()) return;
    await addScenarioStep(scenario.id, {
      name: stepName.trim(),
      description: stepDesc || null,
      step_order: steps.length + 1,
    });
    setStepDialogOpen(false);
    setStepName("");
    setStepDesc("");
    mutate();
  }, [scenario.id, stepName, stepDesc, steps.length, mutate]);

  const handleUpdateStep = useCallback(async () => {
    if (!editingStep || !stepName.trim()) return;
    await updateScenarioStep(scenario.id, editingStep.id, {
      name: stepName.trim(),
      description: stepDesc || null,
    });
    setStepDialogOpen(false);
    setEditingStep(null);
    setStepName("");
    setStepDesc("");
    mutate();
  }, [editingStep, stepName, stepDesc, scenario.id, mutate]);

  const handleDeleteStep = useCallback(async () => {
    if (!deleteStepId) return;
    await deleteScenarioStep(scenario.id, deleteStepId);
    setDeleteStepId(null);
    mutate();
  }, [deleteStepId, scenario.id, mutate]);

  const handleExecute = useCallback(async () => {
    setIsExecuting(true);
    try {
      await executeScenario(scenario.id);
      mutate();
    } finally {
      setIsExecuting(false);
    }
  }, [scenario.id, mutate]);

  const openAddStepDialog = () => {
    setEditingStep(null);
    setStepName("");
    setStepDesc("");
    setStepDialogOpen(true);
  };

  const openEditStepDialog = (step: ScenarioStepInfo) => {
    setEditingStep(step);
    setStepName(step.name);
    setStepDesc(step.description ?? "");
    setStepDialogOpen(true);
  };

  const runStatusBadge = (status: string) => {
    switch (status) {
      case "completed":
        return "bg-green-100 text-green-800";
      case "running":
        return "bg-yellow-100 text-yellow-800";
      case "failed":
        return "bg-red-100 text-red-800";
      default:
        return "bg-gray-100 text-gray-800";
    }
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={onBack}>
            <ArrowLeft className="mr-1 h-4 w-4" />
            返回列表
          </Button>
          <h2 className="text-xl font-semibold">{currentScenario.name}</h2>
          <Badge variant="outline" className="font-mono text-xs">
            {currentScenario.identifier}
          </Badge>
          <Badge>{currentScenario.status}</Badge>
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={handleExecute} disabled={isExecuting}>
            <Play className="mr-2 h-4 w-4" />
            {isExecuting ? "执行中..." : "执行场景"}
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-48 w-full" />
        </div>
      ) : (
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList>
            <TabsTrigger value="steps">步骤管理</TabsTrigger>
            <TabsTrigger value="settings">基本设置</TabsTrigger>
            <TabsTrigger value="runs">
              <History className="mr-1 h-4 w-4" />
              执行历史
            </TabsTrigger>
          </TabsList>

          {/* Steps tab */}
          <TabsContent value="steps" className="mt-4 space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">
                共 {steps.length} 个步骤
              </p>
              <Button size="sm" onClick={openAddStepDialog}>
                <Plus className="mr-2 h-4 w-4" />
                添加步骤
              </Button>
            </div>

            {steps.length === 0 ? (
              <div className="py-8 text-center text-muted-foreground border rounded-md">
                暂无步骤，点击"添加步骤"按钮创建
              </div>
            ) : (
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-10"></TableHead>
                      <TableHead className="w-16">顺序</TableHead>
                      <TableHead>名称</TableHead>
                      <TableHead>描述</TableHead>
                      <TableHead>断言数</TableHead>
                      <TableHead>提取器数</TableHead>
                      <TableHead className="w-24">操作</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {steps.map((step) => (
                      <TableRow key={step.id}>
                        <TableCell className="text-muted-foreground">
                          <GripVertical className="h-4 w-4" />
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline" className="font-mono">
                            {step.step_order}
                          </Badge>
                        </TableCell>
                        <TableCell className="font-medium">
                          {step.name}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground max-w-[200px] truncate">
                          {step.description ?? "-"}
                        </TableCell>
                        <TableCell>
                          <Badge variant="secondary">
                            {Array.isArray(step.assertions) ? step.assertions.length : 0}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <Badge variant="secondary">
                            {Array.isArray(step.extractors) ? step.extractors.length : 0}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => openEditStepDialog(step)}
                            >
                              编辑
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setDeleteStepId(step.id)}
                            >
                              <Trash2 className="h-4 w-4 text-destructive" />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </TabsContent>

          {/* Settings tab */}
          <TabsContent value="settings" className="mt-4">
            <Card>
              <CardHeader>
                <CardTitle>场景设置</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid gap-4 max-w-lg">
                  <div className="grid gap-2">
                    <Label htmlFor="scName">场景名称</Label>
                    <Input
                      id="scName"
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor="scDesc">描述</Label>
                    <Textarea
                      id="scDesc"
                      value={editDesc}
                      onChange={(e) => setEditDesc(e.target.value)}
                      rows={3}
                    />
                  </div>
                  <Button
                    onClick={handleSaveScenario}
                    disabled={isSaving}
                    className="w-fit"
                  >
                    <Save className="mr-2 h-4 w-4" />
                    {isSaving ? "保存中..." : "保存"}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Runs tab */}
          <TabsContent value="runs" className="mt-4">
            <Card>
              <CardHeader>
                <CardTitle>执行历史</CardTitle>
              </CardHeader>
              <CardContent>
                {runs.length === 0 ? (
                  <div className="py-8 text-center text-muted-foreground">
                    暂无执行记录
                  </div>
                ) : (
                  <div className="rounded-md border">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>标识</TableHead>
                          <TableHead>状态</TableHead>
                          <TableHead>通过/失败/跳过</TableHead>
                          <TableHead>耗时</TableHead>
                          <TableHead>执行时间</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {runs.map((run) => (
                          <TableRow key={run.id}>
                            <TableCell className="font-mono text-xs">
                              {run.identifier}
                            </TableCell>
                            <TableCell>
                              <Badge className={runStatusBadge(run.status)}>
                                {run.status}
                              </Badge>
                            </TableCell>
                            <TableCell>
                              <span className="text-green-600">
                                {run.passed_steps}
                              </span>
                              {" / "}
                              <span className="text-red-600">
                                {run.failed_steps}
                              </span>
                              {" / "}
                              <span className="text-yellow-600">
                                {run.skipped_steps}
                              </span>
                              <span className="text-muted-foreground">
                                {" "}({run.total_steps})
                              </span>
                            </TableCell>
                            <TableCell>
                              {run.duration_ms != null
                                ? `${(run.duration_ms / 1000).toFixed(1)}s`
                                : "-"}
                            </TableCell>
                            <TableCell>
                              {new Date(run.created_at).toLocaleString("zh-CN")}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      )}

      {/* Add/Edit step dialog */}
      <Dialog open={stepDialogOpen} onOpenChange={setStepDialogOpen}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>
              {editingStep ? "编辑步骤" : "添加步骤"}
            </DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="stepName">步骤名称</Label>
              <Input
                id="stepName"
                placeholder="请输入步骤名称"
                value={stepName}
                onChange={(e) => setStepName(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="stepDesc">描述</Label>
              <Textarea
                id="stepDesc"
                placeholder="可选描述"
                value={stepDesc}
                onChange={(e) => setStepDesc(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setStepDialogOpen(false)}>
              取消
            </Button>
            <Button
              onClick={editingStep ? handleUpdateStep : handleAddStep}
              disabled={!stepName.trim()}
            >
              {editingStep ? "保存" : "添加"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete step confirmation */}
      <AlertDialog
        open={deleteStepId !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteStepId(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除</AlertDialogTitle>
            <AlertDialogDescription>
              确定删除该步骤吗？删除后剩余步骤将自动重排序。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteStep}>
              确定删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
