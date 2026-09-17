"use client";

/**
 * 概览卡片 + 趋势图 + 失败 TOP。
 *
 * 图表口径说明：趋势按天聚合的是**用例数**（expected/unexpected），不是执行次数——
 * 一次执行跑 10 条用例和跑 1 条，在「这周质量怎么样」这个问题上不是一个量级。
 */

import React from "react";
import {
  Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip,
  XAxis, YAxis,
} from "recharts";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { WebUiStats } from "@/lib/api/useNewModules";
import { cn } from "@/lib/utils";

function StatCard({
  label, value, hint, tone,
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  tone?: string;
}) {
  return (
    <Card className="p-3">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className={cn("mt-0.5 text-xl font-semibold tabular-nums", tone)}>{value}</div>
      {hint && <div className="mt-0.5 text-[11px] text-muted-foreground">{hint}</div>}
    </Card>
  );
}

function passRateTone(rate: number | null | undefined): string {
  if (rate === null || rate === undefined) return "";
  if (rate >= 0.99) return "text-emerald-600";
  if (rate >= 0.8) return "text-amber-600";
  return "text-red-600";
}

export function RunOverview({ stats, days }: { stats?: WebUiStats; days: number }) {
  if (!stats) {
    return (
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Card key={i} className="h-[76px] animate-pulse bg-muted/40 p-3" />
        ))}
      </div>
    );
  }
  const rate = stats.pass_rate;
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="用例脚本" value={stats.scripts} hint="已入库的 Playwright 用例" />
        <StatCard label={`近 ${days} 天执行`} value={stats.runs}
                  hint={`共 ${stats.cases} 条用例被执行`} />
        <StatCard
          label="用例通过率"
          value={rate === null ? "—" : `${(rate * 100).toFixed(1)}%`}
          tone={passRateTone(rate)}
          hint={stats.cases ? `${stats.expected} 通过 / ${stats.unexpected} 失败` : "窗口内没有执行"}
        />
        <StatCard
          label="平均单次耗时"
          value={stats.avg_duration_ms ? `${(stats.avg_duration_ms / 1000).toFixed(1)}s` : "—"}
          hint="playwright CLI 墙钟时长"
        />
      </div>

      <div className="grid gap-3 lg:grid-cols-3">
        <Card className="p-3 lg:col-span-2">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-medium">近 {days} 天趋势</span>
            <span className="text-[11px] text-muted-foreground">
              柱＝用例数（绿通过/红失败）　线＝当日通过率
            </span>
          </div>
          {stats.trend.length === 0 ? (
            <p className="py-10 text-center text-xs text-muted-foreground">
              窗口内没有执行记录，跑一次就会出现在这里
            </p>
          ) : (
            <div className="h-[240px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={stats.trend} margin={{ top: 4, right: 8, bottom: 0, left: -18 }}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" vertical={false} />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={(v: string) => v.slice(5)} />
                  <YAxis yAxisId="cases" tick={{ fontSize: 11 }} allowDecimals={false} />
                  <YAxis yAxisId="rate" orientation="right" tick={{ fontSize: 11 }}
                         domain={[0, 1]} tickFormatter={(v: number) => `${Math.round(v * 100)}%`} />
                  <Tooltip
                    formatter={(value, name) => (String(name) === "通过率"
                      ? [`${(Number(value) * 100).toFixed(1)}%`, String(name)]
                      : [String(value), String(name)])}
                    labelFormatter={(label) => `日期 ${String(label ?? "")}`}
                  />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar yAxisId="cases" dataKey="expected" name="通过" stackId="cases"
                       fill="#10b981" radius={[0, 0, 0, 0]} maxBarSize={28} />
                  <Bar yAxisId="cases" dataKey="unexpected" name="失败" stackId="cases"
                       fill="#ef4444" radius={[3, 3, 0, 0]} maxBarSize={28} />
                  <Line yAxisId="rate" type="monotone" dataKey="pass_rate" name="通过率"
                        stroke="#6366f1" strokeWidth={2} dot={{ r: 3 }} connectNulls />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>

        <Card className="p-3">
          <div className="mb-2 text-sm font-medium">失败最多的用例</div>
          {stats.top_failures.length === 0 ? (
            <p className="py-6 text-center text-xs text-muted-foreground">窗口内没有失败用例</p>
          ) : (
            <ol className="flex flex-col gap-1.5">
              {stats.top_failures.map((item) => (
                <li key={item.title} className="flex items-start justify-between gap-2 text-xs">
                  <span className="min-w-0 flex-1 truncate" title={item.title}>{item.title}</span>
                  <Badge variant="secondary" className="shrink-0 font-normal">×{item.count}</Badge>
                </li>
              ))}
            </ol>
          )}
          <p className="mt-2 text-[11px] text-muted-foreground">
            反复失败的同一条用例优先修——它通常不是站点变了，而是断言写得不对。
          </p>
        </Card>
      </div>
    </div>
  );
}
