"use client";

import React, { useState, useEffect, useCallback, useMemo, useRef, Suspense } from "react";
import { useQueryState, parseAsString } from "nuqs";
import { getDeploymentUrl } from "@/lib/config";
import { Button } from "@/components/ui/button";
import { ClientProvider } from "@/providers/ClientProvider";
import { ChatProvider } from "@/providers/ChatProvider";
import { SquarePen, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { AGENT_CONFIG, DEFAULT_AGENT_KEY, agentKeyForGraph, AgentKey } from "@/app/types/types";
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
  // 智能体（graph）选择：新会话恒为通用智能体；只有点开历史会话时才会变成它当初
  // 记录的旧单能力 graph（否则老会话没法续跑）。用户不再手动切换模式。
  const [activeAgent, setActiveAgent] = useQueryState("agent", {
    defaultValue: DEFAULT_AGENT_KEY,
  });

  // Thread list mutation callback
  const mutateThreadsRef = useRef<(() => void) | null>(null);

  const handleMutateReady = useCallback((mutate: () => void) => {
    mutateThreadsRef.current = mutate;
  }, []);

  const handleHistoryRevalidate = useCallback(() => {
    mutateThreadsRef.current?.();
  }, []);

  // 点开会话时把模式切回这条会话自己的 agent：历史会话记着旧的单能力 graph，
  // 要回到它才能续跑；新会话（无记录或记录为通用智能体）一律走通用智能体。
  const handleThreadSelect = useCallback(
    (id: string, threadAgent?: string) => {
      const match = agentKeyForGraph(threadAgent);
      if (match && match !== activeAgent) {
        setActiveAgent(match);
      }
      setThreadId(id);
    },
    [setThreadId, setActiveAgent, activeAgent],
  );

  const handleNewChat = useCallback(() => {
    setThreadId(null);
    // 新对话回到通用智能体 —— 否则旧会话的模式会一直粘着
    setActiveAgent(DEFAULT_AGENT_KEY);
  }, [setThreadId, setActiveAgent]);

  // Construct activeAssistant from agent config
  const currentConfig = AGENT_CONFIG[activeAgent as AgentKey] ?? AGENT_CONFIG[DEFAULT_AGENT_KEY];
  const assistantId = currentConfig.graphKey;

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
      {/* Slim chat header：左：侧边栏开关；中：当前智能体名（只读）；
          右：新对话。没有模式选择器 —— 对话页只有一个通用智能体。 */}
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
            {currentConfig?.label ?? "通用测试助手"}
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
                  activeAgent={activeAgent ?? DEFAULT_AGENT_KEY}
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
  const [mounted, setMounted] = useState(false);

  // Log unhandled promise rejections for debugging
  useEffect(() => {
    const handler = (e: PromiseRejectionEvent) => {
      console.error("[ChatPage] Unhandled rejection:", e.reason?.message || e.reason, e.reason?.stack);
    };
    window.addEventListener("unhandledrejection", handler);
    return () => window.removeEventListener("unhandledrejection", handler);
  }, []);

  // 挂载后再渲染：服务地址解析依赖 window（回环 → 直连端口，公网 → 同源子路径），
  // SSR 首帧拿不到，提前渲染会造成 hydration 不匹配。
  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
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
