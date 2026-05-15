"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { useTestCase, useUpdateTestCase } from "@/lib/api/useTestCases";
import { CaseDetailForm } from "./components/CaseDetailForm";
import type { TestCaseUpdate } from "@/app/types/api";

export default function CaseDetailPage() {
  const params = useParams();
  const caseId = params.id as string;

  const { data: response, error, isLoading } = useTestCase(caseId);
  const { trigger: updateCase, isMutating: isSaving } = useUpdateTestCase();
  const testCase = response?.data;

  const handleSave = async (data: TestCaseUpdate) => {
    await updateCase({ id: caseId, data });
  };

  if (isLoading) {
    return (
      <div className="flex h-screen flex-col">
        <div className="border-b px-4 py-2">
          <Skeleton className="h-5 w-40" />
        </div>
        <div className="flex-1 overflow-auto p-6 space-y-4">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      </div>
    );
  }

  if (error || !testCase) {
    return (
      <div className="flex h-screen flex-col">
        <div className="border-b px-4 py-2">
          <Button variant="ghost" size="sm" render={<Link href="/cases" />}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              返回用例列表
          </Button>
        </div>
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <p className="text-destructive">加载失败</p>
            <p className="mt-2 text-sm text-muted-foreground">{error?.message || "未找到该用例"}</p>
            <Button variant="outline" className="mt-4" render={<Link href="/cases" />}>
              返回用例列表
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col">
      {/* Breadcrumb header */}
      <div className="border-b px-4 py-2">
        <div className="flex items-center justify-between">
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem>
                <BreadcrumbLink render={<Link href="/cases" />}>
                  测试用例
                </BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage>{testCase.identifier || "..."}</BreadcrumbPage>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
          <span className="text-sm text-muted-foreground">
            版本 {testCase.version}
          </span>
        </div>
      </div>

      {/* Editor content */}
      <div className="flex-1 overflow-auto p-6">
        <div className="mx-auto max-w-3xl">
          <CaseDetailForm
            testCase={testCase}
            onSave={handleSave}
            isSaving={isSaving}
          />
        </div>
      </div>
    </div>
  );
}
