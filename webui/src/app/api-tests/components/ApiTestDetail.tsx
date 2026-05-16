"use client";

import { useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowLeft, Play, FileCode, History } from "lucide-react";
import {
  useApiTest,
  useApiTestRuns,
} from "@/lib/api/useApiTests";
import { triggerExecution } from "@/lib/api/useApiTests";
import { SchemaUpload } from "./SchemaUpload";
import { RunHistory } from "./RunHistory";
import type { APITestInfo } from "@/app/types/api";

interface ApiTestDetailProps {
  test: APITestInfo;
  onBack: () => void;
}

export function ApiTestDetail({ test, onBack }: ApiTestDetailProps) {
  const [activeTab, setActiveTab] = useState("details");

  // Refresh test data from server
  const { data: testData, isLoading } = useApiTest(test.project_id, test.id);
  const currentTest = testData?.data ?? test;

  // Run history
  const { data: runsData } = useApiTestRuns(test.project_id, test.id, 20);
  const runs = runsData?.data ?? [];

  const [isRunning, setIsRunning] = useState(false);

  const handleRun = useCallback(async () => {
    setIsRunning(true);
    try {
      await triggerExecution(test.project_id, test.id);
    } finally {
      setIsRunning(false);
    }
  }, [test.project_id, test.id]);

  const statusColor = (status: string) => {
    switch (status) {
      case "playwright":
        return "bg-blue-100 text-blue-800";
      case "pytest":
        return "bg-green-100 text-green-800";
      case "supertest":
        return "bg-purple-100 text-purple-800";
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
          <h2 className="text-xl font-semibold">{currentTest.name}</h2>
          <Badge variant="outline" className="font-mono text-xs">
            {currentTest.identifier}
          </Badge>
          <Badge className={statusColor(currentTest.script_format)}>
            {currentTest.script_format}
          </Badge>
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={handleRun} disabled={isRunning}>
            <Play className="mr-2 h-4 w-4" />
            {isRunning ? "执行中..." : "执行测试"}
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
            <TabsTrigger value="details">详情</TabsTrigger>
            <TabsTrigger value="script">
              <FileCode className="mr-1 h-4 w-4" />
              脚本
            </TabsTrigger>
            <TabsTrigger value="runs">
              <History className="mr-1 h-4 w-4" />
              执行历史
            </TabsTrigger>
            <TabsTrigger value="upload">
              Schema上传
            </TabsTrigger>
          </TabsList>

          <TabsContent value="details" className="mt-4">
            <Card>
              <CardHeader>
                <CardTitle>测试信息</CardTitle>
              </CardHeader>
              <CardContent>
                <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
                  <div>
                    <dt className="text-muted-foreground">ID</dt>
                    <dd className="font-mono">{currentTest.id}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">名称</dt>
                    <dd>{currentTest.name}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">描述</dt>
                    <dd>{currentTest.description || "-"}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Schema类型</dt>
                    <dd>{currentTest.schema_type}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Schema URL</dt>
                    <dd className="truncate">{currentTest.schema_url || "-"}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">脚本语言</dt>
                    <dd>{currentTest.script_language}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">端点数</dt>
                    <dd>{currentTest.total_endpoints}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">场景数</dt>
                    <dd>{currentTest.total_scenarios}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">创建时间</dt>
                    <dd>{new Date(currentTest.created_at).toLocaleString("zh-CN")}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">更新时间</dt>
                    <dd>
                      {currentTest.updated_at
                        ? new Date(currentTest.updated_at).toLocaleString("zh-CN")
                        : "-"}
                    </dd>
                  </div>
                </dl>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="script" className="mt-4">
            <Card>
              <CardHeader>
                <CardTitle>测试脚本</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="rounded-md bg-muted p-4">
                  <pre className="text-sm font-mono whitespace-pre-wrap">
                    {currentTest.script_path || "暂无脚本文件"}
                  </pre>
                </div>
                {currentTest.script_path && (
                  <p className="mt-2 text-xs text-muted-foreground">
                    脚本路径: {currentTest.script_path}
                  </p>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="runs" className="mt-4">
            <RunHistory runs={runs} projectId={test.project_id} testId={test.id} />
          </TabsContent>

          <TabsContent value="upload" className="mt-4">
            <SchemaUpload projectId={test.project_id} />
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
}
