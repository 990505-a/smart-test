"use client";

import { use } from "react";
import { ManagementLayout } from "@/app/components/ManagementLayout";
import { MarkdownContent } from "@/app/components/MarkdownContent";
import { useReportContent } from "@/lib/api/useReports";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function ReportDetailPage({
  params,
}: {
  params: Promise<{ session: string; filename: string }>;
}) {
  const { session, filename } = use(params);
  const decodedSession = decodeURIComponent(session);
  const decodedFilename = decodeURIComponent(filename);
  const { data, isLoading, error } = useReportContent(decodedSession, decodedFilename);

  return (
    <ManagementLayout>
      <div className="space-y-4">
        <div className="flex items-center gap-4">
          <Link href="/test-reports">
            <Button variant="ghost" size="sm">
              <ArrowLeft className="h-4 w-4 mr-1" />
              返回列表
            </Button>
          </Link>
          <div>
            <h2 className="text-xl font-bold">{decodedFilename}</h2>
            <span className="text-sm text-muted-foreground">{decodedSession}</span>
          </div>
        </div>

        {isLoading ? (
          <div className="py-8 text-center text-muted-foreground">加载中...</div>
        ) : error ? (
          <div className="py-8 text-center text-destructive">
            加载失败: {error.message}
          </div>
        ) : (
          <MarkdownContent content={data?.data?.content ?? ""} />
        )}
      </div>
    </ManagementLayout>
  );
}
