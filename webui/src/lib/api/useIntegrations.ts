"use client";

/**
 * 外部依赖就绪状态（`/api/v2/integrations`）。
 *
 * 一个依赖一行：能不能用、缺什么、怎么补。描述的唯一来源是后端的
 * `core/integrations.py` 注册表 —— 页面只负责渲染，不再各自写"请打开启动器…"
 * 这类文案（同一个依赖在不同页面说法不一致，是这次收敛要消灭的东西）。
 */

import useSWR from "swr";
import { apiClient } from "@/lib/api-client";

export type IntegrationKind = "bundled" | "local_service" | "external";

export interface IntegrationItem {
  key: string;
  label: string;
  kind: IntegrationKind;
  optional: boolean;
  summary: string;
  absent_effect: string;
  fix_hint: string;
  /** 启动器里的服务名；有值就说明平台能一键把它拉起来 */
  launch: string | null;
  /** 平台能自己装的安装目标（目前只有 codebase-memory） */
  install: string | null;
  ready: boolean;
  detail?: string;
  error?: string | null;
  /** 未配置（而非故障）时的说明，例如"选填：不配则只落本地" */
  reason?: string;
  configured?: boolean;
  install_state?: {
    managed_dir?: string;
    installed_version?: string | null;
    target_version?: string;
    asset?: string;
    supported?: boolean;
    upgradable?: boolean;
    /** 当前实际生效的 exe 路径 */
    configured_exe?: string;
    /** false = 有人用 .env 指定了别的路径，平台自管安装没被用上 */
    using_managed?: boolean;
  };
}

export interface IntegrationsPayload {
  items: IntegrationItem[];
  ready: number;
  total: number;
  /** 必选依赖缺失的 key（缺了这些平台不可用，选填的不算） */
  blocking: string[];
}

export function useIntegrations(options?: { refreshInterval?: number }) {
  return useSWR(
    "/integrations",
    () => apiClient.get<IntegrationsPayload>("/integrations").then((r) => r.data),
    { refreshInterval: options?.refreshInterval ?? 30000 },
  );
}

/** 让启动器启动这个依赖（本机模式） */
export async function startIntegration(key: string) {
  return apiClient.post<{ service?: string }>(`/integrations/${key}/start`, {}).then((r) => r.data);
}

/** 平台自管安装/升级（codebase-memory） */
export async function installIntegration(key: string, force = false) {
  return apiClient
    .post<{ version?: string; message?: string }>(`/integrations/${key}/install`, {
      force,
      version: null,
    })
    .then((r) => r.data);
}

/**
 * 清掉一个平台设置项（写空值 = 回退平台默认）。
 *
 * 目前只用在"把 CODEBASE_MEMORY_EXE 恢复成平台自管版本"上：设置页已经不提供
 * 这个输入框，但 .env 里可能有老配置覆盖着自管安装，那条路径已经不可达时
 * 就绪中心要能一键改回来。
 */
export async function clearPlatformSetting(key: string) {
  return apiClient.put("/settings/platform", { values: { [key]: "" } }).then((r) => r.data);
}
