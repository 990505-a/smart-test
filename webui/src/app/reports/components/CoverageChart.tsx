"use client";

import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import type { TestRunInfo } from "@/app/types/api";

interface CoverageChartProps {
  runs: TestRunInfo[];
}

export function CoverageChart({ runs }: CoverageChartProps) {
  const data = runs.map((run) => ({
    name: run.name.length > 12 ? run.name.slice(0, 12) + "..." : run.name,
    passed: run.passed_count,
    failed: run.failed_count,
    skipped: run.skipped_count,
    blocked: run.blocked_count,
  }));

  if (data.length === 0) {
    return <div className="flex h-[300px] items-center justify-center text-muted-foreground">暂无覆盖率数据</div>;
  }

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="name" />
        <YAxis />
        <Tooltip />
        <Legend />
        <Bar dataKey="passed" fill="#22c55e" name="通过" stackId="a" />
        <Bar dataKey="failed" fill="#ef4444" name="失败" stackId="a" />
        <Bar dataKey="skipped" fill="#f59e0b" name="跳过" stackId="a" />
        <Bar dataKey="blocked" fill="#6b7280" name="阻塞" stackId="a" />
      </BarChart>
    </ResponsiveContainer>
  );
}
