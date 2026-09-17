/** 删掉验收夹具（失败路径 + 通过路径两个），别在用例库里留常驻垃圾脚本。 */

import { request, type FullConfig } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const API = process.env.WEBUI_API ?? "http://127.0.0.1:5012";

// 这个包是 ESM，没有 __dirname；用 Playwright 传进来的 rootDir。
export default async function globalTeardown(config: FullConfig): Promise<void> {
  let scriptId: string | null = null;
  let smokeScriptId: string | null = null;
  try {
    const fixture = JSON.parse(
      readFileSync(join(config.rootDir, "artifacts", "fixture.json"), "utf8"),
    ) as { scriptId: string; smokeScriptId?: string };
    scriptId = fixture.scriptId;
    smokeScriptId = fixture.smokeScriptId ?? null;
  } catch (error) {
    console.warn(`[验收夹具] 读不到 fixture.json，跳过清理：${String(error)}`);
    return;
  }
  if (!scriptId && !smokeScriptId) return;

  const api = await request.newContext({ baseURL: API });
  try {
    const login = await api.post("/api/v2/auth/login", {
      data: {
        username: process.env.WEBUI_USER ?? "",
        password: process.env.WEBUI_PASS ?? "",
      },
    });
    if (!login.ok()) {
      console.warn(`[验收夹具] 清理失败：登录 HTTP ${login.status()}`);
      return;
    }
    const token = (await login.json()).data.token as string;
    for (const id of [scriptId, smokeScriptId].filter(Boolean) as string[]) {
      const response = await api.delete(`/api/v2/web-ui-auto/scripts/${id}`, {
        headers: { "X-Auth-Token": token },
      });
      if (!response.ok()) {
        console.warn(`[验收夹具] 清理失败 script=${id}：HTTP ${response.status()}`);
        continue;
      }
      console.log(`[验收夹具] 已清理 script=${id}`);
    }
  } finally {
    await api.dispose();
  }
}
