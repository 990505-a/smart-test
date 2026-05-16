"use client";

import { useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useApiTestResults } from "@/lib/api/useApiTests";
import type { APITestRunInfo } from "@/app/types/api";

interface RunHistoryProps {
  runs: APITestRunInfo[];
  projectId: string;
  testId: string;
}

function statusBadgeColor(status: string) {
  switch (status) {
    case "completed":
      return "bg-green-100 text-green-800";
    case "running":
      return "bg-yellow-100 text-yellow-800";
    case "failed":
      return "bg-red-100 text-red-800";
    case "pending":
    case "cancelled":
    default:
      return "bg-gray-100 text-gray-800";
  }
}

function resultStatusColor(status: string) {
  switch (status) {
    case "passed":
      return "bg-green-100 text-green-800";
    case "failed":
      return "bg-red-100 text-red-800";
    case "skipped":
      return "bg-yellow-100 text-yellow-800";
    case "blocked":
      return "bg-orange-100 text-orange-800";
    default:
      return "bg-gray-100 text-gray-800";
  }
}

function RunRow({
  run,
  projectId,
  testId,
}: {
  run: APITestRunInfo;
  projectId: string;
  testId: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const { data: resultsData } = useApiTestResults(
    expanded ? projectId : null,
    expanded ? testId : null,
    expanded ? run.id : null,
  );
  const results = resultsData?.data ?? [];

  return (
    <>
      <TableRow
        className="cursor-pointer hover:bg-muted/50"
        onClick={() => setExpanded(!expanded)}
      >
        <TableCell>
          {expanded ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronRight className="h-4 w-4" />
          )}
        </TableCell>
        <TableCell className="font-mono text-xs">{run.identifier}</TableCell>
        <TableCell>
          <Badge className={statusBadgeColor(run.status)}>{run.status}</Badge>
        </TableCell>
        <TableCell>
          <span className="text-green-600">{run.passed_tests}</span>
          {" / "}
          <span className="text-red-600">{run.failed_tests}</span>
          {" / "}
          <span className="text-yellow-600">{run.skipped_tests}</span>
          <span className="text-muted-foreground"> ({run.total_tests})</span>
        </TableCell>
        <TableCell>
          {run.duration_ms != null ? `${(run.duration_ms / 1000).toFixed(1)}s` : "-"}
        </TableCell>
        <TableCell>
          {new Date(run.created_at).toLocaleString("zh-CN")}
        </TableCell>
      </TableRow>

      {/* Expanded results */}
      {expanded && results.length > 0 && (
        results.map((r) => (
          <TableRow key={r.id} className="bg-muted/30">
            <TableCell />
            <TableCell />
            <TableCell>
              <Badge className={resultStatusColor(r.status)}>{r.status}</Badge>
            </TableCell>
            <TableCell>
              <span className="text-sm">
                {r.method && (
                  <span className="font-mono text-xs font-bold mr-1">
                    {r.method}
                  </span>
                )}
                {r.endpoint || r.scenario_name || "-"}
              </span>
            </TableCell>
            <TableCell>
              {r.duration_ms != null
                ? `${r.duration_ms}ms`
                : "-"}
            </TableCell>
            <TableCell>
              {r.error_message && (
                <span className="text-xs text-destructive truncate max-w-[200px] block">
                  {r.error_message}
                </span>
              )}
            </TableCell>
          </TableRow>
        ))
      )}
    </>
  );
}

export function RunHistory({ runs, projectId, testId }: RunHistoryProps) {
  if (runs.length === 0) {
    return (
      <div className="py-8 text-center text-muted-foreground">
        暂无执行记录
      </div>
    );
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-10" />
            <TableHead>标识</TableHead>
            <TableHead>状态</TableHead>
            <TableHead>通过/失败/跳过</TableHead>
            <TableHead>耗时</TableHead>
            <TableHead>执行时间</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {runs.map((run) => (
            <RunRow
              key={run.id}
              run={run}
              projectId={projectId}
              testId={testId}
            />
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
