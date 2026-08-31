"use client";

// 结构化审批视图：把用例 Markdown 解析树渲染成「统计条 + 模块树 + 用例卡片」，
// 代替直接阅读原始 Markdown。待确认问题在这里只读展示——答案统一回聊天里
// 告诉智能体，页面不提供作答入口。

import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  ChevronDown,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  ListTree,
  MessageSquareQuote,
  Search,
} from "lucide-react";
import type {
  CaseDoc,
  CaseGroup,
  CaseItem,
  CaseStep,
} from "@/lib/api/useCaseDocs";

const PRIORITY_ORDER = ["critical", "high", "medium", "low"] as const;

const PRIORITY_LABEL: Record<string, string> = {
  critical: "P0",
  high: "P1",
  medium: "P2",
  low: "P3",
};

const PRIORITY_BADGE: Record<string, string> = {
  critical: "border-destructive/40 bg-destructive/10 text-destructive",
  high: "border-orange-500/40 bg-orange-500/10 text-orange-600 dark:text-orange-400",
  medium: "border-blue-500/30 bg-blue-500/10 text-blue-600 dark:text-blue-400",
  low: "border-border bg-muted text-muted-foreground",
};

interface FlatGroup {
  key: string;
  name: string;
  depth: number;
  cases: CaseItem[];
}

function flattenGroups(groups: CaseGroup[], depth = 0, prefix = ""): FlatGroup[] {
  return groups.flatMap((group, index) => {
    const key = prefix ? `${prefix}/${index}` : `${index}`;
    const nested = flattenGroups(group.children, depth + 1, key);
    const direct = group.cases;
    // 分组自身展示其直接用例；父级不重复统计子分组用例（卡片按选中分组展示）
    return [
      { key, name: group.name, depth, cases: direct },
      ...nested,
    ];
  });
}

function collectCases(groups: CaseGroup[]): CaseItem[] {
  return groups.flatMap((group) => [...group.cases, ...collectCases(group.children)]);
}

function normalizeQuestion(q: unknown): string {
  if (typeof q === "string") return q;
  if (q && typeof q === "object") {
    const item = q as Record<string, unknown>;
    const text = item.question ?? item.title ?? item.summary;
    if (typeof text === "string" && text.trim()) return text.trim();
  }
  return JSON.stringify(q);
}

function StepsList({ steps }: { steps: CaseStep[] }) {
  if (steps.length === 0) return null;
  return (
    <ol className="m-0 list-none space-y-1 p-0">
      {steps.map((step, index) => (
        <li key={index} className="text-sm leading-6">
          <span className="mr-1.5 inline-block min-w-5 text-right font-mono text-[11px] text-muted-foreground">
            {index + 1}.
          </span>
          <span>{step.action}</span>
          {step.expected ? (
            <span className="text-muted-foreground">
              {" "}⇒ <span className="text-foreground/80">{step.expected}</span>
            </span>
          ) : null}
          {step.children && step.children.length > 0 && (
            <div className="mt-1 ml-6 border-l pl-3">
              <StepsList steps={step.children} />
            </div>
          )}
        </li>
      ))}
    </ol>
  );
}

function CaseCard({ item }: { item: CaseItem }) {
  const meta = item.metadata;
  return (
    <div className="rounded-lg border bg-card p-3 shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        <Badge
          variant="outline"
          className={`h-5 px-1.5 text-[11px] font-semibold ${PRIORITY_BADGE[item.priority] ?? PRIORITY_BADGE.low}`}
        >
          {PRIORITY_LABEL[item.priority] ?? item.priority}
        </Badge>
        <span className="text-sm font-medium">{item.name}</span>
        {meta?.case_id && (
          <span className="ml-auto font-mono text-[10px] text-muted-foreground">
            {meta.case_id}
          </span>
        )}
      </div>
      {(meta?.requirements?.length || meta?.risks?.length) && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {meta?.requirements?.map((req) => (
            <Badge key={req} variant="secondary" className="h-4 px-1.5 font-mono text-[10px]">
              {req}
            </Badge>
          ))}
          {meta?.risks?.map((risk) => (
            <Badge
              key={risk}
              variant="outline"
              className="h-4 px-1.5 font-mono text-[10px] text-muted-foreground"
            >
              {risk}
            </Badge>
          ))}
        </div>
      )}
      {item.preconditions && (
        <p className="mt-2 mb-0 text-xs text-muted-foreground">
          <span className="font-medium">前置：</span>
          {item.preconditions}
        </p>
      )}
      <div className="mt-2">
        <StepsList steps={item.steps} />
      </div>
    </div>
  );
}

export function CaseStructureView({ doc }: { doc: CaseDoc }) {
  const tree = doc.parsed?.tree ?? [];
  const [selectedGroup, setSelectedGroup] = useState<string | null>(null);
  const [priorityFilter, setPriorityFilter] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [showQuestions, setShowQuestions] = useState(false);
  const [showCoverage, setShowCoverage] = useState(false);

  const flatGroups = useMemo(() => flattenGroups(tree), [tree]);
  const allCases = useMemo(() => collectCases(tree), [tree]);

  const priorityCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const item of allCases) {
      counts[item.priority] = (counts[item.priority] ?? 0) + 1;
    }
    return counts;
  }, [allCases]);

  // 需求覆盖：需求包里的每个 REQ 被哪些用例引用
  const coverage = useMemo(() => {
    const referenced = new Map<string, string[]>();
    for (const item of allCases) {
      const caseId = item.metadata?.case_id ?? item.name;
      for (const req of item.metadata?.requirements ?? []) {
        const list = referenced.get(req) ?? [];
        list.push(caseId);
        referenced.set(req, list);
      }
    }
    const entries = (doc.requirements ?? [])
      .map((req, index) => {
        const id = req.id ?? `REQ-${index + 1}`;
        return {
          id,
          summary: req.summary ?? "",
          risk: req.risk,
          coveredBy: referenced.get(id) ?? [],
        };
      });
    const covered = entries.filter((e) => e.coveredBy.length > 0).length;
    return { entries, covered, total: entries.length, referenced };
  }, [allCases, doc.requirements]);

  const visibleCases = useMemo(() => {
    let base = allCases;
    if (selectedGroup) {
      const group = flatGroups.find((g) => g.key === selectedGroup);
      base = group ? group.cases : allCases;
    }
    const keyword = search.trim().toLowerCase();
    return base.filter((item) => {
      if (priorityFilter && item.priority !== priorityFilter) return false;
      if (!keyword) return true;
      const haystack = [
        item.name,
        item.metadata?.case_id ?? "",
        ...(item.metadata?.requirements ?? []),
        ...(item.metadata?.risks ?? []),
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(keyword);
    });
  }, [allCases, selectedGroup, flatGroups, priorityFilter, search]);

  const questions = doc.unresolved_questions ?? [];
  const uncovered = coverage.entries.filter((e) => e.coveredBy.length === 0);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* 统计条 + 筛选 */}
      <div className="shrink-0 border-b px-4 py-2.5">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs">
          <span className="flex items-center gap-1.5 font-medium">
            <ListTree className="h-3.5 w-3.5" />
            共 {allCases.length} 条用例 · {flatGroups.length} 个分组
          </span>
          <span className="flex items-center gap-1">
            {PRIORITY_ORDER.map((p) =>
              priorityCounts[p] ? (
                <Badge
                  key={p}
                  variant="outline"
                  className={`h-5 px-1.5 text-[10px] ${PRIORITY_BADGE[p]}`}
                >
                  {PRIORITY_LABEL[p]} × {priorityCounts[p]}
                </Badge>
              ) : null,
            )}
          </span>
          {coverage.total > 0 && (
            <span
              className={`flex items-center gap-1 ${uncovered.length > 0 ? "text-warning" : "text-emerald-600 dark:text-emerald-400"}`}
            >
              {uncovered.length > 0 ? (
                <CircleAlert className="h-3.5 w-3.5" />
              ) : (
                <CircleCheck className="h-3.5 w-3.5" />
              )}
              需求覆盖 {coverage.covered}/{coverage.total}
              {uncovered.length > 0 ? `（${uncovered.length} 条未覆盖）` : ""}
            </span>
          )}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            onClick={() => setPriorityFilter(null)}
            className={`rounded-full border px-2 py-0.5 text-[11px] transition-colors ${
              priorityFilter === null
                ? "bg-accent"
                : "text-muted-foreground hover:bg-accent/50"
            }`}
          >
            全部优先级
          </button>
          {PRIORITY_ORDER.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setPriorityFilter(priorityFilter === p ? null : p)}
              className={`rounded-full border px-2 py-0.5 text-[11px] transition-colors ${
                priorityFilter === p
                  ? PRIORITY_BADGE[p]
                  : "text-muted-foreground hover:bg-accent/50"
              }`}
            >
              {PRIORITY_LABEL[p]}
            </button>
          ))}
          <div className="relative ml-auto">
            <Search className="absolute top-1/2 left-2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索用例标题 / CASE / REQ"
              className="h-7 w-56 pl-7 text-xs"
            />
          </div>
        </div>
      </div>

      {/* 待确认问题：只读展示，答案回聊天 */}
      {questions.length > 0 && (
        <div className="shrink-0 border-b bg-warning/5 px-4 py-2">
          <button
            type="button"
            onClick={() => setShowQuestions(!showQuestions)}
            className="flex w-full items-center gap-1.5 text-left text-xs font-medium text-warning"
          >
            {showQuestions ? (
              <ChevronDown className="h-3.5 w-3.5" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5" />
            )}
            {questions.length} 个待确认问题（点击展开查看）
          </button>
          {showQuestions && (
            <div className="mt-2 space-y-1.5">
              <p className="m-0 flex items-center gap-1 text-[11px] text-muted-foreground">
                <MessageSquareQuote className="h-3 w-3" />
                这些问题请回到聊天中逐条回复智能体解答，页面不作答；答案更新后会生成新版本并重新检查。
              </p>
              <ol className="m-0 list-decimal space-y-1 pl-5 text-xs">
                {questions.map((q, index) => (
                  <li key={index} className="text-foreground/85">
                    {normalizeQuestion(q)}
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        {/* 模块树 */}
        <div className="w-56 shrink-0 overflow-y-auto border-r py-2">
          <button
            type="button"
            onClick={() => setSelectedGroup(null)}
            className={`w-full px-3 py-1.5 text-left text-xs font-medium transition-colors ${
              selectedGroup === null ? "bg-accent" : "hover:bg-accent/50"
            }`}
          >
            全部用例（{allCases.length}）
          </button>
          {flatGroups.map((group) => (
            <button
              key={group.key}
              type="button"
              onClick={() => setSelectedGroup(group.key)}
              className={`w-full truncate px-3 py-1.5 text-left text-xs transition-colors ${
                selectedGroup === group.key
                  ? "bg-accent font-medium"
                  : "text-muted-foreground hover:bg-accent/50"
              }`}
              style={{ paddingLeft: `${12 + group.depth * 14}px` }}
              title={group.name}
            >
              {group.name}
              <span className="ml-1 text-[10px] text-muted-foreground">
                （{group.cases.length}）
              </span>
            </button>
          ))}
        </div>

        {/* 用例卡片流 */}
        <div className="min-w-0 flex-1 overflow-y-auto p-3">
          {visibleCases.length === 0 ? (
            <p className="mt-8 text-center text-xs text-muted-foreground">
              没有符合条件的用例
            </p>
          ) : (
            <div className="space-y-2.5">
              {visibleCases.map((item, index) => (
                <CaseCard key={item.metadata?.case_id ?? index} item={item} />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 需求覆盖明细（折叠） */}
      {coverage.total > 0 && (
        <div className="max-h-56 shrink-0 overflow-y-auto border-t px-4 py-2">
          <button
            type="button"
            onClick={() => setShowCoverage(!showCoverage)}
            className="flex w-full items-center gap-1.5 text-left text-xs font-medium"
          >
            {showCoverage ? (
              <ChevronDown className="h-3.5 w-3.5" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5" />
            )}
            需求覆盖明细（{coverage.covered}/{coverage.total}）
          </button>
          {showCoverage && (
            <ul className="m-0 mt-1.5 list-none space-y-1 p-0">
              {coverage.entries.map((entry) => (
                <li key={entry.id} className="flex items-start gap-2 text-xs">
                  {entry.coveredBy.length > 0 ? (
                    <CircleCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
                  ) : (
                    <CircleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
                  )}
                  <span className="font-mono text-[11px]">{entry.id}</span>
                  <span className="min-w-0 flex-1 truncate text-muted-foreground" title={entry.summary}>
                    {entry.summary || "（无摘要）"}
                  </span>
                  <span className="shrink-0 text-[10px] text-muted-foreground">
                    {entry.coveredBy.length > 0
                      ? `${entry.coveredBy.length} 条用例`
                      : "未覆盖"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
