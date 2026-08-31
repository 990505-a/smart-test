/**
 * Browser-side service-address overrides.
 *
 * 本地部署端口固定（LangGraph :5011 / FastAPI :5012，见启动器），正常使用
 * 无需任何配置——这里只保留两个可选覆盖字段（例如后端跑在别的机器上时）。
 * 登录页的「服务器设置」是唯一入口。
 */

export interface StandaloneConfig {
  deploymentUrl?: string;  // LangGraph API 地址，默认 DEFAULT_DEPLOYMENT_URL
  fastapiUrl?: string;     // FastAPI 地址，默认 DEFAULT_FASTAPI_URL
}

export const DEFAULT_DEPLOYMENT_URL = "http://localhost:5011";
export const DEFAULT_FASTAPI_URL = "http://localhost:5012";

const CONFIG_KEY = "smart-test-platform-config";

// 服务端口从 2026/8001 迁到 5010-5014 段后，登录时持久化的旧默认地址
// 仍会覆盖代码默认值——读取时把精确匹配的旧默认地址原地改写一次。
const PORT_MIGRATION: Record<string, string> = {
  "http://localhost:2026": DEFAULT_DEPLOYMENT_URL,
  "http://localhost:8001": DEFAULT_FASTAPI_URL,
};

export function getConfig(): StandaloneConfig | null {
  if (typeof window === "undefined") return null;

  const stored = localStorage.getItem(CONFIG_KEY);
  if (!stored) return null;

  try {
    const config = JSON.parse(stored) as StandaloneConfig;
    let migrated = false;
    for (const key of ["deploymentUrl", "fastapiUrl"] as const) {
      const value = config[key];
      if (typeof value === "string" && PORT_MIGRATION[value]) {
        config[key] = PORT_MIGRATION[value];
        migrated = true;
      }
    }
    if (migrated) {
      localStorage.setItem(CONFIG_KEY, JSON.stringify(config));
    }
    return config;
  } catch {
    return null;
  }
}

export function getDeploymentUrl(): string {
  return getConfig()?.deploymentUrl || DEFAULT_DEPLOYMENT_URL;
}

export function getFastapiUrl(): string {
  return getConfig()?.fastapiUrl || DEFAULT_FASTAPI_URL;
}

export function saveConfig(config: StandaloneConfig): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(CONFIG_KEY, JSON.stringify(config));
}
