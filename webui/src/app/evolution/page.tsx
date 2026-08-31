"use client";

import React, { useState } from "react";
import { PageHeader, StatusBadge, EmptyState } from "@/app/components/ui-patterns";
import { useEvolutionRuns, useEvolutionSchedule } from "@/lib/api/useNewModules";
import { apiClient } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { Play, Clock, Sparkles } from "lucide-react";
import { MarkdownContent } from "@/app/components/MarkdownContent";

export default function EvolutionPage() {
  const runs = useEvolutionRuns();
  const schedule = useEvolutionSchedule();
  const [hour, setHour] = useState("2");
  const [minute, setMinute] = useState("0");
  const [triggering, setTriggering] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

  const trigger = async () => {
    setTriggering(true);
    try {
      await apiClient.post("/evolution/trigger", {});
      toast.success("自进化已在后台启动，稍后刷新查看结果");
      setTimeout(() => runs.mutate(), 3000);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "触发失败");
    } finally {
      setTriggering(false);
    }
  };

  const saveSchedule = async () => {
    try {
      await apiClient.put(`/evolution/schedule?hour=${hour}&minute=${minute}`, {});
      toast.success("调度时间已更新");
      schedule.mutate();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "保存失败");
    }
  };

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-5xl px-6 py-8 lg:px-8">
        <div className="flex flex-col gap-5">
          <PageHeader
            title="自进化"
            description="每晚自动聚合沉淀标注 → LLM 反思好/坏原因 → 经验记录在运行历史中供回看；技能库由你手动维护，进化不会修改技能文件"
            actions={
              <Button onClick={trigger} disabled={triggering}>
                <Play className="mr-1.5 h-4 w-4" />{triggering ? "启动中…" : "立即进化一次"}
              </Button>
            }
          />

        {/* 调度状态 */}
        <Card className="p-4">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2 text-sm">
              <Clock className="h-4 w-4 text-muted-foreground" />
              {schedule.data?.jobs?.[0] ? (
                <>
                  每日自进化：{schedule.data.jobs[0].trigger}
                  {schedule.data.jobs[0].next_run && (
                    <span className="text-muted-foreground">
                      （下次：{new Date(schedule.data.jobs[0].next_run).toLocaleString("zh-CN")}）
                    </span>
                  )}
                </>
              ) : "调度未启动"}
            </div>
            <div className="ml-auto flex items-end gap-2">
              <div className="flex flex-col gap-1">
                <Label className="text-xs">时</Label>
                <Input className="w-16" value={hour} onChange={(e) => setHour(e.target.value)} />
              </div>
              <div className="flex flex-col gap-1">
                <Label className="text-xs">分</Label>
                <Input className="w-16" value={minute} onChange={(e) => setMinute(e.target.value)} />
              </div>
              <Button size="sm" variant="outline" onClick={saveSchedule}>调整时间</Button>
            </div>
          </div>
        </Card>

        {/* 运行历史 */}
        <div className="flex flex-col gap-3">
          {runs.isLoading && (
            <div className="flex flex-1 items-center justify-center py-16 text-sm text-muted-foreground">
              加载中…
            </div>
          )}
          {(runs.data ?? []).map((run) => (
            <Card key={run.id} className="p-4">
              <div className="flex items-center gap-3">
                <StatusBadge status={run.status} />
                <Sparkles className="h-4 w-4 text-warning" />
                <span className="text-sm">
                  {run.created_at ? new Date(run.created_at).toLocaleString("zh-CN") : "-"}
                </span>
                <Badge variant="outline">{run.trigger === "scheduled" ? "定时" : "手动"}</Badge>
                <span className="text-sm text-muted-foreground">
                  标注 {run.annotations_total}（好 {run.good_count} / 坏 {run.bad_count}）
                </span>
                <Button
                  size="sm" variant="ghost" className="ml-auto"
                  onClick={() => setExpanded(expanded === run.id ? null : run.id)}
                >
                  {expanded === run.id ? "收起" : "详情"}
                </Button>
              </div>
              {run.regression_summary && (
                <div className="mt-2 text-sm text-muted-foreground">{run.regression_summary}</div>
              )}
              {run.error && <div className="mt-2 text-sm text-destructive">{run.error}</div>}
              {expanded === run.id && run.lessons && (
                <div className="mt-3 rounded-md border bg-muted/30 p-3">
                  <MarkdownContent content={run.lessons} />
                </div>
              )}
              {expanded === run.id && run.skill_patches && (
                <div className="mt-2 rounded-lg border bg-muted/50 p-3 font-mono text-xs overflow-auto max-h-64">
                  {run.skill_patches}
                </div>
              )}
            </Card>
          ))}
          {!runs.isLoading && (runs.data ?? []).length === 0 && (
            <EmptyState
              title="还没有进化记录"
              description="先在「用例沉淀」中标注用例，然后点击「立即进化一次」"
            />
          )}
        </div>
        </div>
      </div>
    </div>
  );
}
