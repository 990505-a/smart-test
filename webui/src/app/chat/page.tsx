"use client";

import React, { useState, useEffect, useCallback, useMemo, useRef, Suspense } from "react";
import { useQueryState } from "nuqs";
import { getConfig, saveConfig, StandaloneConfig } from "@/lib/config";
import { Button } from "@/components/ui/button";
import { ClientProvider } from "@/providers/ClientProvider";
import { ChatProvider } from "@/providers/ChatProvider";
import { Settings, SquarePen, MessagesSquare } from "lucide-react";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { AGENT_CONFIG, AgentKey } from "@/app/types/types";
import { WORKSPACES, WorkspaceId } from "@/app/types/types";
import { AgentTabs } from "@/app/components/AgentTabs";
import { WorkspaceSelect } from "@/app/components/WorkspaceSelect";
import { ChatInterface } from "@/app/components/ChatInterface";
import { ThreadList } from "@/app/components/ThreadList";
import { ConfigDialog } from "@/app/components/ConfigDialog";
import { Header } from "@/app/components/Header";
import { Assistant } from "@langchain/langgraph-sdk";

// ---------------------------------------------------------------------------
// HomePageInner -- the main layout with header, tabs, and resizable panels
// ---------------------------------------------------------------------------
function HomePageInner({
  config,
  configDialogOpen,
  setConfigDialogOpen,
  handleSaveConfig,
}: {
  config: StandaloneConfig;
  configDialogOpen: boolean;
  setConfigDialogOpen: (open: boolean) => void;
  handleSaveConfig: (config: StandaloneConfig) => void;
}) {
  const [threadId, setThreadId] = useQueryState("threadId");
  const [sidebar, setSidebar] = useQueryState("sidebar");
  const [activeAgent, setActiveAgent] = useQueryState("agent", {
    defaultValue: "testcase",
  });

  // Workspace state: persisted to localStorage via config
  const [currentWorkspace, setCurrentWorkspace] = useState<WorkspaceId>(
    (config?.workspaceId as WorkspaceId) || "default",
  );

  const handleWorkspaceChange = useCallback(
    (id: WorkspaceId) => {
      setCurrentWorkspace(id);
      setThreadId(null); // Prevent cross-workspace data leakage
      const currentConfig = getConfig();
      if (currentConfig) {
        saveConfig({ ...currentConfig, workspaceId: id });
      }
    },
    [setThreadId],
  );

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

  const handleThreadSelect = useCallback(
    (id: string) => {
      setThreadId(id);
    },
    [setThreadId],
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

  return (
    <>
      <ConfigDialog
        open={configDialogOpen}
        onOpenChange={setConfigDialogOpen}
        onSave={handleSaveConfig}
        initialConfig={config}
      />
      <div className="flex h-screen flex-col">
        {/* Header */}
        <Header>
          {!sidebar && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setSidebar("1")}
              className="rounded-md border bg-card text-foreground hover:bg-accent"
            >
              <MessagesSquare className="mr-2 h-4 w-4" />
              对话列表
            </Button>
          )}
          <AgentTabs
            activeAgent={activeAgent ?? "testcase"}
            onAgentChange={handleAgentChange}
          />
          <WorkspaceSelect
            workspaceId={currentWorkspace}
            onWorkspaceChange={handleWorkspaceChange}
          />
          <span className="text-xs text-muted-foreground">
            助手: {assistantId}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setConfigDialogOpen(true)}
          >
            <Settings className="mr-2 h-4 w-4" />
            设置
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleNewChat}
            disabled={!threadId}
            className="border-primary bg-primary text-primary-foreground hover:bg-primary/80"
          >
            <SquarePen className="mr-2 h-4 w-4" />
            新建对话
          </Button>
        </Header>

        {/* Main content area with resizable panels */}
        <div className="flex-1 overflow-hidden">
          <ResizablePanelGroup orientation="horizontal" id="smart-test-platform">
            {sidebar && (
              <>
                <ResizablePanel
                  id="thread-history"
                  defaultSize={25}
                  minSize={20}
                  className="min-w-[300px]"
                >
                  <ThreadList
                    onThreadSelect={handleThreadSelect}
                    onMutateReady={handleMutateReady}
                    onClose={() => setSidebar(null)}
                  />
                </ResizablePanel>
                <ResizableHandle />
              </>
            )}

            <ResizablePanel
              id="chat"
              className="relative flex flex-col"
            >
              <ChatProvider
                activeAssistant={activeAssistant}
                onHistoryRevalidate={handleHistoryRevalidate}
                workspaceId={currentWorkspace}
              >
                <ChatInterface assistantId={assistantId} />
              </ChatProvider>
            </ResizablePanel>
          </ResizablePanelGroup>
        </div>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// HomePageContent -- loads config, wraps in ClientProvider
// ---------------------------------------------------------------------------
function HomePageContent() {
  const [config, setConfig] = useState<StandaloneConfig | null>(null);
  const [configDialogOpen, setConfigDialogOpen] = useState(false);

  // On mount, check for saved config, otherwise show config dialog
  useEffect(() => {
    const savedConfig = getConfig();
    if (savedConfig) {
      setConfig(savedConfig);
    } else {
      setConfigDialogOpen(true);
    }
  }, []);

  const handleSaveConfig = useCallback((newConfig: StandaloneConfig) => {
    saveConfig(newConfig);
    setConfig(newConfig);
  }, []);

  const langsmithApiKey =
    config?.langsmithApiKey || process.env.NEXT_PUBLIC_LANGSMITH_API_KEY || "";

  if (!config) {
    return (
      <>
        <ConfigDialog
          open={configDialogOpen}
          onOpenChange={setConfigDialogOpen}
          onSave={handleSaveConfig}
        />
        <div className="flex h-screen items-center justify-center">
          <div className="text-center">
            <h1 className="text-2xl font-bold">欢迎使用智能测试平台</h1>
            <p className="mt-2 text-muted-foreground">
              请配置您的部署以开始使用
            </p>
            <Button onClick={() => setConfigDialogOpen(true)} className="mt-4">
              打开配置
            </Button>
          </div>
        </div>
      </>
    );
  }

  return (
    <ClientProvider
      deploymentUrl={config.deploymentUrl}
      apiKey={langsmithApiKey}
    >
      <HomePageInner
        config={config}
        configDialogOpen={configDialogOpen}
        setConfigDialogOpen={setConfigDialogOpen}
        handleSaveConfig={handleSaveConfig}
      />
    </ClientProvider>
  );
}

// ---------------------------------------------------------------------------
// ChatPage -- Suspense wrapper (required by nuqs)
// ---------------------------------------------------------------------------
export default function ChatPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-screen items-center justify-center">
          <p className="text-muted-foreground">加载中...</p>
        </div>
      }
    >
      <HomePageContent />
    </Suspense>
  );
}
