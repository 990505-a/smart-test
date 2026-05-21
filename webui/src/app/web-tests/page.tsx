"use client";

import { useState, useCallback } from "react";
import { ManagementLayout } from "@/app/components/ManagementLayout";
import { WebFunctionList } from "./components/WebFunctionList";
import { WebTestList } from "./components/WebTestList";
import { CreateFunctionDialog } from "./components/CreateFunctionDialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Search } from "lucide-react";
import { useWebFunctions } from "@/lib/api/useWebFunctions";
import { useProjects } from "@/lib/api/useProjects";

export default function WebTestsPage() {
  // Get projectId from the first project (same pattern as api-tests page)
  const { data: projectsData } = useProjects(1, 100);
  const projects = projectsData?.data ?? [];
  const projectId = projects[0]?.id ?? null;

  // Function list state
  const [page, setPage] = useState(1);
  const pageSize = 30;
  const [search, setSearch] = useState("");
  const [selectedFunctionId, setSelectedFunctionId] = useState<string | null>(null);
  const [selectedSubFunctionId, setSelectedSubFunctionId] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  // Fetch web functions
  const { data: functionsData, error: functionsError, isLoading: isLoadingFunctions, mutate } = useWebFunctions(
    projectId,
    page,
    pageSize,
    search || undefined,
  );

  const functions = functionsData?.data ?? [];

  const handleFunctionSelect = useCallback(
    (functionId: string | null, subFunctionId?: string | null) => {
      setSelectedFunctionId(functionId);
      setSelectedSubFunctionId(subFunctionId ?? null);
    },
    [],
  );

  const handleCreateSuccess = useCallback(() => {
    mutate();
    setRefreshKey((k) => k + 1);
  }, [mutate]);

  return (
    <ManagementLayout>
      <div className="flex flex-col gap-4 h-full">
        {/* Header */}
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold">Web测试</h2>
          {projectId && (
            <CreateFunctionDialog
              projectId={projectId}
              onSuccess={handleCreateSuccess}
            />
          )}
        </div>

        {/* Main content: two-panel layout */}
        {!projectId ? (
          <div className="flex items-center justify-center py-16">
            <Skeleton className="h-8 w-48" />
          </div>
        ) : (
          <div className="flex gap-6 flex-1 min-h-0">
            {/* Left panel: Function tree */}
            <div className="w-[400px] flex-shrink-0 flex flex-col gap-3">
              {/* Search */}
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="搜索功能名称..."
                  value={search}
                  onChange={(e) => {
                    setSearch(e.target.value);
                    setPage(1);
                  }}
                  className="pl-9"
                />
              </div>

              {/* Function list */}
              <div className="flex-1 overflow-auto">
                {isLoadingFunctions ? (
                  <div className="space-y-2">
                    {Array.from({ length: 4 }).map((_, i) => (
                      <Skeleton key={i} className="h-24 w-full" />
                    ))}
                  </div>
                ) : functionsError ? (
                  <div className="flex flex-col items-center justify-center gap-2 py-8">
                    <p className="text-destructive">加载功能列表失败</p>
                    <button
                      className="text-sm text-primary hover:underline"
                      onClick={() => mutate()}
                    >
                      重试
                    </button>
                  </div>
                ) : (
                  <WebFunctionList
                    functions={functions}
                    projectId={projectId}
                    onFunctionSelect={handleFunctionSelect}
                    selectedFunctionId={selectedFunctionId}
                    isLoading={isLoadingFunctions}
                  />
                )}
              </div>

              {/* Pagination */}
              {functionsData?.info && functionsData.info.total > pageSize && (
                <div className="flex items-center justify-end gap-2 pt-2">
                  <button
                    className="text-sm text-primary hover:underline disabled:text-muted-foreground"
                    disabled={!functionsData.info.prev || page <= 1}
                    onClick={() => setPage(page - 1)}
                  >
                    上一页
                  </button>
                  <span className="text-sm text-muted-foreground">
                    {functionsData.info.page}/{Math.ceil(functionsData.info.total / functionsData.info.page_size)}
                  </span>
                  <button
                    className="text-sm text-primary hover:underline disabled:text-muted-foreground"
                    disabled={!functionsData.info.next}
                    onClick={() => setPage(page + 1)}
                  >
                    下一页
                  </button>
                </div>
              )}
            </div>

            {/* Right panel: Web tests for selected function */}
            <div className="flex-1 min-h-0 overflow-auto">
              <WebTestList
                projectId={projectId}
                functionId={selectedFunctionId}
                subFunctionId={selectedSubFunctionId}
              />
            </div>
          </div>
        )}
      </div>
    </ManagementLayout>
  );
}
