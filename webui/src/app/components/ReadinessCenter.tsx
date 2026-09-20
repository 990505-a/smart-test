"use client";

/**
 * 就绪中心 —— 一屏看完"平台依赖的外部东西现在能不能用、缺什么、怎么补"。
 *
 * 存在的理由：这些依赖以前散落在四处描述（设置页字段 / 启动器服务表 / MCP 清单 /
 * 能力里的中文散文），没有任何一处能回答"我现在缺什么"。于是用户看到的是一堆要填的
 * 字段和各页面各写一句的"不可达"。现在统一读 `/api/v2/integrations`。
 *
 * 两类行分开显示：
 *  - **必选**（缺了平台不可用）：缺了就标红，这是真故障；
 *  - **选填**（缺了只是少一块能力）：缺了不该显示成故障，写清"失去什么"即可——
 *    以前 Langfuse 一类的选填件和模型这种必选件混在一起，用户分不清要不要管。
 */

import React, { useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import {
  CheckCircle2, CircleDashed, Loader2, RefreshCw, Play, Download, AlertTriangle,
} from "lucide-react";
import {
  useIntegrations, startIntegration, installIntegration, clearPlatformSetting,
  type IntegrationItem,
} from "@/lib/api/useIntegrations";

function KindBadge({ item }: { item: IntegrationItem }) {
  const text = item.kind === "bundled"
    ? "自带/平台可装"
    : item.kind === "local_service" ? "本机服务" : "外部";
  return (
    <Badge variant="outline" className="text-[10px] font-normal text-muted-foreground">
      {text}
    </Badge>
  );
}

function IntegrationRow({ item, onChanged }: { item: IntegrationItem; onChanged: () => void }) {
  const [busy, setBusy] = useState<string | null>(null);

  const run = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label);
    try {
      await fn();
      toast.success(`${item.label}：${label}已发起`);
      setTimeout(onChanged, 1500);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : `${label}失败`);
    } finally {
      setBusy(null);
    }
  };

  // 三态：就绪 / 未配置（选填件，不是故障） / 未就绪
  const unconfigured = item.configured === false;
  const tone = item.ready
    ? "text-success"
    : unconfigured ? "text-muted-foreground"
    : item.optional ? "text-warning" : "text-destructive";

  const icon = item.ready
    ? <CheckCircle2 className={`mt-0.5 h-4 w-4 shrink-0 ${tone}`} />
    : unconfigured ? <CircleDashed className={`mt-0.5 h-4 w-4 shrink-0 ${tone}`} />
    : <AlertTriangle className={`mt-0.5 h-4 w-4 shrink-0 ${tone}`} />;

  const state = item.ready
    ? (item.detail || "就绪")
    : unconfigured ? (item.reason || "未配置")
    : (item.error || item.reason || "未就绪");

  const upgradable = item.install_state?.upgradable;

  return (
    <div className="flex items-start gap-3 border-t py-3 first:border-t-0">
      {icon}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium">{item.label}</span>
          <KindBadge item={item} />
          {item.optional
            ? <span className="text-[10px] text-muted-foreground">选填</span>
            : <span className="text-[10px] text-destructive">必选</span>}
        </div>
        <p className={`mt-0.5 text-xs ${item.ready ? "text-muted-foreground" : tone}`}>{state}</p>
        {/* 缺了会失去什么 + 怎么补：两句话都来自后端注册表，页面不自己编 */}
        {!item.ready && (
          <p className="mt-1 text-xs text-muted-foreground">
            {item.absent_effect}
            <span className="mx-1 text-border">|</span>
            <span className="text-foreground/80">{item.fix_hint}</span>
          </p>
        )}
        {upgradable && (
          <p className="mt-1 text-xs text-warning">
            已安装 {item.install_state?.installed_version}，可升级到 {item.install_state?.target_version}
          </p>
        )}
        {/* 引擎路径被 .env 手动指定、且指的不是平台自管那份时，说清"实际用的是哪个"
            并给一条改回去的路 —— 设置页已经没有这个输入框了，不给按钮用户只能去翻 .env */}
        {item.install && item.install_state?.using_managed === false && (
          <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span>
              实际使用 <code className="text-foreground/80">{item.install_state?.configured_exe}</code>
              （.env 里的 CODEBASE_MEMORY_EXE 覆盖了平台自管安装）
            </span>
            <Button size="sm" variant="ghost" className="h-6 px-2 text-xs"
                    disabled={busy !== null}
                    onClick={() => run("改用平台自管版本", () => clearPlatformSetting("codebase_memory_exe"))}>
              {busy ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : null}
              改用平台自管版本
            </Button>
          </p>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-2">
        {item.launch && !item.ready && (
          <Button size="sm" variant="outline"
                  disabled={busy !== null}
                  onClick={() => run("启动", () => startIntegration(item.key))}>
            {busy === "启动" ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                            : <Play className="mr-1 h-3.5 w-3.5" />}
            启动
          </Button>
        )}
        {item.install && (!item.ready || upgradable) && (
          <Button size="sm" variant="outline"
                  disabled={busy !== null}
                  onClick={() => run(upgradable ? "升级" : "安装",
                                     () => installIntegration(item.key, !!upgradable))}>
            {busy ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                   : <Download className="mr-1 h-3.5 w-3.5" />}
            {upgradable ? "升级" : "安装"}
          </Button>
        )}
      </div>
    </div>
  );
}

export function ReadinessCenter() {
  const { data, isLoading, mutate } = useIntegrations();

  const items = data?.items ?? [];
  const blocking = data?.blocking ?? [];
  const required = items.filter((i) => !i.optional);
  const optionalItems = items.filter((i) => i.optional);

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold">就绪中心</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {isLoading ? "正在探活…"
              : blocking.length > 0
                ? `必选依赖缺失：${blocking.join("、")} —— 平台功能不完整`
                : `${data?.ready ?? 0}/${data?.total ?? 0} 就绪，必选依赖全部就绪`}
          </p>
        </div>
        <Button size="sm" variant="ghost" onClick={() => mutate()} disabled={isLoading}>
          <RefreshCw className={`mr-1 h-3.5 w-3.5 ${isLoading ? "animate-spin" : ""}`} />
          重新探活
        </Button>
      </div>

      {items.length > 0 && (
        <div className="mt-3">
          {required.map((item) => (
            <IntegrationRow key={item.key} item={item} onChanged={() => mutate()} />
          ))}
          <div className="border-t pt-3">
            <p className="text-xs font-medium text-muted-foreground">
              选填依赖（缺了只是少一块能力，不影响其余功能）
            </p>
          </div>
          {optionalItems.map((item) => (
            <IntegrationRow key={item.key} item={item} onChanged={() => mutate()} />
          ))}
        </div>
      )}
    </Card>
  );
}
