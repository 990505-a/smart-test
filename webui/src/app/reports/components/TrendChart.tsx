"use client";

import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import type { TestRunInfo } from "@/app/types/api";

interface TrendChartProps {
  runs: TestRunInfo[];
}

export function TrendChart({ runs }: TrendChartProps) {
  const data = runs.map((run) => {
    const total =
      run.passed_count +
      run.failed_count +
      run.skipped_count +
      run.blocked_count +
      run.not_executed_count;
    const passRate = total > 0 ? Math.round((run.passed_count / total) * 1000) / 10 : 0;
    return {
      name: run.name.length > 12 ? run.name.slice(0, 12) + "..." : run.name,
      passRate,
    };
  });

  if (data.length === 0) {
    return <div className="flex h-[300px] items-center justify-center text-muted-foreground">暂无趋势数据</div>;
  }

  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="name" />
        <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
        <Tooltip formatter={(value) => `${value}%`} />
        <Line
          type="monotone"
          dataKey="passRate"
          stroke="#22c55e"
          name="通过率"
          dot={{ r: 4 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
