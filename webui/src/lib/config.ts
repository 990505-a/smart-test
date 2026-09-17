/**
 * Browser-side service-address resolution.
 *
 * 本地部署端口固定（LangGraph :5011 / FastAPI :5012，见启动器），正常使用
 * 无需任何配置——这里保留两个可选覆盖字段（例如后端跑在别的机器上时）。
 * 登录页的「服务器设置」是唯一入口。
 *
 * 公网访问（h3comfyui.art 门户）时的额外一层：caddy 反代把同一个域名按路径
 * 前缀分流到两个后端（`/lg` → LangGraph :5011，`/py` → FastAPI :5012），
 * 所以当页面不是从回环地址打开时，默认值改为**同源子路径**——浏览器无需
 * 额外配置、不跨域、Basic Auth 凭据也随同源请求自动带上。
 */

export interface StandaloneConfig {
  deploymentUrl?: string;  // LangGraph API 地址，默认 DEFAULT_DEPLOYMENT_URL
  fastapiUrl?: string;     // FastAPI 地址，默认 DEFAULT_FASTAPI_URL
}

export const DEFAULT_DEPLOYMENT_URL = "http://localhost:5011";
export const DEFAULT_FASTAPI_URL = "http://localhost:5012";

/** 反代域名下的路径前缀（与 ~/h3services/Caddyfile 的 @smarttest 段一致）。 */
export const PROXY_DEPLOYMENT_PATH = "/lg";
export const PROXY_FASTAPI_PATH = "/py";

// 去登录之后不再有应用 token；后端仍接受 X-Auth-Token（外部脚本用），
// 见 src/app/api/v2/auth.py::_extract_token。

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

/** 是否从回环地址访问（本机开发 / 启动器打开的浏览器）。 */
function isLoopback(): boolean {
  const host = window.location.hostname;
  return (
    host === "localhost" ||
    host === "127.0.0.1" ||
    host === "0.0.0.0" ||
    host === "::1" ||
    host.endsWith(".localhost")
  );
}

/**
 * 未显式配置时的有效默认地址。回环 → 直连端口；公网域名 → 同源子路径。
 *
 * SSR 期间 window 不存在，统一返回回环默认值——这样服务端与客户端首帧一致，
 * 不会有 hydration 不匹配；真正的解析在挂载后（见各页的 useState/useEffect）。
 */
function resolve(explicit: string | undefined, proxyPath: string, fallback: string): string {
  if (explicit) return explicit;
  if (typeof window === "undefined" || isLoopback()) return fallback;
  return `${window.location.origin}${proxyPath}`;
}

export function getDeploymentUrl(): string {
  return resolve(getConfig()?.deploymentUrl, PROXY_DEPLOYMENT_PATH, DEFAULT_DEPLOYMENT_URL);
}

export function getFastapiUrl(): string {
  return resolve(getConfig()?.fastapiUrl, PROXY_FASTAPI_PATH, DEFAULT_FASTAPI_URL);
}

export function saveConfig(config: StandaloneConfig): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(CONFIG_KEY, JSON.stringify(config));
}
