"use client";

/**
 * 模式选择器（dsh 风格）：在输入框旁边选"这次对话用哪个智能体"。
 *
 * 以前的顶部 Tab 栏把智能体当成"页面"，切一下就换页；实际上这些智能体只是
 * **挂载的工具与技能不同**（用例生成挂用例工具+飞书，Unity 自动化挂 unity 工具，
 * Web-UI 自动化挂 playwright 工具，代码分析挂图谱工具），是同一个 harness 的
 * 不同模式。所以它属于"这次对话的配置"，跟输入框放在一起、跟着会话走：
 *
 *   - 选择即切换（切换会开一个新会话——不同 graph 的 checkpoint 不能混用）
 *   - 会话记着自己的模式（thread_infos.agent），点开历史会话会把模式切回去
 *   - 菜单里写清每个模式能干什么，省得靠标签猜
 */

import { useState } from "react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { AGENT_CONFIG, AGENT_ORDER, AGENT_ICONS, type AgentKey } from "@/app/types/types";
import { Check, ChevronDown } from "lucide-react";

export function AgentPicker({
  activeAgent,
  onAgentChange,
  disabled,
}: {
  activeAgent: string;
  onAgentChange: (value: string) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const key = (activeAgent in AGENT_CONFIG ? activeAgent : "testcase") as AgentKey;
  const current = AGENT_CONFIG[key];
  const CurrentIcon = AGENT_ICONS[key];

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger
        disabled={disabled}
        title="选择智能体模式（切换会开一个新会话）"
        className="flex h-8 shrink-0 items-center gap-1.5 rounded-md border border-input bg-transparent px-2 text-sm hover:bg-accent disabled:opacity-50"
      >
        <CurrentIcon className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="max-w-[7rem] truncate">{current.label}</span>
        <ChevronDown className="h-3 w-3 text-muted-foreground" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-80">
        {/* Base UI 的 GroupLabel 必须在 Group 内，否则渲染时直接抛错 */}
        <DropdownMenuGroup>
          <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
            智能体模式（同为 harness，挂载的工具与技能不同）
          </DropdownMenuLabel>
          {AGENT_ORDER.map((agentKey) => {
            const config = AGENT_CONFIG[agentKey];
            const Icon = AGENT_ICONS[agentKey];
            const active = agentKey === key;
            return (
              <DropdownMenuItem
                key={agentKey}
                className="items-start gap-2 py-2"
                // Base UI 的 Menu.Item 用 onClick（Radix 才是 onSelect）
                onClick={() => {
                  if (!active) onAgentChange(agentKey);
                  setOpen(false);
                }}
              >
                <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className="text-sm font-medium">{config.label}</span>
                    {active && <Check className="h-3.5 w-3.5 text-brand" />}
                  </div>
                  <p className="mt-0.5 text-xs leading-4 text-muted-foreground">
                    {config.description}
                  </p>
                  <p className="mt-0.5 font-mono text-[10px] text-muted-foreground/70">
                    {config.graphKey}
                  </p>
                </div>
              </DropdownMenuItem>
            );
          })}
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
