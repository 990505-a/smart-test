"use client";

import { ManagementLayout } from "@/app/components/ManagementLayout";
import { useReportSessions } from "@/lib/api/useReports";
import Link from "next/link";
import { FileText, FolderOpen } from "lucide-react";

export default function TestReportsPage() {
  const { data, isLoading, error } = useReportSessions();

  return (
    <ManagementLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold">测试报告</h1>
          <p className="text-sm text-muted-foreground">浏览 Agent 生成的测试报告文件</p>
        </div>

        {isLoading ? (
          <div className="py-8 text-center text-muted-foreground">加载中...</div>
        ) : error ? (
          <div className="py-8 text-center text-destructive">
            加载失败: {error.message}
          </div>
        ) : !data?.data?.length ? (
          <div className="py-8 text-center text-muted-foreground">暂无测试报告</div>
        ) : (
          <div className="space-y-6">
            {data.data.map((session) => (
              <div key={session.name} className="border rounded-lg p-4">
                <div className="flex items-center gap-3 mb-3">
                  <FolderOpen className="h-5 w-5 text-muted-foreground" />
                  <h2 className="text-lg font-semibold">{session.name}</h2>
                  <span className="text-xs bg-muted px-2 py-1 rounded">
                    {session.file_count} 个文件
                  </span>
                </div>
                <div className="space-y-1">
                  {session.files.map((file) => (
                    <Link
                      key={file}
                      href={`/test-reports/${encodeURIComponent(session.name)}/${encodeURIComponent(file)}`}
                      className="flex items-center gap-2 text-sm hover:text-primary transition-colors py-1"
                    >
                      <FileText className="h-4 w-4 text-muted-foreground" />
                      {file}
                    </Link>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </ManagementLayout>
  );
}
