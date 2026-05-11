"use client";

import React, { useState, useEffect, useCallback, Suspense } from "react";
import { useQueryState } from "nuqs";
import { getConfig, saveConfig, StandaloneConfig } from "@/lib/config";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ClientProvider } from "@/providers/ClientProvider";
import { Settings, SquarePen, Sun, Moon, MessagesSquare } from "lucide-react";
import { useTheme } from "next-themes";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { AGENT_CONFIG, AgentKey } from "@/app/types/types";

// ---------------------------------------------------------------------------
// ConfigDialog – lets the user set deploymentUrl / assistantId
// ---------------------------------------------------------------------------
function ConfigDialog({
  open,
  onOpenChange,
  onSave,
  initialConfig,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (config: StandaloneConfig) => void;
  initialConfig?: StandaloneConfig | null;
}) {
  const [deploymentUrl, setDeploymentUrl] = useState(
    initialConfig?.deploymentUrl ?? ""
  );
  const [assistantId, setAssistantId] = useState(
    initialConfig?.assistantId ?? ""
  );
  const [langsmithApiKey, setLangsmithApiKey] = useState(
    initialConfig?.langsmithApiKey ?? ""
  );

  useEffect(() => {
    if (open && initialConfig) {
      setDeploymentUrl(initialConfig.deploymentUrl ?? "");
      setAssistantId(initialConfig.assistantId ?? "");
      setLangsmithApiKey(initialConfig.langsmithApiKey ?? "");
    }
  }, [open, initialConfig]);

  const handleSave = () => {
    if (!deploymentUrl.trim() || !assistantId.trim()) return;
    onSave({
      deploymentUrl: deploymentUrl.trim(),
      assistantId: assistantId.trim(),
      langsmithApiKey: langsmithApiKey.trim() || undefined,
    });
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>平台配置</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid grid-cols-4 items-center gap-4">
            <label className="text-right text-sm col-span-1">部署地址</label>
            <Input
              className="col-span-3"
              placeholder="http://localhost:2026"
              value={deploymentUrl}
              onChange={(e) => setDeploymentUrl(e.target.value)}
            />
          </div>
          <div className="grid grid-cols-4 items-center gap-4">
            <label className="text-right text-sm col-span-1">助手ID</label>
            <Input
              className="col-span-3"
              placeholder="testcase_agent"
              value={assistantId}
              onChange={(e) => setAssistantId(e.target.value)}
            />
          </div>
          <div className="grid grid-cols-4 items-center gap-4">
            <label className="text-right text-sm col-span-1">API Key</label>
            <Input
              className="col-span-3"
              placeholder="可选"
              value={langsmithApiKey}
              onChange={(e) => setLangsmithApiKey(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button onClick={handleSave}>保存</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// ThemeToggle – switches between light and dark mode
// ---------------------------------------------------------------------------
function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
    >
      <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
      <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
    </Button>
  );
}

// ---------------------------------------------------------------------------
// HomePageInner – the main layout with header, tabs, and resizable panels
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

  const handleAgentChange = (value: string) => {
    setActiveAgent(value);
    setThreadId(null); // Clear thread on agent switch to prevent state leakage
  };

  const currentConfig = AGENT_CONFIG[activeAgent as AgentKey];
  const assistantId = currentConfig?.graphKey ?? "testcase_agent";

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
        <header className="flex h-14 items-center justify-between border-b px-4">
          <div className="flex items-center gap-4">
            <h1 className="text-lg font-semibold">智能测试平台</h1>
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
          </div>

          {/* Agent tabs */}
          <Tabs value={activeAgent ?? "testcase"} onValueChange={handleAgentChange}>
            <TabsList>
              <TabsTrigger value="testcase">{AGENT_CONFIG.testcase.label}</TabsTrigger>
              <TabsTrigger value="web">{AGENT_CONFIG.web.label}</TabsTrigger>
              <TabsTrigger value="api">{AGENT_CONFIG.api.label}</TabsTrigger>
            </TabsList>
          </Tabs>

          {/* Right actions */}
          <div className="flex items-center gap-2">
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
              onClick={() => setThreadId(null)}
              disabled={!threadId}
              className="border-primary bg-primary text-primary-foreground hover:bg-primary/80"
            >
              <SquarePen className="mr-2 h-4 w-4" />
              新建对话
            </Button>
            <ThemeToggle />
          </div>
        </header>

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
                  {/* ThreadList placeholder - will be implemented in Plan 03 */}
                  <div className="flex h-full flex-col items-center justify-center border-r p-4">
                    <p className="text-sm text-muted-foreground">
                      对话列表 (待实现)
                    </p>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="mt-2"
                      onClick={() => setSidebar(null)}
                    >
                      关闭侧栏
                    </Button>
                  </div>
                </ResizablePanel>
                <ResizableHandle />
              </>
            )}

            <ResizablePanel
              id="chat"
              className="relative flex flex-col"
            >
              {/* ChatInterface placeholder - will be implemented in Plan 03 */}
              <div className="flex h-full flex-col items-center justify-center p-4">
                <p className="text-lg font-medium">智能测试平台</p>
                <p className="mt-2 text-sm text-muted-foreground">
                  当前助手: {currentConfig?.label ?? "用例生成"}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  聊天界面将在后续计划中实现
                </p>
              </div>
            </ResizablePanel>
          </ResizablePanelGroup>
        </div>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// HomePageContent – loads config, wraps in ClientProvider
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
// HomePage – Suspense wrapper (required by nuqs)
// ---------------------------------------------------------------------------
export default function HomePage() {
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
