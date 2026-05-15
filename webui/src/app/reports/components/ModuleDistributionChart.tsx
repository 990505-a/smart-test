"use client";

import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from "recharts";
import type { TestRunInfo } from "@/app/types/api";

interface ModuleDistributionChartProps {
  runs: TestRunInfo[];
}

const COLORS = {
  passed: "#22c55e",
  failed: "#ef4444",
  skipped: "#f59e0b",
  blocked: "#6b7280",
  not_executed: "#d1d5db",
};

const LABELS: Record<string, string> = {
  passed: "通过",
  failed: "失败",
  skipped: "跳过",
  blocked: "阻塞",
  not_executed: "未执行",
};

export function ModuleDistributionChart({ runs }: ModuleDistributionChartProps) {
  // Aggregate totals across all runs
  const totals = runs.reduce(
    (acc, run) => ({
      passed: acc.passed + run.passed_count,
      failed: acc.failed + run.failed_count,
      skipped: acc.skipped + run.skipped_count,
      blocked: acc.blocked + run.blocked_count,
      not_executed: acc.not_executed + run.not_executed_count,
    }),
    { passed: 0, failed: 0, skipped: 0, blocked: 0, not_executed: 0 }
  );

  const data = Object.entries(totals)
    .filter(([, value]) => value > 0)
    .map(([key, value]) => ({
      name: LABELS[key] || key,
      value,
      color: COLORS[key as keyof typeof COLORS],
    }));

  if (data.length === 0) {
    return <div className="flex h-[300px] items-center justify-center text-muted-foreground">暂无分布数据</div>;
  }

  return (
    <ResponsiveContainer width="100%" height={300}>
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={100} label>
          {data.map((entry, index) => (
            <Cell key={index} fill={entry.color} />
          ))}
        </Pie>
        <Tooltip />
        <Legend />
      </PieChart>
    </ResponsiveContainer>
  );
}
