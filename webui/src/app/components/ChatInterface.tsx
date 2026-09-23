"use client";

import React, { useState, useRef, useCallback, useEffect, useMemo, Fragment, FormEvent } from "react";
import { Virtuoso } from "react-virtuoso";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ArrowUp, Square, Plus, CheckCircle, Clock, Circle, ChevronUp, FlaskConical, Brain, ShieldAlert, FolderGit2, Bot, Cpu, Loader, Gauge } from "lucide-react";
import useSWR from "swr";
import { useCbmRepos, useModelPresets, useModelSettings } from "@/lib/api/useNewModules";
import { apiClient } from "@/lib/api-client";
import { ChatMessage } from "@/app/components/ChatMessage";
import { ApprovalCard } from "@/app/components/ApprovalCard";
import { useChatContext } from "@/providers/ChatProvider";
import { cn } from "@/lib/utils";
import { useQueryState } from "nuqs";
import { toast } from "sonner";
import { formatTokenCount, pickLatestContextUsage } from "@/lib/formatTokens";
import { countRunSteps, progressFingerprint, runHud } from "@/lib/runProgress";

import { useFileUpload } from "@/app/hooks/useFileUpload";
import { useTodos } from "@/app/hooks/useTodos";
import { ContentBlocksPreview } from "@/app/components/ContentBlocksPreview";
import { UploadProgressList } from "@/app/components/UploadProgress";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { ToolCall, TodoItem, SubAgent } from "@/app/types/types";
import type { Message } from "@langchain/langgraph-sdk";
import { SubAgentPanel } from "@/app/components/SubAgentPanel";
import { useProcessedMessages } from "@/app/hooks/useProcessedMessages";

interface ChatInterfaceProps {
  assistantId: string;
  /** 当前会话的智能体键（只读）：新会话恒为 general，历史会话是它当初的旧模式 */
  activeAgent: string;
}

const getStatusIcon = (status: TodoItem["status"], className?: string) => {
  switch (status) {
    case "completed":
      return <CheckCircle size={16} className={cn("text-green-500", className)} />;
    case "in_progress":
      return <Clock size={16} className={cn("text-yellow-500", className)} />;
    default:
      return <Circle size={16} className={cn("text-muted-foreground/70", className)} />;
  }
};

export const ChatInterface = React.memo<ChatInterfaceProps>(({
  assistantId,
  activeAgent,
}) => {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const [input, setInput] = useState("");
  const [metaOpen, setMetaOpen] = useState<"tasks" | null>(null);

  // Scroll container ref for auto-scroll
  const scrollContainerRef = useRef<HTMLElement | null>(null);

  // Read threadId from URL — 线程懒创建：首条消息/首次文件上传时才有 id
  const [currentThreadId] = useQueryState("threadId");
  // Reasoning effort chip state (?effort=off|low|medium|high); defaults to high
  const [reasoningEffort, setReasoningEffort] = useQueryState("effort", {
    defaultValue: "high",
  });
  // execute 审批档位（?permission=workspace_write|full_access）。
  // read_only 已移除：用例工作流必须落盘，只读档等于关闭流程；旧链接回落工作区档。
  const [permissionMode, setPermissionMode] = useQueryState("permission", {
    defaultValue: "workspace_write",
  });
  // 本次对话挂载哪个仓库（?repo=<受管仓库 id>，空 = 不挂载）。
  // 挂上之后：该仓库的绝对路径成为工作目录（cwd + 相对路径解析基准），
  // 代码分析的图谱工具才进工具面（后端按 configurable.workspace_path 判断）。
  // 仓库列表就是「代码图谱」页注册的那些 —— 没注册的仓库照样能让智能体 grep
  // 绝对路径，只是没有图谱能力（见 codebase 能力段提示词）。
  const [repoId, setRepoId] = useQueryState("repo", { defaultValue: "" });
  const { data: repoData } = useCbmRepos();
  const repos = useMemo(() => repoData?.repos ?? [], [repoData]);
  const selectedRepo = useMemo(
    () => repos.find((r) => r.id === repoId) ?? null,
    [repos, repoId],
  );
  // 用哪个智能体（?agentId=<装配目录里的智能体>，空 = 平台默认智能体）。
  // 装配目录在「智能体装配」页编辑：每个智能体有自己的一套能力/工具/技能/审批。
  // 不设「默认」这一项：默认智能体（general = 通用测试助手）本来就在候选列表里，
  // 后端 active_agent_id() 在缺省时也是解析到它 —— 两个选项指的是同一个智能体。
  const [agentKey, setAgentKey] = useQueryState("agentId", { defaultValue: "" });
  const { data: catalog } = useSWR<{ agents: { id: string; label: string }[]; default_agent_id?: string }>(
    "/agents", () => apiClient.get<{ agents: { id: string; label: string }[]; default_agent_id?: string }>("/agents").then((r) => r.data));
  const pickableAgents = useMemo(() => catalog?.agents ?? [], [catalog]);
  const selectedAgent = useMemo(
    () => pickableAgents.find((a) => a.id === agentKey) ?? null,
    [pickableAgents, agentKey],
  );
  // 本次实际生效的智能体：没选、或选了个已被删掉的，就落到默认智能体。
  // 默认是哪个由后端说了算（`default_agent_id`），前端只做与 Catalog.default_agent()
  // 一致的兜底（默认那个被删了就取第一个），否则「界面显示的」和「后端真正用的」
  // 会在这种边界上分叉。
  const effectiveAgent = useMemo(() => {
    if (selectedAgent) return selectedAgent;
    return pickableAgents.find((a) => a.id === catalog?.default_agent_id)
      ?? pickableAgents[0]
      ?? null;
  }, [selectedAgent, pickableAgents, catalog]);
  // 本次对话用哪个模型（?model=<模型预设名>，空 = 跟随设置页的全局模型）。
  // 候选就是设置页存的那些预设（各自一套 模型名+端点+Key），所以能跨供应商切换。
  const [modelPreset, setModelPreset] = useQueryState("model", { defaultValue: "" });
  const { data: presetList } = useModelPresets();
  const modelPresets = useMemo(() => presetList ?? [], [presetList]);
  const selectedPreset = useMemo(
    () => modelPresets.find((p) => p.name === modelPreset) ?? null,
    [modelPresets, modelPreset],
  );
  useEffect(() => {
    if (permissionMode === "read_only") setPermissionMode("workspace_write");
  }, [permissionMode, setPermissionMode]);
  // 切到完全访问需要二次确认（dsh: RiskConfirmation）
  const [fullAccessConfirmOpen, setFullAccessConfirmOpen] = useState(false);

  // === 会话级设置持久化 ===
  // 选择器以前只活在 URL 参数里：重启 / 从别的页面回来 / 换台机器，点开
  // 会话就全部回落默认（"设置了完全访问再切回来又没了"）。现在变化后防抖
  // PATCH 到 thread_infos.config，切换会话时由 chat 页统一恢复。
  // 刚切进一个会话的那次触发不回写（那时值是恢复值/默认值，不是用户改动），
  // 否则会把旧会话的设置误写进新会话。
  const persistedConfigRef = useRef<{ threadId: string; serialized: string } | null>(null);
  useEffect(() => {
    if (!currentThreadId) return;
    const config = {
      permission_mode: permissionMode,
      llm_reasoning_effort: reasoningEffort,
      model_preset: modelPreset,
      agent_id: agentKey,
      repo_id: repoId,
    };
    const serialized = JSON.stringify(config);
    const persisted = persistedConfigRef.current;
    if (!persisted || persisted.threadId !== currentThreadId) {
      // 首次见到这个会话：记住当前快照作为基线，不回写
      persistedConfigRef.current = { threadId: currentThreadId, serialized };
      return;
    }
    if (persisted.serialized === serialized) return;
    const timer = window.setTimeout(() => {
      persistedConfigRef.current = { threadId: currentThreadId, serialized };
      apiClient
        .patch(`/threads/${currentThreadId}`, { config })
        .catch(() => {/* 持久化失败不打扰：URL 参数里仍有当前值，下次变化重试 */});
    }, 600);
    return () => window.clearTimeout(timer);
  }, [currentThreadId, permissionMode, reasoningEffort, modelPreset, agentKey, repoId]);
  // 飞书检索开关已移除（2026-09）：它默认就该开着，摆个开关只会让人忘了开。
  // 智能体现在默认被允许用 lark-cli 只读检索飞书需求（写操作仍走审批门）。

  // 需在 useFileUpload 之前解构：ensureThreadId 传给上传 hook 按需建线程
  const {
    messages,
    isLoading,
    sendMessage,
    stopStream,
    interrupt,
    resumeInterrupt,
    ensureThreadId,
    isLoadingHistory,
    hasOlderMessages,
    loadOlderMessages,
    historyError,
    threadId,
    getSubAgentFeed,
    isSubAgentTaskClosed,
    subagentVersion,
  } = useChatContext();

  const {
    contentBlocks,
    uploads,
    isUploading,
    handleFileUpload,
    dropRef,
    removeContentBlock,
    clearContentBlocks,
    isDragging,
    handlePaste,
  } = useFileUpload(undefined, currentThreadId ?? undefined, ensureThreadId);

  // 任务清单：从消息里的 write_todos 工具调用派生（见 hooks/useTodos.ts）。
  // 原先是从 chat context 读一个恒为空的数组，面板因此永不渲染。
  const todos = useTodos(messages);

  // 子智能体实时操作面板（右侧抽屉）
  const [activitySubAgent, setActivitySubAgent] = useState<SubAgent | null>(null);
  const handleSubAgentActivity = useCallback((sa: SubAgent) => {
    setActivitySubAgent(sa);
  }, []);

  useEffect(() => {
    setActivitySubAgent(null);
  }, [currentThreadId, assistantId]);

  const submitDisabled = isLoading || !assistantId;
  // 审批等待期间不允许并发发消息（dsh：审批接管输入区）
  const approvalPending = !!interrupt;
  // 列表末尾的「生成中」指示器：只由 run 是否活跃驱动（isLoading 即
  // isCurrentThreadLoading），不看"最近有没有新 token"——模型思考、长工具
  // 调用期间一个 token 都不来，按文本到达驱动会误判成卡死，而这正是要解决的
  // 场景。审批挂起时 run 停在等用户决策（不是在干活），不能继续转。
  const showGenerating = isLoading && !approvalPending;

  // 运行状态条：这一轮跑了多久、第几步、还在不在动。
  //
  // 为什么需要它：这一轮跑到哪儿以前界面上没有任何地方说得清，于是"跑很久"只能靠
  // 一个**模型调用次数上限**（120 次就硬收尾）来兜——那个闸误伤长探索，收尾还只留
  // 一句英文报错。现在改成看得见 + 随时能停：计时 + 步数 + 静默 90s 提示。
  const [hudNow, setHudNow] = useState(() => Date.now());
  const runStartedAtRef = useRef<number | null>(null);
  const lastProgressAtRef = useRef<number>(Date.now());
  // 指纹只在"真的多了一条消息 / 文本又长了 / 多了一个工具调用"时才变 —— 用它判断
  // 还在不在动，比"最近有没有 token"准（模型思考与长工具调用期间本来就没有 token）。
  const progressKey = useMemo(
    () => progressFingerprint(messages ?? []),
    [messages],
  );
  useEffect(() => {
    if (isLoading) {
      if (runStartedAtRef.current === null) {
        runStartedAtRef.current = Date.now();
        lastProgressAtRef.current = Date.now();
      }
      return;
    }
    runStartedAtRef.current = null;
  }, [isLoading]);
  useEffect(() => {
    lastProgressAtRef.current = Date.now();
  }, [progressKey]);
  useEffect(() => {
    if (!isLoading) return;
    const timer = window.setInterval(() => setHudNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [isLoading]);
  const hud = useMemo(() => {
    if (!isLoading || runStartedAtRef.current === null) return null;
    return runHud({
      elapsedMs: hudNow - runStartedAtRef.current,
      silentMs: hudNow - lastProgressAtRef.current,
      steps: countRunSteps(messages ?? []),
    });
  }, [isLoading, hudNow, messages, progressKey]);

  const handleSubmit = useCallback(
    (e?: FormEvent) => {
      if (e) {
        e.preventDefault();
      }
      const messageText = input.trim();
      if (
        (!messageText && contentBlocks.length === 0) ||
        isLoading ||
        submitDisabled ||
        approvalPending
      )
        return;
      // Files still converting/uploading — sending now would drop them.
      if (isUploading) {
        toast.error("文件还在上传中，请等待上传完成后再发送");
        return;
      }
      // 挂了仓库就把它的绝对路径交给 agent（configurable.workspace_path）：
      // 后端据此把 cwd 指到该仓库，并按挂载与否决定图谱工具出不出现。
      // 没挂载则一律走平台默认工作区（后端 resolve_workspace_dir 的兜底）。
      isNearBottomRef.current = true;
      sendMessage(messageText, contentBlocks, {
        workspacePath: selectedRepo?.repo_path,
        // 传实际生效的那个：触发器显示谁就发谁，避免"看到通用、实际走默认"这种
        // 只在边界上（目录被改过）才暴露的不一致。目录没加载出来时仍留空，
        // 交给后端按默认智能体解析。
        agentId: effectiveAgent?.id,
        // 会话级配置持久化需要仓库 id（URL 上的 ?repo=），useChat 落库用
        repoId,
      });
      setInput("");
      clearContentBlocks();
    },
    [input, contentBlocks, isLoading, isUploading, approvalPending, sendMessage, submitDisabled, clearContentBlocks, selectedRepo, effectiveAgent, repoId],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (submitDisabled) return;
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit, submitDisabled],
  );

  // Extract tool calls from messages (shared with the codebase analysis panel)
  const processedMessages = useProcessedMessages(messages, isLoading, subagentVersion);

  // 当前上下文占用：取**最后一次模型调用**的 total_tokens。它的 input 就是
  // 本轮发给模型的完整对话（含全部历史），total ≈ 当前上下文真实水位。
  // 旧实现把各条 AI 回复的 total_tokens 累加——每轮 input 都重发全部历史，
  // 长会话会虚高出数倍（实测 460 万），刷新/切会话后数值"乱跳"即此因。
  const latestUsage = useMemo(
    () => pickLatestContextUsage(messages ?? []),
    [messages],
  );
  const sessionTokens = latestUsage?.used ?? 0;

  // 占上下文窗口的百分比：分母是设置页的「上下文窗口」（与后端
  // SummarizationMiddleware 的 85% 压缩触发点同一个口径）。设置页与就绪
  // 中心读的是同一个 SWR key，这里不会再多打一次请求。
  const { data: modelSettings } = useModelSettings();
  const contextWindow = useMemo(() => {
    const parsed = parseInt(String(modelSettings?.llm_context_window ?? ""), 10);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 128_000;
  }, [modelSettings]);
  const sessionTokenPct =
    contextWindow > 0 ? Math.round((sessionTokens / contextWindow) * 1000) / 10 : 0;

  // 跟随设置时的实际模型名（模型选择器直接显示它，而不是笼统的「默认」）
  const defaultModelName = String(modelSettings?.llm_model ?? "").trim();


  // 面板显示的子智能体实时化：点击传入的是当时的快照（status/output 停在
  // 点击那一刻），这里从当前消息流重建，状态与最终输出随流更新
  const liveSubAgent = useMemo(() => {
    if (!activitySubAgent) return null;
    for (const { toolCalls } of processedMessages) {
      const tc = toolCalls.find((t) => t.id === activitySubAgent.id && t.name === "task");
      if (tc) {
        return {
          id: tc.id,
          name: tc.name,
          subAgentName: String(tc.args?.subagent_type ?? ""),
          input: tc.args,
          output: tc.result ? { result: tc.result } : undefined,
          status:
            tc.status === "completed" || isSubAgentTaskClosed(tc.id)
              ? ("completed" as const)
              : tc.status === "error"
                ? ("error" as const)
                : ("active" as const),
        };
      }
    }
    return activitySubAgent;
  }, [activitySubAgent, processedMessages, isSubAgentTaskClosed, subagentVersion]);

  // Grouped todos for display
  const groupedTodos = useMemo(() => ({
    in_progress: todos.filter((t) => t.status === "in_progress"),
    pending: todos.filter((t) => t.status === "pending"),
    completed: todos.filter((t) => t.status === "completed"),
  }), [todos]);

  const hasTasks = todos.length > 0;

  // Auto-scroll to bottom on new messages — ONLY when the user is already
  // near the bottom. Streaming in background (subagent/tool results) must
  // never yank the viewport while the user is reading older messages.
  const lastMessageId = messages?.at(-1)?.id;
  const isNearBottomRef = useRef(true);

  useEffect(() => {
    const el = scrollContainerRef.current;
    // 新会话从底部开始跟随（Virtuoso initialTopMostItemIndex 已定位到底部）
    isNearBottomRef.current = true;
    if (!el) return;
    const onScroll = () => {
      isNearBottomRef.current =
        el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
    // Re-attach when the Virtuoso scroller mounts/unmounts (list empty ↔ non-empty)
  }, [processedMessages.length > 0, currentThreadId]);

  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el || !isNearBottomRef.current) return;
    const frameId = window.requestAnimationFrame(() => {
      el.scrollTo({
        top: el.scrollHeight,
        behavior: "auto",
      });
    });
    return () => window.cancelAnimationFrame(frameId);
  }, [lastMessageId, messages?.length]);

  // Virtualization: when older pages are prepended (loading history), tell
  // Virtuoso via firstItemIndex so it keeps the viewport anchored instead of
  // jumping. Detected by the oldest message id changing with a length gain.
  const [firstItemIndex, setFirstItemIndex] = useState(1_000_000);
  const prevListRef = useRef<{ oldest?: string; len: number }>({ len: 0 });
  useEffect(() => {
    const oldest = processedMessages[0]?.message.id;
    const prev = prevListRef.current;
    if (
      prev.oldest &&
      oldest &&
      oldest !== prev.oldest &&
      processedMessages.length > prev.len
    ) {
      setFirstItemIndex((v) => Math.max(1, v - (processedMessages.length - prev.len)));
    }
    prevListRef.current = { oldest, len: processedMessages.length };
  }, [processedMessages]);

  const renderItem = useCallback(
    (index: number, data: { message: Message; toolCalls: ToolCall[] }) => {
      const isLastMessage = index === processedMessages.length - 1;
      // min-h: an empty streaming placeholder (no content/tool_calls yet)
      // otherwise measures 0px, which react-virtuoso warns about.
      return (
        <div className="mx-auto min-h-[1px] w-full max-w-[1024px] px-6">
          <ChatMessage
            message={data.message}
            toolCalls={data.toolCalls}
            isStreaming={isLastMessage && isLoading}
            onSubAgentActivity={handleSubAgentActivity}
            isSubAgentClosed={isSubAgentTaskClosed}
          />
        </div>
      );
    },
    [processedMessages.length, isLoading, assistantId, handleSubAgentActivity, isSubAgentTaskClosed],
  );

  const ListHeader = useMemo(
    () =>
      function VirtuosoListHeader() {
        return hasOlderMessages ? (
          <div className="mb-4 flex justify-center pt-4">
            <Button
              variant="ghost"
              size="sm"
              onClick={loadOlderMessages}
              disabled={isLoadingHistory}
              className="text-xs text-muted-foreground"
            >
              {isLoadingHistory ? "加载中..." : "加载更早的消息"}
              {!isLoadingHistory && <ChevronUp size={14} className="ml-1" />}
            </Button>
          </div>
        ) : (
          <div className="pt-4" />
        );
      },
    [hasOlderMessages, loadOlderMessages, isLoadingHistory],
  );

  /**
   * 「生成中」指示器：挂在 Virtuoso 的 Footer 上——位于最后一条消息之下、
   * 列表流之内，不裹进任何消息气泡。图标是 lucide 的 Loader（8 道辐条，
   * 与参考图的经典 spinner 一致）。
   * 组件身份用 useMemo 钉住：给 Footer 传一个新的函数=新的组件类型，React 会
   * 卸载重挂，CSS 动画被重置回第一帧；流式期间每 50ms 一次重渲染，spinner
   * 看起来就是卡死不动。身份只在显示/隐藏切换时变一次，正好配动画生命周期。
   */
  const ListFooter = useMemo(
    () =>
      function VirtuosoListFooter() {
        if (!showGenerating) return null;
        return (
          <div className="mx-auto w-full max-w-[1024px] px-6 pb-4 pt-1">
            {/* 左对齐（与 assistant 消息同一起始边），不用居中/右对齐 */}
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader className="h-4 w-4 animate-spin" />
              <span>生成中</span>
            </div>
          </div>
        );
      },
    [showGenerating],
  );

  const virtuosoComponents = useMemo(
    () => ({ Header: ListHeader, Footer: ListFooter }),
    [ListHeader, ListFooter],
  );

  return (
    // 行布局：主列（消息+输入）+ 右侧子智能体面板并排，互不遮挡；
    // 面板未打开时主列占满
    <div className="relative flex min-h-0 flex-1 overflow-hidden">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      {/* Message list area (virtualized: long threads render only the
          visible window instead of keeping every message in the DOM) */}
      {processedMessages.length > 0 ? (
        <Virtuoso
          data={processedMessages}
          scrollerRef={(ref) => {
            scrollContainerRef.current =
              ref instanceof HTMLElement ? ref : null;
          }}
          computeItemKey={(_, item) => item.message.id ?? `item-${_}`}
          firstItemIndex={firstItemIndex}
          initialTopMostItemIndex={Math.max(0, processedMessages.length - 1)}
          itemContent={renderItem}
          components={virtuosoComponents}
          className="flex-1 overflow-y-auto overflow-x-hidden overscroll-contain"
        />
      ) : historyError && threadId ? (
        <div className="flex-1 flex flex-col items-center justify-center p-8">
          <p className="text-lg font-medium text-destructive">
            无法加载会话消息
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            该会话状态过大，暂时无法加载。请尝试新建对话。
          </p>
        </div>
      ) : (
        <div className="flex flex-1 flex-col items-center justify-center p-8">
          <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-[14px] bg-primary text-primary-foreground">
            <FlaskConical className="h-5 w-5" />
          </div>
          <p className="text-lg font-medium leading-8">
            开始你的测试任务
          </p>
          <p className="mt-1.5 max-w-md text-center text-[13px] leading-6 text-muted-foreground">
            上传需求文档生成测试用例、分析代码仓库，或直接描述你的测试问题
          </p>
        </div>
      )}

      {/* Input area */}
      <div className="flex-shrink-0 bg-background">
        <div
          ref={dropRef}
          className={cn(
            "mx-4 mb-6 flex flex-shrink-0 flex-col overflow-hidden rounded-[22px] border border-border bg-background",
            "mx-auto w-[calc(100%-32px)] max-w-[1024px] transition-colors duration-200 ease-[cubic-bezier(0.4,0,0.2,1)]",
            "surface-float",
            isDragging && "border-2 border-dotted border-brand",
          )}
        >
          {/* 任务进度条（模型用 write_todos 列的计划） */}
          {hasTasks && (
            <div className="flex max-h-72 flex-col overflow-y-auto border-b border-border bg-muted empty:hidden">
              {!metaOpen && (
                <div className="grid grid-cols-[1fr_auto_auto] items-center">
                  {hasTasks && (() => {
                    const activeTask = todos.find((t) => t.status === "in_progress");
                    const totalTasks = todos.length;
                    const completedCount = groupedTodos.completed.length + groupedTodos.in_progress.length;
                    const isCompleted = totalTasks === completedCount;

                    return (
                      <button
                        type="button"
                        onClick={() => setMetaOpen((prev) => prev === "tasks" ? null : "tasks")}
                        className="grid w-full cursor-pointer grid-cols-[auto_auto_1fr] items-center gap-3 px-[18px] py-3 text-left"
                        aria-expanded={metaOpen === "tasks"}
                      >
                        {isCompleted ? (
                          <>
                            <CheckCircle size={16} className="text-green-500" />
                            <span className="ml-[1px] min-w-0 truncate text-sm">所有任务已完成</span>
                          </>
                        ) : activeTask ? (
                          <>
                            {getStatusIcon(activeTask.status)}
                            <span className="ml-[1px] min-w-0 truncate text-sm">
                              任务 {completedCount} / {totalTasks}
                            </span>
                            <span className="min-w-0 gap-2 truncate text-sm text-muted-foreground">
                              {activeTask.content}
                            </span>
                          </>
                        ) : (
                          <>
                            <Circle size={16} className="text-muted-foreground/70" />
                            <span className="ml-[1px] min-w-0 truncate text-sm">
                              任务 {completedCount} / {totalTasks}
                            </span>
                          </>
                        )}
                      </button>
                    );
                  })()}
                </div>
              )}

              {metaOpen && (
                <div className="px-[18px] pb-3">
                  {metaOpen === "tasks" && (
                    Object.entries(groupedTodos)
                      .filter(([, items]) => items.length > 0)
                      .map(([status, items]) => (
                        <div key={status} className="mb-3">
                          <h3 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                            {{ pending: "待处理", in_progress: "进行中", completed: "已完成" }[status]}
                          </h3>
                          <div className="grid grid-cols-[auto_1fr] gap-3 rounded-sm p-1 pl-0 text-sm">
                            {items.map((todo, idx) => (
                              <Fragment key={`${status}_${todo.id}_${idx}`}>
                                {getStatusIcon(todo.status, "mt-0.5")}
                                <span className="break-words">{todo.content}</span>
                              </Fragment>
                            ))}
                          </div>
                        </div>
                      ))
                  )}
                  <button
                    type="button"
                    className="mt-2 text-xs text-muted-foreground hover:text-foreground"
                    onClick={() => setMetaOpen(null)}
                  >
                    收起
                  </button>
                </div>
              )}
            </div>
          )}

          <form onSubmit={handleSubmit} className="flex flex-col">
            {/* 审批卡片：越权操作等待用户决策（dsh 式接管输入区） */}
            {interrupt && (
              <ApprovalCard
                interrupt={interrupt}
                onDecide={resumeInterrupt}
                className="mx-3 mt-3"
              />
            )}
            <UploadProgressList uploads={uploads} />
            <ContentBlocksPreview
              blocks={contentBlocks}
              onRemove={removeContentBlock}
            />
            {hud && (
              <div
                className={cn(
                  "flex flex-wrap items-center gap-2 border-b border-border px-4 py-1.5 text-xs",
                  hud.stalled ? "text-warning" : "text-muted-foreground",
                )}
                title={"这一轮的进度。长时间没有新事件时会在这里说出来 —— 平台不再按"
                  + "「模型调用次数上限」硬收尾，跑多久由你看着决定（右上停止按钮随时可用）。"}
              >
                <span
                  className={cn(
                    "size-1.5 shrink-0 rounded-full",
                    hud.stalled ? "bg-warning" : "animate-pulse bg-success",
                  )}
                />
                <span>{hud.text}</span>
                {hud.hint && <span className="text-muted-foreground">{hud.hint}</span>}
              </div>
            )}
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              onPaste={handlePaste}
              placeholder={isLoading ? "运行中..." : "输入您的消息..."}
              className="flex-1 resize-none border-0 bg-transparent px-[18px] pb-[13px] pt-[14px] text-sm leading-7 text-foreground outline-none placeholder:text-muted-foreground"
              rows={1}
            />
            <div className="flex flex-wrap items-center justify-between gap-2 p-3">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                <label
                  htmlFor="file-input"
                  className="flex shrink-0 cursor-pointer items-center gap-2 whitespace-nowrap text-muted-foreground hover:text-foreground"
                >
                  <Plus className="size-5" />
                  <span className="text-sm">上传 PDF 或图片</span>
                </label>
                <input
                  id="file-input"
                  type="file"
                  onChange={handleFileUpload}
                  multiple
                  accept="image/jpeg,image/png,image/gif,image/webp,application/pdf,text/markdown"
                  className="hidden"
                />
                <div className="flex flex-wrap items-center gap-2 border-l border-border pl-4">
                  {/* 模式选择器已移除：对话页只有一个通用智能体，专项能力全挂在
                      它的工具面上，由它自己判断该用哪一类。装配清单见「智能体装配」页。
                      历史会话（旧的单能力 graph）仍按自己的 graph 续跑，顶部只读显示。 */}
                  {/* Reasoning effort chip (per conversation, ?effort=) */}
                  <div className="flex shrink-0 items-center gap-1">
                    <Brain size={14} className="text-muted-foreground" />
                    <Select
                      value={reasoningEffort === "" ? null : reasoningEffort}
                      onValueChange={(v) => setReasoningEffort(v ?? "")}
                    >
                      <SelectTrigger
                        size="sm"
                        className="h-7 gap-1 border border-border bg-transparent px-1.5 text-xs text-foreground"
                        title="思考强度（需要模型支持 reasoning_effort）"
                      >
                        <SelectValue placeholder="思考：关">
                          {{"": "思考：关", low: "思考：低", medium: "思考：中",
                            high: "思考：高"}[reasoningEffort] ?? "思考：关"}
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="">思考：关</SelectItem>
                        <SelectItem value="low">思考：低</SelectItem>
                        <SelectItem value="medium">思考：中</SelectItem>
                        <SelectItem value="high">思考：高</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  {/* 权限档位（per conversation, ?permission=）—— 受限/完全访问。
                      文案说清"免审批区"到底是什么：平台自己的工作目录
                      （workspace/default/…），不是某个用户挂载的仓库。 */}
                  <div className="flex shrink-0 items-center gap-1 border-l border-border pl-4">
                    <ShieldAlert
                      size={14}
                      className={cn(
                        "text-muted-foreground",
                        permissionMode === "full_access" && "text-destructive",
                      )}
                    />
                    <Select
                      value={permissionMode}
                      onValueChange={(v) => {
                        if (v === "full_access" && permissionMode !== "full_access") {
                          setFullAccessConfirmOpen(true);
                          return;
                        }
                        setPermissionMode(v ?? "workspace_write");
                      }}
                    >
                      <SelectTrigger
                        size="sm"
                        className="h-7 gap-1 border border-border bg-transparent px-1.5 text-xs text-foreground"
                        title="权限档位：受限=写入限于平台工作目录、只读命令白名单自动放行、其余命令与越界写入需审批；完全访问=全部放行"
                      >
                        <SelectValue placeholder="受限">
                          {permissionMode === "full_access" ? "完全访问" : "受限"}
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="workspace_write">受限（越界需审批）</SelectItem>
                        <SelectItem value="full_access">完全访问</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  {/* 智能体（per conversation, ?agentId=）—— 用装配目录里的哪一个。
                      每个智能体有自己的一套能力/工具/技能/审批，见「智能体装配」页。
                      候选就是目录本身，没有额外的「默认」项：缺省时生效的就是列表里的
                      默认智能体，触发器直接把它的名字显示出来。 */}
                  <div className="flex shrink-0 items-center gap-1 border-l border-border pl-4">
                    <Bot size={14} className="text-muted-foreground" />
                    <Select value={effectiveAgent?.id ?? ""} onValueChange={(v) => setAgentKey(v ?? "")}>
                      <SelectTrigger
                        size="sm"
                        className="h-7 max-w-[200px] gap-1 border border-border bg-transparent px-1.5 text-xs text-foreground"
                        title={effectiveAgent
                          ? `本次对话用「${effectiveAgent.label}」（它的能力清单见「智能体装配」页）`
                          : "用哪个智能体：各自的能力/工具/技能/审批在「智能体装配」页配置"}
                      >
                        <SelectValue placeholder="智能体">
                          {effectiveAgent?.label ?? "智能体"}
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        {pickableAgents.map((a) => (
                          <SelectItem key={a.id} value={a.id}>{a.label || a.id}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  {/* 模型（per conversation, ?model=）—— 用设置页存的哪个「模型预设」。
                      预设各自带 模型名+端点+Key，所以能跨供应商切；留空跟着设置页的全局模型。 */}
                  <div className="flex shrink-0 items-center gap-1 border-l border-border pl-4">
                    <Cpu size={14} className="text-muted-foreground" />
                    <Select value={modelPreset} onValueChange={(v) => setModelPreset(v ?? "")}>
                      <SelectTrigger
                        size="sm"
                        className="h-7 max-w-[200px] gap-1 border border-border bg-transparent px-1.5 text-xs text-foreground"
                        title={selectedPreset
                          ? `本次对话用预设「${selectedPreset.name}」的模型与端点（${selectedPreset.values.llm_model ?? "默认模型名"}）；只影响本会话`
                          : `本次对话跟随设置页的全局模型${defaultModelName ? `（当前：${defaultModelName}）` : ""}`}
                      >
                        <SelectValue placeholder="模型">
                          {selectedPreset
                            ? selectedPreset.name
                            : (defaultModelName || "跟随设置")}
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="">
                          {defaultModelName
                            ? `跟随设置（${defaultModelName}）`
                            : "跟随设置（未配置）"}
                        </SelectItem>
                        {modelPresets.map((p) => (
                          <SelectItem key={p.name} value={p.name}>
                            {p.name}{p.values.llm_model ? `（${p.values.llm_model}）` : ""}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  {/* Token 用量（只读，当前上下文占用 + 占窗口百分比）：取最后一次
                      模型调用的 total_tokens（其 input 即当前完整对话）。达到窗口
                      85% 时后端会自动压缩早期历史，届时占比会回落——正常现象。 */}
                  {sessionTokens > 0 && (
                    <div
                      className={cn(
                        "flex shrink-0 items-center gap-1 border-l border-border pl-4 text-xs text-muted-foreground",
                        sessionTokenPct >= 85 && "text-destructive",
                      )}
                      title={`当前上下文占用 ${sessionTokens.toLocaleString()} tokens`
                        + `（最近一轮：输入 ${(latestUsage?.input ?? 0).toLocaleString()} / 输出 ${(latestUsage?.output ?? 0).toLocaleString()}）`
                        + `，占上下文窗口 ${contextWindow.toLocaleString()} 的 ${sessionTokenPct}%。`
                        + `超过 85% 时平台自动压缩早期历史`}
                    >
                      <Gauge size={14} className="shrink-0" />
                      <span className="whitespace-nowrap">
                        上下文 {formatTokenCount(sessionTokens)} ({sessionTokenPct}%)
                      </span>
                    </div>
                  )}
                  {/* 代码图谱仓库（per conversation, ?repo=）—— 挂上哪个，代码分析就作用于它。
                      候选来自「代码图谱」页注册的仓库；挂上后写它仍需审批（只读分析对象）。
                      叫「代码图谱仓库」而不是「仓库」：这里的仓库只有一个来源、也只服务
                      一件事（代码图谱），跟一般意义上的"代码目录"不是一回事。 */}
                  {repos.length > 0 && (
                    <div className="flex shrink-0 items-center gap-1 border-l border-border pl-4">
                      <FolderGit2 size={14} className="text-muted-foreground" />
                      <Select
                        value={repoId}
                        onValueChange={(v) => setRepoId(v ?? "")}
                      >
                        <SelectTrigger
                          size="sm"
                          className="h-7 max-w-[220px] gap-1 border border-border bg-transparent px-1.5 text-xs text-foreground"
                          title={selectedRepo
                            ? `本次对话的工作目录：${selectedRepo.repo_path}（未建索引时图谱工具不可用，退回 grep/read_file）`
                            : "挂一个代码图谱仓库：它的绝对路径成为工作目录，代码分析类工具按它解析目标。候选是「代码图谱」页里注册的仓库（未建索引的会标出来，那种情况下图谱工具用不了，只能 grep/read_file）"}
                        >
                          <SelectValue placeholder="代码图谱仓库：不挂载">
                            {selectedRepo
                              ? (selectedRepo.display_name || selectedRepo.repo_path)
                              : "代码图谱仓库：不挂载"}
                          </SelectValue>
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="">代码图谱仓库：不挂载</SelectItem>
                          {repos.map((r) => (
                            <SelectItem key={r.id} value={r.id}>
                              {(r.display_name || r.repo_path)}{r.indexed ? "" : "（未建索引）"}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  )}
                </div>
              </div>
              <div className="flex justify-end gap-2">
                {isLoading ? (
                  <Button
                    type="button"
                    onClick={stopStream}
                    className="h-9 w-9 rounded-full bg-destructive p-0 text-destructive-foreground hover:bg-destructive/90"
                    title="停止生成"
                  >
                    <Square className="h-3.5 w-3.5" />
                  </Button>
                ) : (
                  <Button
                    type="submit"
                    onClick={handleSubmit}
                    disabled={
                      submitDisabled ||
                      approvalPending ||
                      isUploading ||
                      (!input.trim() && contentBlocks.length === 0)
                    }
                    className="h-9 w-9 rounded-full bg-brand p-0 text-white hover:bg-brand-600 disabled:opacity-40"
                    title={approvalPending ? "等待命令审批" : isUploading ? "文件上传中…" : "发送"}
                  >
                    <ArrowUp className="h-4.5 w-4.5" />
                  </Button>
                )}
              </div>
            </div>
          </form>
        </div>
      </div>

      {/* Full Access Risk Confirmation (dsh: RiskConfirmation) */}
      <Dialog open={fullAccessConfirmOpen} onOpenChange={setFullAccessConfirmOpen}>
        <DialogContent className="sm:max-w-[400px]">
          <DialogHeader>
            <DialogTitle>开启完全访问？</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            完全访问模式下，智能体执行任何命令（含白名单外的 shell 命令）与读写任何路径
            都不再需要你的确认。仅在自己完全信任当前任务时使用。
          </p>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" size="sm" onClick={() => setFullAccessConfirmOpen(false)}>
              取消
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => {
                setPermissionMode("full_access");
                setFullAccessConfirmOpen(false);
              }}
            >
              确认开启
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      </div>{/* 主列结束 */}

      {/* 子智能体实时操作面板：与主列并排（大屏）/覆盖（小屏）。
          feed 拷贝成新数组——store 原地变更同一引用，React.memo 会认为
          props 没变而跳过重渲染，面板就永远停在打开那一刻（「正在启动…」） */}
      <SubAgentPanel
        subAgent={liveSubAgent}
        feed={
          liveSubAgent ? [...getSubAgentFeed(liveSubAgent.id)] : []
        }
        onClose={() => setActivitySubAgent(null)}
      />
    </div>
  );
});

ChatInterface.displayName = "ChatInterface";
