"use client";

import { useState, useCallback } from "react";
import { ManagementLayout } from "@/app/components/ManagementLayout";
import { ScenarioList } from "./components/ScenarioList";
import { ScenarioEditor } from "./components/ScenarioEditor";
import type { ScenarioInfo } from "@/app/types/api";

export default function ScenariosPage() {
  const [selectedScenario, setSelectedScenario] = useState<ScenarioInfo | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const handleSelect = useCallback((scenario: ScenarioInfo) => {
    setSelectedScenario(scenario);
  }, []);

  const handleBack = useCallback(() => {
    setSelectedScenario(null);
    setRefreshKey((k) => k + 1);
  }, []);

  return (
    <ManagementLayout>
      {selectedScenario ? (
        <ScenarioEditor
          key={selectedScenario.id}
          scenario={selectedScenario}
          onBack={handleBack}
        />
      ) : (
        <ScenarioList
          key={refreshKey}
          onSelect={handleSelect}
        />
      )}
    </ManagementLayout>
  );
}
