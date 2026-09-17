"use client";

import React, { useState, useEffect, useCallback, useMemo, useRef, Suspense } from "react";
import { useQueryState, parseAsString } from "nuqs";
import { getConfig, getDeploymentUrl, StandaloneConfig } from "@/lib/config";
import { Button } from "@/components/ui/button";
import { ClientProvider } from "@/providers/ClientProvider";
import { ChatProvider } from "@/providers/ChatProvider";
import { SquarePen, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { AGENT_CONFIG, AgentKey } from "@/app/types/types";
import { ChatInterface } from "@/app/components/ChatInterface";
import { ThreadList } from "@/app/components/ThreadList";
import { Assistant } from "@langchain/langgraph-sdk";

// ---------------------------------------------------------------------------
// HomePageInner — slim top bar + resizable [threads | chat] panels.
// Global navigation lives in the AppShell rail; this header only carries
// chat-scoped controls.
// ---------------------------------------------------------------------------
function HomePageInner() {
  const [, setThreadId] = useQueryState("threadId");
  // "1" (default) shows the session list, "0" hides it.
  const [sidebar, setSidebar] = useQueryState("sidebar", parseAsString.withDefault("1"));
  const [activeAgent, setActiveAgent] = useQueryState("agent", {
    defaultValue: "testcase",
  });

  // Thread list mutation callback
  const mutateThreadsRef = useRef<(() => void) | null>(null);

  const handleMutateReady = useCallback((mutate: () => void) => {
    mutateThreadsRef.current = mutate;
  }, []);

  const handleHistoryRevalidate = useCallback(() => {
    mutateThreadsRef.current?.();
  }, []);

  const handleAgentChange = (value: string) => {
    setActiveAgent(value);
    setThreadId(null); // Clear thread on agent switch to prevent state leakage
  };

  // 点开会话时把模式切回这条会话自己的 agent（dsh：会话记着自己的模式）。
  // 旧会话（agent 为空）保持当前模式不动。
  const handleThreadSelect = useCallback(
    (id: string, threadAgent?: string) => {
      const match = threadAgent
        ? (Object.keys(AGENT_CONFIG) as AgentKey[]).find(
            (key) => AGENT_CONFIG[key].graphKey === threadAgent,
          )
        : undefined;
      if (match && match !== activeAgent) {
        setActiveAgent(match);
      }
      setThreadId(id);
    },
    [setThreadId, setActiveAgent, activeAgent],
  );

  const handleNewChat = useCallback(() => {
    setThreadId(null);
  }, [setThreadId]);

  // Construct activeAssistant from agent config
  const currentConfig = AGENT_CONFIG[activeAgent as AgentKey];
  const assistantId = currentConfig?.graphKey ?? "testcase_agent";

  const activeAssistant = useMemo<Assistant>(
    () => ({
      assistant_id: assistantId,
      graph_id: assistantId,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      metadata: {},
      config: {},
      version: 1,
      name: currentConfig?.label ?? "TestCase",
      context: {},
    }),
    [assistantId, currentConfig?.label],
  );

  const threadsVisible = sidebar !== "0";

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Slim chat header：左：侧边栏开关；中：当前模式名（只读提示，切换在输入框旁）；
          右：新对话。模式选择移进输入区了——它属于"这次对话的配置"，不是导航。 */}
      <div className="flex h-12 shrink-0 items-center justify-between gap-3 border-b bg-background px-4">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setSidebar(threadsVisible ? "0" : "1")}
          title={threadsVisible ? "隐藏对话列表" : "显示对话列表"}
          className="shrink-0"
        >
          {threadsVisible ? (
            <PanelLeftClose className="h-4 w-4" />
          ) : (
            <PanelLeftOpen className="h-4 w-4" />
          )}
        </Button>
        <div className="flex min-w-0 flex-1 items-center justify-center gap-2 text-sm">
          <span className="truncate text-muted-foreground">
            {currentConfig?.label ?? "用例生成"}
          </span>
          <span className="hidden font-mono text-[11px] text-muted-foreground/60 sm:inline">
            {assistantId}
          </span>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={handleNewChat}
          className="shrink-0"
        >
          <SquarePen className="h-4 w-4" />
          <span className="ml-1.5">新对话</span>
        </Button>
      </div>

        {/* Main content area with resizable panels */}
        <div className="min-h-0 flex-1">
          <ResizablePanelGroup orientation="horizontal" id="smart-test-platform">
            {threadsVisible && (
              <>
                <ResizablePanel
                  id="thread-history"
                  defaultSize="22%"
                  minSize="18%"
                  maxSize="35%"
                  className="relative z-20 overflow-hidden bg-background"
                >
                  <ThreadList
                    onThreadSelect={handleThreadSelect}
                    onMutateReady={handleMutateReady}
                  />
                </ResizablePanel>
                <ResizableHandle />
              </>
            )}

            <ResizablePanel
              id="chat"
              className="relative flex flex-col overflow-hidden"
            >
              <ChatProvider
                activeAssistant={activeAssistant}
                onHistoryRevalidate={handleHistoryRevalidate}
                workspaceId="default"
              >
                <ChatInterface
                  assistantId={assistantId}
                  activeAgent={activeAgent ?? "testcase"}
                  onAgentChange={handleAgentChange}
                />
              </ChatProvider>
            </ResizablePanel>
          </ResizablePanelGroup>
        </div>
      </div>
  );
}

// ---------------------------------------------------------------------------
// HomePageContent — resolves optional address overrides, wraps ClientProvider
// ---------------------------------------------------------------------------
function HomePageContent() {
  const [config, setConfig] = useState<StandaloneConfig | null>(null);

  // Log unhandled promise rejections for debugging
  useEffect(() => {
    const handler = (e: PromiseRejectionEvent) => {
      console.error("[ChatPage] Unhandled rejection:", e.reason?.message || e.reason, e.reason?.stack);
    };
    window.addEventListener("unhandledrejection", handler);
    return () => window.removeEventListener("unhandledrejection", handler);
  }, []);

  // Resolve localStorage overrides once after mount (avoids SSR/localStorage
  // hydration mismatch); defaults are used when nothing is stored.
  useEffect(() => {
    setConfig(getConfig() ?? {});
  }, []);

  if (!config) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-muted-foreground">加载中…</p>
      </div>
    );
  }

  return (
    <ClientProvider deploymentUrl={getDeploymentUrl()}>
      <HomePageInner />
    </ClientProvider>
  );
}

// ---------------------------------------------------------------------------
// ChatPage — Suspense wrapper (required by nuqs)
// ---------------------------------------------------------------------------
export default function ChatPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-full items-center justify-center">
          <p className="text-sm text-muted-foreground">加载中…</p>
        </div>
      }
    >
      <HomePageContent />
    </Suspense>
  );
}
