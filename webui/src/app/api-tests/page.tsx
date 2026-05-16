"use client";

import { useState, useCallback } from "react";
import { ManagementLayout } from "@/app/components/ManagementLayout";
import { ApiTestList } from "./components/ApiTestList";
import { ApiTestDetail } from "./components/ApiTestDetail";
import type { APITestInfo } from "@/app/types/api";

export default function ApiTestsPage() {
  const [selectedTest, setSelectedTest] = useState<APITestInfo | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const handleSelectTest = useCallback((test: APITestInfo) => {
    setSelectedTest(test);
  }, []);

  const handleBack = useCallback(() => {
    setSelectedTest(null);
    setRefreshKey((k) => k + 1);
  }, []);

  return (
    <ManagementLayout>
      {selectedTest ? (
        <ApiTestDetail
          key={selectedTest.id}
          test={selectedTest}
          onBack={handleBack}
        />
      ) : (
        <ApiTestList
          key={refreshKey}
          onSelectTest={handleSelectTest}
        />
      )}
    </ManagementLayout>
  );
}
