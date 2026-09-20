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
import type { SuccessResponse } from "@/app/types/api";

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
  /**
   * 这台机器不跑它（用户标记）。降级成中性状态：不计入 blocking、不报警、不给动作，
   * 只留一个「恢复」。远端服务器上永远不会有 Unity 编辑器，那种"修不好的红项"
   * 会让用户怀疑整页的可信度。
   */
  not_applicable?: boolean;
  /** 探针给的"要不要提醒用户可以标记为不适用"的提示（如本机未检测到 Unity） */
  na_hint?: string | null;
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
  const r = await apiClient.post<{ error?: string; hint?: string; service?: string }>(
    `/integrations/${key}/start`, {});
  return unwrapAction(r, "启动");
}

/**
 * 平台自管安装/升级（codebase-memory 二进制 / playwright 浏览器）。
 *
 * 失败必须抛：后端约定「API 边界不抛异常」，失败是 HTTP 200 + `success:false`，
 * 错误与修复提示都装在 data 里。不检查的话调用方会把"失败"当"已发起"——用户
 * 看到成功提示、界面却毫无变化（Linux 宿主机缺 root、装不上系统依赖就是这种情形，
 * 而那条 sudo 命令正是要给他看的）。
 */
export async function installIntegration(key: string, force = false) {
  const r = await apiClient.post<{ error?: string; hint?: string; version?: string }>(
    `/integrations/${key}/install`, { force, version: null });
  return unwrapAction(r, "安装");
}

/** 把 `{success, data:{error,hint}}` 信封解成"成功返回值"或"带提示的异常"。 */
function unwrapAction<T extends { error?: string; hint?: string }>(
  r: SuccessResponse<T>, label: string,
): T {
  if (r.success === false) {
    const d = (r.data ?? {}) as { error?: string; hint?: string };
    throw new Error([d.error, d.hint].filter(Boolean).join(" —— ") || `${label}失败`);
  }
  return r.data;
}

/**
 * 标记/取消「这台机器不跑它」。
 *
 * 用于远端服务器这类"某项能力天生不可能可用"的场景：标记后该项降级成中性状态，
 * 不再以未就绪的形式长期报警。applicable=false 即标记为不适用。
 */
export async function setApplicability(key: string, applicable: boolean) {
  const r = await apiClient.post<{ error?: string; applicable?: boolean }>(
    `/integrations/${key}/applicability`, { applicable });
  return unwrapAction(r, applicable ? "恢复" : "标记");
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
