"use client";

import React, { useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { ChevronDown, ChevronUp } from "lucide-react";
import type { SubAgent } from "@/app/types/types";
import { extractSubAgentContent } from "@/app/types/types";
import { MarkdownContent } from "@/app/components/MarkdownContent";

interface SubAgentIndicatorProps {
  subAgent: SubAgent;
}

export const SubAgentIndicator = React.memo<SubAgentIndicatorProps>(
  ({ subAgent }) => {
    const [isExpanded, setIsExpanded] = useState(true);

    const toggleExpanded = useCallback(() => {
      setIsExpanded((prev) => !prev);
    }, []);

    return (
      <div className="w-full overflow-hidden rounded-lg border-none bg-card shadow-none outline-none">
        <Button
          variant="ghost"
          size="sm"
          onClick={toggleExpanded}
          className="flex w-full items-center justify-between gap-2 border-none px-4 py-2 text-left shadow-none outline-none transition-colors duration-200"
        >
          <div className="flex items-center gap-2">
            <span className="text-[15px] font-bold leading-[140%] tracking-[-0.6px] text-foreground">
              {subAgent.subAgentName}
            </span>
          </div>
          {isExpanded ? (
            <ChevronUp size={14} className="shrink-0 text-muted-foreground" />
          ) : (
            <ChevronDown size={14} className="shrink-0 text-muted-foreground" />
          )}
        </Button>

        {isExpanded && (
          <div className="w-full max-w-full px-4 pb-3">
            <div className="rounded-md border border-border p-4">
              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                输入
              </h4>
              <div className="mb-4">
                <MarkdownContent content={extractSubAgentContent(subAgent.input)} />
              </div>
              {subAgent.output && (
                <>
                  <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    输出
                  </h4>
                  <MarkdownContent content={extractSubAgentContent(subAgent.output)} />
                </>
              )}
            </div>
          </div>
        )}
      </div>
    );
  },
);

SubAgentIndicator.displayName = "SubAgentIndicator";
