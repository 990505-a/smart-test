"use client";

import { useState, useCallback } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  ChevronDown,
  ChevronRight,
  Play,
  Clock,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Loader2,
} from "lucide-react";
import { useWebTests, useWebTestRuns, triggerWebTestExecution } from "@/lib/api/useWebTests";
import type { WebTestInfo } from "@/app/types/api";

interface WebTestListProps {
  projectId: string;
  functionId?: string | null;
  subFunctionId?: string | null;
}

function RunStatusBadge({ status }: { status: string }) {
  const config: Record<string, { icon: React.ReactNode; className: string }> = {
    pending: {
      icon: <Clock className="h-3 w-3" />,
      className: "text-yellow-600 bg-yellow-50 border-yellow-200",
    },
    running: {
      icon: <Loader2 className="h-3 w-3 animate-spin" />,
      className: "text-blue-600 bg-blue-50 border-blue-200",
    },
    completed: {
      icon: <CheckCircle2 className="h-3 w-3" />,
      className: "text-green-600 bg-green-50 border-green-200",
    },
    passed: {
      icon: <CheckCircle2 className="h-3 w-3" />,
      className: "text-green-600 bg-green-50 border-green-200",
    },
    failed: {
      icon: <XCircle className="h-3 w-3" />,
      className: "text-red-600 bg-red-50 border-red-200",
    },
    cancelled: {
      icon: <AlertCircle className="h-3 w-3" />,
      className: "text-gray-600 bg-gray-50 border-gray-200",
    },
  };

  const labelMap: Record<string, string> = {
    pending: "待执行",
    running: "运行中",
    completed: "已完成",
    passed: "通过",
    failed: "失败",
    cancelled: "已取消",
  };

  const { icon, className } = config[status] || config.pending;

  return (
    <Badge variant="outline" className={`gap-1 ${className}`}>
      {icon}
      {labelMap[status] || status}
    </Badge>
  );
}

function TestRunHistory({
  projectId,
  testId,
}: {
  projectId: string;
  testId: string;
}) {
  const { data: runsData, isLoading } = useWebTestRuns(projectId, testId, 5);
  const runs = (runsData?.data ?? []) as Array<{ id: string; status: string; identifier: string; total_tests: number; passed_tests: number; failed_tests: number; duration_ms: number | null; created_at: string }>;

  if (isLoading) {
    return (
      <div className="p-2">
        <Skeleton className="h-6 w-full" />
      </div>
    );
  }

  if (runs.length === 0) {
    return (
      <div className="p-2 text-xs text-muted-foreground">
        暂无执行记录
      </div>
    );
  }

  return (
    <div className="p-2 space-y-1">
      {runs.map((run) => (
        <div
          key={run.id}
          className="flex items-center justify-between text-xs px-2 py-1.5 rounded bg-muted/50"
        >
          <div className="flex items-center gap-2">
            <RunStatusBadge status={run.status} />
            <span className="font-mono text-muted-foreground">{run.identifier}</span>
          </div>
          <div className="flex items-center gap-3 text-muted-foreground">
            <span>{run.passed_tests}/{run.total_tests} 通过</span>
            {run.duration_ms !== null && <span>{run.duration_ms}ms</span>}
            <span>{new Date(run.created_at).toLocaleString("zh-CN")}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

export function WebTestList({
  projectId,
  functionId,
  subFunctionId,
}: WebTestListProps) {
  const [page, setPage] = useState(1);
  const pageSize = 30;
  const [expandedTestId, setExpandedTestId] = useState<string | null>(null);

  const { data, error, isLoading, mutate } = useWebTests(
    projectId,
    page,
    pageSize,
    functionId,
    subFunctionId,
  );

  const handleRun = useCallback(
    async (test: WebTestInfo) => {
      await triggerWebTestExecution(test.project_id, test.id);
      mutate();
    },
    [mutate],
  );

  const toggleExpand = useCallback((testId: string) => {
    setExpandedTestId((prev) => (prev === testId ? null : testId));
  }, []);

  if (!functionId && !subFunctionId) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-16">
        <p className="text-muted-foreground">请从左侧选择一个功能查看关联的测试</p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-8">
        <p className="text-destructive">加载测试列表失败</p>
        <Button variant="outline" size="sm" onClick={() => mutate()}>
          重试
        </Button>
      </div>
    );
  }

  if (!data?.data?.length) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-8">
        <p className="text-muted-foreground">该功能暂无关联的Web测试</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium">
          关联测试 ({data.info?.total ?? data.data.length})
        </h3>
      </div>

      <div className="border rounded-md">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-8" />
              <TableHead className="w-[120px]">标识</TableHead>
              <TableHead>名称</TableHead>
              <TableHead className="w-[100px]">状态</TableHead>
              <TableHead className="w-[140px]">创建时间</TableHead>
              <TableHead className="w-20">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.data.map((test) => (
              <>
                <TableRow
                  key={test.id}
                  className="cursor-pointer hover:bg-muted/50"
                  onClick={() => toggleExpand(test.id)}
                >
                  <TableCell>
                    {expandedTestId === test.id ? (
                      <ChevronDown className="h-4 w-4 text-muted-foreground" />
                    ) : (
                      <ChevronRight className="h-4 w-4 text-muted-foreground" />
                    )}
                  </TableCell>
                  <TableCell>
                    <span className="font-mono text-xs">{test.identifier}</span>
                  </TableCell>
                  <TableCell>
                    <span className="font-medium">{test.name}</span>
                    {test.description && (
                      <p className="text-xs text-muted-foreground truncate max-w-[300px]">
                        {test.description}
                      </p>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{test.script_format}</Badge>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {new Date(test.created_at).toLocaleDateString("zh-CN")}
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleRun(test);
                      }}
                      title="执行测试"
                    >
                      <Play className="h-4 w-4" />
                    </Button>
                  </TableCell>
                </TableRow>
                {expandedTestId === test.id && (
                  <TableRow key={`${test.id}-runs`}>
                    <TableCell colSpan={6} className="p-0 border-t-0">
                      <TestRunHistory projectId={projectId} testId={test.id} />
                    </TableCell>
                  </TableRow>
                )}
              </>
            ))}
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      {data.info && data.info.total > pageSize && (
        <div className="flex items-center justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={!data.info.prev || page <= 1}
            onClick={() => setPage(page - 1)}
          >
            上一页
          </Button>
          <span className="text-sm text-muted-foreground">
            第 {data.info.page} 页 / 共 {Math.ceil(data.info.total / data.info.page_size)} 页
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={!data.info.next}
            onClick={() => setPage(page + 1)}
          >
            下一页
          </Button>
        </div>
      )}
    </div>
  );
}
