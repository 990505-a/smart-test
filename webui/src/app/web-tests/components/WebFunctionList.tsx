"use client";

import { useState, useCallback } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ChevronDown, ChevronRight, Globe, Layers } from "lucide-react";
import { useSubFunctions } from "@/lib/api/useWebFunctions";
import type { WebFunctionInfo, WebSubFunctionInfo } from "@/app/types/api";

interface WebFunctionListProps {
  functions: WebFunctionInfo[];
  projectId: string;
  onFunctionSelect: (functionId: string | null, subFunctionId?: string | null) => void;
  selectedFunctionId: string | null;
  isLoading?: boolean;
}

function StatusBadge({ status }: { status: string | null }) {
  if (!status) return <Badge variant="secondary">未执行</Badge>;

  const variantMap: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
    passed: "default",
    completed: "default",
    failed: "destructive",
    running: "secondary",
    pending: "outline",
  };

  const labelMap: Record<string, string> = {
    passed: "通过",
    completed: "完成",
    failed: "失败",
    running: "运行中",
    pending: "待执行",
    cancelled: "已取消",
  };

  return (
    <Badge variant={variantMap[status] || "secondary"}>
      {labelMap[status] || status}
    </Badge>
  );
}

function PriorityBadge({ priority }: { priority: string }) {
  const variantMap: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
    critical: "destructive",
    high: "default",
    medium: "secondary",
    low: "outline",
  };

  const labelMap: Record<string, string> = {
    critical: "严重",
    high: "高",
    medium: "中",
    low: "低",
  };

  return (
    <Badge variant={variantMap[priority] || "secondary"}>
      {labelMap[priority] || priority}
    </Badge>
  );
}

function SubFunctionItem({
  subFunction,
  isSelected,
  onSelect,
}: {
  subFunction: WebSubFunctionInfo;
  isSelected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      className={`w-full text-left px-3 py-2 rounded-md text-sm hover:bg-accent transition-colors ${
        isSelected ? "bg-accent font-medium" : ""
      }`}
      onClick={onSelect}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate">{subFunction.display_name}</span>
        <div className="flex items-center gap-1 flex-shrink-0">
          <PriorityBadge priority={subFunction.priority} />
          {subFunction.total_test_cases > 0 && (
            <Badge variant="outline" className="text-xs">
              {subFunction.total_test_cases}用例
            </Badge>
          )}
        </div>
      </div>
    </button>
  );
}

function FunctionCard({
  func,
  projectId,
  isSelected,
  isExpanded,
  onSelect,
  onToggleExpand,
  onSubFunctionSelect,
  selectedSubFunctionId,
}: {
  func: WebFunctionInfo;
  projectId: string;
  isSelected: boolean;
  isExpanded: boolean;
  onSelect: () => void;
  onToggleExpand: () => void;
  onSubFunctionSelect: (subFunc: WebSubFunctionInfo) => void;
  selectedSubFunctionId: string | null;
}) {
  const { data: subFunctionsData, isLoading: isLoadingSubs } = useSubFunctions(
    isExpanded ? projectId : null,
    isExpanded ? func.id : null,
    1,
    100,
  );

  const subFunctions = subFunctionsData?.data ?? [];

  return (
    <Card className={`${isSelected ? "ring-2 ring-primary" : ""}`}>
      <CardContent className="p-3">
        {/* Function header */}
        <div className="flex items-start gap-2">
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0 mt-0.5"
            onClick={onToggleExpand}
          >
            {isExpanded ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )}
          </Button>
          <button
            className="flex-1 text-left"
            onClick={onSelect}
          >
            <div className="font-medium text-sm">{func.display_name}</div>
            <div className="flex items-center gap-2 mt-1">
              <span className="font-mono text-xs text-muted-foreground">{func.identifier}</span>
              {func.base_url && (
                <span className="text-xs text-muted-foreground truncate max-w-[150px]">
                  {func.base_url}
                </span>
              )}
            </div>
          </button>
          <div className="flex items-center gap-1 flex-shrink-0">
            <StatusBadge status={func.last_run_status} />
          </div>
        </div>

        {/* Function stats */}
        <div className="flex items-center gap-3 mt-2 ml-8 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <Layers className="h-3 w-3" />
            {func.total_sub_functions} 子功能
          </span>
          <span className="flex items-center gap-1">
            <Globe className="h-3 w-3" />
            {func.total_test_cases} 测试用例
          </span>
        </div>

        {/* Expanded sub-functions */}
        {isExpanded && (
          <div className="mt-2 ml-8 border-l-2 border-muted pl-3 space-y-1">
            {isLoadingSubs ? (
              <div className="space-y-1">
                {Array.from({ length: 2 }).map((_, i) => (
                  <Skeleton key={i} className="h-8 w-full" />
                ))}
              </div>
            ) : subFunctions.length === 0 ? (
              <p className="text-xs text-muted-foreground py-1">暂无子功能</p>
            ) : (
              subFunctions.map((sf) => (
                <SubFunctionItem
                  key={sf.id}
                  subFunction={sf}
                  isSelected={selectedSubFunctionId === sf.id}
                  onSelect={() => onSubFunctionSelect(sf)}
                />
              ))
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function WebFunctionList({
  functions,
  projectId,
  onFunctionSelect,
  selectedFunctionId,
  isLoading,
}: WebFunctionListProps) {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [selectedSubFunctionId, setSelectedSubFunctionId] = useState<string | null>(null);

  const toggleExpand = useCallback((id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const handleFunctionSelect = useCallback(
    (func: WebFunctionInfo) => {
      setSelectedSubFunctionId(null);
      onFunctionSelect(func.id);
    },
    [onFunctionSelect],
  );

  const handleSubFunctionSelect = useCallback(
    (subFunc: WebSubFunctionInfo) => {
      setSelectedSubFunctionId(subFunc.id);
      onFunctionSelect(subFunc.function_id, subFunc.id);
    },
    [onFunctionSelect],
  );

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-24 w-full" />
        ))}
      </div>
    );
  }

  if (functions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-8">
        <Globe className="h-8 w-8 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">暂无Web功能</p>
        <p className="text-xs text-muted-foreground">点击上方按钮创建新功能</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {functions.map((func) => (
        <FunctionCard
          key={func.id}
          func={func}
          projectId={projectId}
          isSelected={selectedFunctionId === func.id}
          isExpanded={expandedIds.has(func.id)}
          onSelect={() => handleFunctionSelect(func)}
          onToggleExpand={() => toggleExpand(func.id)}
          onSubFunctionSelect={handleSubFunctionSelect}
          selectedSubFunctionId={selectedSubFunctionId}
        />
      ))}
    </div>
  );
}
