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
  CheckCircle2, CircleDashed, CircleSlash, Loader2, RefreshCw, Play, Download,
  AlertTriangle,
} from "lucide-react";
import {
  useIntegrations, startIntegration, installIntegration, clearPlatformSetting,
  setApplicability, type IntegrationItem,
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

function IntegrationRow({ item, onChanged, waitReady }: {
  item: IntegrationItem;
  onChanged: () => void;
  /** 轮询到该项就绪为止（或超时）；返回是否就绪。见 ReadinessCenter 里的说明。 */
  waitReady: (key: string) => Promise<boolean>;
}) {
  const [busy, setBusy] = useState<string | null>(null);

  const run = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label);
    try {
      await fn();
      if (label === "启动") {
        // 「启动」不能只报"已发起"：启动器 start 只 sleep 0.5s 就返回，它不等服务
        // 就绪（LightRAG 要起 uvicorn、unity-mcp 走 uvx 首次还得下包）。固定 1.5s
        // 刷一次的话，用户看到的是"点了没反应"然后要等 30 秒轮询。这里轮询到就绪。
        setBusy("等待就绪");
        const ok = await waitReady(item.key);
        if (ok) toast.success(`${item.label}：已就绪`);
        else toast.warning(`${item.label}：已发起，但还没就绪`, {
          description: "服务可能需要更久（首次运行要下载依赖）。可稍后点「重新探活」，或看启动器(:5010)的日志。",
        });
      } else {
        toast.success(`${item.label}：${label}已发起`);
        setTimeout(onChanged, 1500);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : `${label}失败`);
    } finally {
      setBusy(null);
    }
  };

  // 四态：就绪 / 不适用（这台机器不跑它） / 未配置（选填件，不是故障） / 未就绪
  const unconfigured = item.configured === false;
  const na = item.not_applicable === true;
  const tone = na ? "text-muted-foreground"
    : item.ready ? "text-success"
    : unconfigured ? "text-muted-foreground"
    : item.optional ? "text-warning" : "text-destructive";

  const icon = na
    ? <CircleSlash className={`mt-0.5 h-4 w-4 shrink-0 ${tone}`} />
    : item.ready
    ? <CheckCircle2 className={`mt-0.5 h-4 w-4 shrink-0 ${tone}`} />
    : unconfigured ? <CircleDashed className={`mt-0.5 h-4 w-4 shrink-0 ${tone}`} />
    : <AlertTriangle className={`mt-0.5 h-4 w-4 shrink-0 ${tone}`} />;

  const state = na
    ? "已标记为不适用（这台机器不跑它，不计入缺失）"
    : item.ready
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
        <p className={`mt-0.5 text-xs ${item.ready || na ? "text-muted-foreground" : tone}`}>{state}</p>
        {/* 缺了会失去什么 + 怎么补：两句话都来自后端注册表，页面不自己编。
            已标记「不适用」的不再重复这些——那是待办清单，不是故障说明。 */}
        {!item.ready && !na && (
          <p className="mt-1 text-xs text-muted-foreground">
            {item.absent_effect}
            <span className="mx-1 text-border">|</span>
            <span className="text-foreground/80">{item.fix_hint}</span>
          </p>
        )}
        {/* 探针给的"要不要提醒用户可以标记不适用"（如本机未检测到 Unity）：
            决定权在用户，这里只负责让他知道有这个开关 */}
        {!item.ready && !na && item.na_hint && (
          <p className="mt-1 text-xs text-muted-foreground/80">{item.na_hint}</p>
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
        {item.launch && !item.ready && !na && (
          <Button size="sm" variant="outline"
                  disabled={busy !== null}
                  onClick={() => run("启动", () => startIntegration(item.key))}>
            {busy !== null ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                           : <Play className="mr-1 h-3.5 w-3.5" />}
            {busy === "等待就绪" ? "等待就绪…" : "启动"}
          </Button>
        )}
        {item.install && (!item.ready || upgradable) && !na && (
          <Button size="sm" variant="outline"
                  disabled={busy !== null}
                  onClick={() => run(upgradable ? "升级" : "安装",
                                     () => installIntegration(item.key, !!upgradable))}>
            {busy ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                   : <Download className="mr-1 h-3.5 w-3.5" />}
            {upgradable ? "升级" : "安装"}
          </Button>
        )}
        {/* 只给选填件：必选件缺了就是真故障，不该提供"标记为不适用"这条逃避路径 */}
        {!item.ready && item.optional && !na && (
          <Button size="sm" variant="ghost" className="text-xs text-muted-foreground"
                  disabled={busy !== null}
                  title="这台机器不跑它（如服务端没有 Unity 编辑器）——降级成中性状态，不再长期报警"
                  onClick={() => run("标记为不适用", () => setApplicability(item.key, false))}>
            {busy ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : null}
            标记为不适用
          </Button>
        )}
        {na && (
          <Button size="sm" variant="ghost" className="text-xs"
                  disabled={busy !== null}
                  onClick={() => run("恢复", () => setApplicability(item.key, true))}>
            {busy ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : null}
            恢复
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
  // 已标记「不适用」的不计入分母：这台机器不跑它，算进"x/y 就绪"只会让数字永远不满
  const applicable = items.filter((i) => !i.not_applicable);
  const naCount = items.length - applicable.length;
  const readyCount = applicable.filter((i) => i.ready).length;

  /**
   * 轮询到某一项就绪为止（或超时），返回是否就绪。
   *
   * 为什么需要：启动器 `start_service` 只 `sleep(0.5)` 就返回，它**不等服务就绪**；
   * 而 LightRAG 要起 uvicorn、unity-mcp 走 uvx 首次还要从 PyPI 下包。只刷一次的话
   * 用户看到的是"点了没反应"，再等 30 秒轮询才发现好了——很容易误判成按钮坏了。
   *
   * 用 `mutate()` 拿**新鲜数据**判断，而不是读闭包里的 `item`：后者是这次渲染时的
   * 快照，永远停在"未就绪"。
   */
  const waitReady = async (key: string, timeoutMs = 90_000): Promise<boolean> => {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 3000));
      const fresh = await mutate();
      if ((fresh?.items ?? []).find((i) => i.key === key)?.ready) return true;
    }
    return false;
  };

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold">就绪中心</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {isLoading ? "正在探活…"
              : blocking.length > 0
                ? `必选依赖缺失：${blocking.join("、")} —— 平台功能不完整`
                : `${readyCount}/${applicable.length} 就绪，必选依赖全部就绪`
                  + (naCount > 0 ? `（另有 ${naCount} 项已标记为不适用）` : "")}
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
            <IntegrationRow key={item.key} item={item} onChanged={() => mutate()} waitReady={waitReady} />
          ))}
          <div className="border-t pt-3">
            <p className="text-xs font-medium text-muted-foreground">
              选填依赖（缺了只是少一块能力，不影响其余功能）
            </p>
          </div>
          {optionalItems.map((item) => (
            <IntegrationRow key={item.key} item={item} onChanged={() => mutate()} waitReady={waitReady} />
          ))}
        </div>
      )}
    </Card>
  );
}
