/**
 * Browser-side service-address resolution.
 *
 * 地址是**算出来的，不是配出来的**：本地部署端口固定（LangGraph :5011 /
 * FastAPI :5012，见启动器），公网门户走同源子路径。曾经有一套 localStorage
 * 覆盖（`smart-test-platform-config`），但它的唯一入口是已删除的登录页
 * 「服务器设置」，于是只剩读路径没有写路径——2026-09-18 一并删除。
 *
 * 公网访问（h3comfyui.art 门户）：caddy 反代把同一个域名按路径前缀分流到两个
 * 后端（`/lg` → LangGraph :5011，`/py` → FastAPI :5012），所以当页面不是从
 * 回环地址打开时，默认值改为**同源子路径**——浏览器无需额外配置、不跨域、
 * Basic Auth 凭据也随同源请求自动带上。
 */

export const DEFAULT_DEPLOYMENT_URL = "http://localhost:5011";
export const DEFAULT_FASTAPI_URL = "http://localhost:5012";

/** 反代域名下的路径前缀（与 ~/h3services/Caddyfile 的 @smarttest 段一致）。 */
export const PROXY_DEPLOYMENT_PATH = "/lg";
export const PROXY_FASTAPI_PATH = "/py";

// 去登录之后不再有应用 token；后端仍接受 X-Auth-Token（外部脚本用），
// 见 src/app/api/v2/auth.py::_extract_token。

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
 * 回环 → 直连端口；公网域名 → 同源子路径。
 *
 * SSR 期间 window 不存在，统一返回回环默认值——这样服务端与客户端首帧一致，
 * 不会有 hydration 不匹配；真正的解析在挂载后（见各页的 useState/useEffect）。
 */
function resolve(proxyPath: string, fallback: string): string {
  if (typeof window === "undefined" || isLoopback()) return fallback;
  return `${window.location.origin}${proxyPath}`;
}

export function getDeploymentUrl(): string {
  return resolve(PROXY_DEPLOYMENT_PATH, DEFAULT_DEPLOYMENT_URL);
}

export function getFastapiUrl(): string {
  return resolve(PROXY_FASTAPI_PATH, DEFAULT_FASTAPI_URL);
}
