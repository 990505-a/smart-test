"use client";

// SWR hooks for Markdown case documents and their workflow gates.

import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { mutate } from "swr";
import { apiClient } from "@/lib/api-client";

export type LifecycleStatus =
  | "draft"
  | "needs_clarification"
  | "generated"
  | "in_review"
  | "changes_requested"
  | "approved"
  | "released";

export type LintStatus = "not_run" | "passed" | "failed";
export type ReviewStatus = "not_run" | "passed" | "failed";

export interface LintDiagnostic {
  code: string;
  line?: number;
  severity: "error" | "warning";
  message: string;
}

export interface ReviewIssue {
  severity: "blocker" | "high" | "medium" | "low";
  code: string;
  case_id?: string | null;
  requirement_id?: string | null;
  evidence?: string;
  recommendation?: string;
}

export interface ReviewReport {
  verdict?: string;
  summary?: string;
  issues?: ReviewIssue[];
}

export interface WorkflowMeta {
  revision: number;
  content_hash: string;
  lifecycle_status: LifecycleStatus;
  lint_status: LintStatus;
  review_status: ReviewStatus;
  lint_report?: {
    ok: boolean;
    errors: LintDiagnostic[];
    warnings: LintDiagnostic[];
    stats?: Record<string, number>;
    content_hash?: string;
  } | null;
  review_report?: ReviewReport | null;
  review_round?: number;
  unresolved_questions?: UnresolvedQuestion[];
  assumptions?: unknown[];
  requirements?: RequirementEntry[];
  coverage_plan?: unknown[];
}

export interface UnresolvedQuestion {
  question?: string;
  severity?: string;
  blocking?: boolean;
  requirement_id?: string;
  [key: string]: unknown;
}

export interface RequirementEntry {
  id?: string;
  summary?: string;
  risk?: string;
  [key: string]: unknown;
}

export interface CaseStep {
  action: string;
  expected?: string | null;
  mark?: string;
  children?: CaseStep[];
}

export interface CaseItem {
  name: string;
  priority: string;
  preconditions?: string | null;
  steps: CaseStep[];
  metadata?: {
    case_id: string | null;
    requirements: string[];
    risks: string[];
  } | null;
}

export interface CaseGroup {
  name: string;
  children: CaseGroup[];
  cases: CaseItem[];
}

export interface CaseDocParsed {
  title: string;
  tree: CaseGroup[];
  case_count: number;
}

export interface CaseDocInfo extends WorkflowMeta {
  name: string;
  title: string;
  size: number;
  updated_at: number;
  case_count: number;
  good: number;
  bad: number;
  warn: number;
  annotated: boolean;
}

export interface CaseDoc extends WorkflowMeta {
  name: string;
  content: string;
  updated_at: number;
  parsed?: CaseDocParsed;
}

export interface WorkflowActionArgs {
  expected_revision?: number;
  expected_hash?: string;
  reason?: string;
}

const fetcher = <T,>(path: string) => apiClient.get<T>(path).then((r) => r.data);

export function useCaseDocs() {
  return useSWR<CaseDocInfo[]>("/case-docs", fetcher);
}

export function useCaseDoc(name: string | null) {
  return useSWR<CaseDoc>(
    name ? `/case-docs/${encodeURIComponent(name)}` : null,
    fetcher,
  );
}

export function useSaveCaseDoc() {
  return useSWRMutation(
    "/case-docs",
    async (
      url: string,
      { arg }: {
        arg: {
          name: string;
          content: string;
          expected_revision?: number;
          expected_hash?: string;
          workflow_mode?: boolean;
        };
      },
    ) => {
      const result = await apiClient.put<CaseDocInfo>(
        `${url}/${encodeURIComponent(arg.name)}`,
        {
          content: arg.content,
          expected_revision: arg.expected_revision,
          expected_hash: arg.expected_hash,
          workflow_mode: arg.workflow_mode ?? false,
        },
      );
      revalidateCaseDocs();
      return result;
    },
  );
}

export function useDeleteCaseDoc() {
  return useSWRMutation(
    "/case-docs",
    async (url: string, { arg }: { arg: string }) => {
      const result = await apiClient.delete(`${url}/${encodeURIComponent(arg)}`);
      revalidateCaseDocs();
      return result;
    },
  );
}

export function useSaveRequirementPackage() {
  return useSWRMutation(
    "/case-docs",
    async (
      url: string,
      { arg }: { arg: { name: string; package: Record<string, unknown>; expected_revision?: number } },
    ) => {
      const result = await apiClient.post<WorkflowMeta>(
        `${url}/${encodeURIComponent(arg.name)}/requirement-package`,
        {
          package: arg.package,
          expected_revision: arg.expected_revision,
        },
      );
      revalidateCaseDocs();
      return result;
    },
  );
}

function useWorkflowAction(path: string) {
  return useSWRMutation(
    "/case-docs",
    async (
      url: string,
      { arg }: { arg: { name: string } & WorkflowActionArgs },
    ) => {
      const result = await apiClient.post<WorkflowMeta>(
        `${url}/${encodeURIComponent(arg.name)}/${path}`,
        {
          expected_revision: arg.expected_revision,
          expected_hash: arg.expected_hash,
          reason: arg.reason,
        },
      );
      revalidateCaseDocs();
      return result;
    },
  );
}

export function useLintCaseDoc() {
  return useWorkflowAction("lint");
}

export function useReviewCaseDoc() {
  return useWorkflowAction("review");
}

export function useRequestCaseDocChanges() {
  return useWorkflowAction("request-changes");
}

export function useApproveCaseDoc() {
  return useWorkflowAction("approve");
}

export function useReleaseCaseDoc() {
  return useWorkflowAction("release");
}

export function revalidateCaseDocs() {
  mutate((key) => typeof key === "string" && key.startsWith("/case-docs"));
}
