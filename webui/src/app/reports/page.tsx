"use client";

import { useState, useMemo } from "react";
import { ManagementLayout } from "@/app/components/ManagementLayout";
import { CoverageChart } from "./components/CoverageChart";
import { TrendChart } from "./components/TrendChart";
import { ModuleDistributionChart } from "./components/ModuleDistributionChart";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useProjects } from "@/lib/api/useProjects";
import { useTestRuns } from "@/lib/api/useTestRuns";

export default function ReportsPage() {
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const { data: projectsData } = useProjects(1, 100);
  const projects = projectsData?.data ?? [];

  // Fetch test runs for selected project (up to 100 for reporting)
  const { data: runsData, isLoading, error } = useTestRuns(1, 100, selectedProjectId ?? undefined);
  const runs = runsData?.data ?? [];

  // Compute summary stats
  const stats = useMemo(() => {
    const runCount = runs.length;
    const totalCases = runs.reduce((sum, r) => sum + r.test_cases_count, 0);
    const totalFailed = runs.reduce((sum, r) => sum + r.failed_count, 0);

    let passRateSum = 0;
    let runsWithCases = 0;
    for (const run of runs) {
      const total =
        run.passed_count +
        run.failed_count +
        run.skipped_count +
        run.blocked_count +
        run.not_executed_count;
      if (total > 0) {
        passRateSum += run.passed_count / total;
        runsWithCases++;
      }
    }
    const avgPassRate = runsWithCases > 0 ? Math.round((passRateSum / runsWithCases) * 1000) / 10 : 0;

    return { runCount, totalCases, avgPassRate, totalFailed };
  }, [runs]);

  // Reset project selection
  const handleProjectChange = (val: string | null) => {
    setSelectedProjectId(val);
  };

  return (
    <ManagementLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center gap-4">
          <h2 className="text-2xl font-bold">测试报告</h2>
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

        {/* Stats row */}
        <div className="grid grid-cols-4 gap-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">总执行次数</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.runCount}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">总测试用例</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.totalCases}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">平均通过率</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.avgPassRate}%</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">失败用例数</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-red-600">{stats.totalFailed}</div>
            </CardContent>
          </Card>
        </div>

        {/* Charts grid */}
        {error ? (
          <div className="py-8 text-center">
            <p className="text-destructive">加载失败</p>
          </div>
        ) : isLoading ? (
          <div className="py-8 text-center text-muted-foreground">加载中...</div>
        ) : (
          <div className="grid grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>覆盖率分布</CardTitle>
              </CardHeader>
              <CardContent>
                <CoverageChart runs={runs} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>通过率趋势</CardTitle>
              </CardHeader>
              <CardContent>
                <TrendChart runs={runs} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>状态分布</CardTitle>
              </CardHeader>
              <CardContent>
                <ModuleDistributionChart runs={runs} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>更多图表</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex h-[300px] items-center justify-center text-muted-foreground">
                  更多图表开发中...
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </ManagementLayout>
  );
}
