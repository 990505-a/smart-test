"use client";

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AGENT_CONFIG, type AgentKey } from "@/app/types/types";
import { Bug, CodeXml, Gamepad2 } from "lucide-react";

const AGENT_ICONS: Record<AgentKey, React.ComponentType<{ className?: string }>> = {
  testcase: Bug,
  unity: Gamepad2,
  codeanalyst: CodeXml,
};

export function AgentTabs({
  activeAgent,
  onAgentChange,
}: {
  activeAgent: string;
  onAgentChange: (value: string) => void;
}) {
  return (
    <Tabs value={activeAgent} onValueChange={onAgentChange}>
      <TabsList>
        {(Object.entries(AGENT_CONFIG) as [AgentKey, (typeof AGENT_CONFIG)[AgentKey]][]).map(
          ([key, cfg]) => {
            const Icon = AGENT_ICONS[key];
            return (
              <TabsTrigger key={key} value={key} className="gap-2">
                <Icon className="h-4 w-4" />
                {cfg.label}
              </TabsTrigger>
            );
          },
        )}
      </TabsList>
    </Tabs>
  );
}
