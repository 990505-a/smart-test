/**
 * 验收夹具：通过接口造一条「会失败」的用例并执行，供失败路径的验收使用。
 *
 * 为什么要造失败：通过路径的存证几乎为空（无失败截图、无 trace、报告只有几百 KB），
 * 而失败路径才是真正要验的东西——失败截图能不能看、trace 能不能回放、错误行号
 * 对不对。跑完由 global-teardown 删掉，不在平台里留常驻失败用例。
 */

import { request, type FullConfig } from "@playwright/test";
import { writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";

const API = process.env.WEBUI_API ?? "http://127.0.0.1:5012";
const FIXTURE_NAME = "验收夹具-故意失败（自动创建）";
const SMOKE_FIXTURE_NAME = "验收夹具-冒烟（自动创建）";

const SPEC = `import { test, expect } from '@playwright/test'

test.describe('验收夹具', () => {
  test('故意失败：断言不成立以验证失败存证链路', async ({ page }) => {
    await page.goto('https://example.com', { waitUntil: 'domcontentloaded' })
    await expect(page.getByText('这段文字不存在-用于制造失败')).toBeVisible({ timeout: 5000 })
  })
})
`;

// 通过路径的夹具：要够慢，才观察得到「运行中 → 实时进度 → 收敛」这条链路
const SMOKE_SPEC = `import { test, expect } from '@playwright/test'

test.describe('验收夹具·冒烟', () => {
  test('页面可打开且标题正确', async ({ page }) => {
    await page.goto('https://example.com', { waitUntil: 'domcontentloaded' })
    await expect(page).toHaveTitle(/Example/)
    await page.waitForTimeout(4000)
    await expect(page).toHaveTitle(/Example/)
  })
})
`;

export default async function globalSetup(config: FullConfig): Promise<void> {
  const api = await request.newContext({ baseURL: API });
  const login = await api.post("/api/v2/auth/login", {
    data: {
      username: process.env.WEBUI_USER ?? "",
      password: process.env.WEBUI_PASS ?? "",
    },
  });
  if (!login.ok()) throw new Error(`夹具登录失败: HTTP ${login.status()}`);
  const token = (await login.json()).data.token as string;
  const headers = { "X-Auth-Token": token };

  // 清掉上一次残留（同名）
  const existing = await api.get("/api/v2/web-ui-auto/scripts", { headers });
  for (const script of (await existing.json()).data as { id: string; name: string }[]) {
    if (script.name === FIXTURE_NAME) {
      await api.delete(`/api/v2/web-ui-auto/scripts/${script.id}`, { headers });
    }
  }

  const created = await api.post("/api/v2/web-ui-auto/scripts", {
    headers,
    data: {
      name: FIXTURE_NAME,
      module: "验收",
      description: "自动化验收夹具，跑完即删",
      content: SPEC,
      spec_file: "tests/acceptance-fail.spec.ts",
      target_url: "https://example.com",
      options: {},
      status: "draft",
    },
  });
  if (!created.ok()) throw new Error(`夹具创建失败: HTTP ${created.status()}`);
  const scriptId = (await created.json()).data.id as string;

  // auto_repair: false 是**必须的**，不能省。
  // 平台默认会拿 .env 的 WEB_UI_MAX_REPAIR（本机是 2）去自修复：这条夹具的失败
  // 原因是"断言的目标元素不存在"，而模型完全可以把它改成一个成立的断言——于是
  // 这条"故意失败"的执行变成通过（0 失败、退出码 0），下游 04 号用例找不到
  // 「失败原因」直接挂。实测就撞上过一次。要验的是失败存证链路，就不能让自修复
  // 把失败修掉。
  await api.post(`/api/v2/web-ui-auto/scripts/${scriptId}/run`, {
    headers,
    data: { auto_repair: false },
  });

  // 等执行进入终态。注意：执行记录现在**先以 running 落库**再开跑
  // （前端要靠它显示实时进度），所以看到记录 ≠ 跑完了。
  let runId: string | null = null;
  for (let i = 0; i < 60 && runId === null; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 3000));
    const runs = await api.get(`/api/v2/web-ui-auto/scripts/${scriptId}/runs`, { headers });
    const rows = (await runs.json()).data as { id: string; status: string }[];
    if (rows.length > 0 && rows[0].status !== "running") runId = rows[0].id;
  }
  if (runId === null) throw new Error("夹具执行超时，未收敛到终态");

  // ---- 第二个夹具：一条会通过、但跑得够慢的冒烟脚本 -------------------------
  // 供「执行中能看实时进度」那条用例现场点「执行」用。以前它用的是用户用例库里
  // 的「豆瓣电影首页冒烟测试」——那意味着**清空过数据（或新装）的环境里这套验收
  // 直接跑不起来**。夹具必须自己造，不能依赖用户的数据。
  for (const script of (await (await api.get("/api/v2/web-ui-auto/scripts", { headers })).json())
       .data as { id: string; name: string }[]) {
    if (script.name === SMOKE_FIXTURE_NAME) {
      await api.delete(`/api/v2/web-ui-auto/scripts/${script.id}`, { headers });
    }
  }
  const smoke = await api.post("/api/v2/web-ui-auto/scripts", {
    headers,
    data: {
      name: SMOKE_FIXTURE_NAME,
      module: "验收",
      description: "自动化验收夹具（通过路径），跑完即删",
      content: SMOKE_SPEC,
      spec_file: "tests/acceptance-smoke.spec.ts",
      target_url: "https://example.com",
      options: {},
      status: "draft",
    },
  });
  if (!smoke.ok()) throw new Error(`冒烟夹具创建失败: HTTP ${smoke.status()}`);
  const smokeScriptId = (await smoke.json()).data.id as string;

  mkdirSync(join(config.rootDir, "artifacts"), { recursive: true });
  writeFileSync(
    join(config.rootDir, "artifacts", "fixture.json"),
    JSON.stringify({ scriptId, runId, name: FIXTURE_NAME,
                     smokeScriptId, smokeName: SMOKE_FIXTURE_NAME }, null, 2),
  );
  console.log(`[验收夹具] script=${scriptId} run=${runId} smoke=${smokeScriptId}`);
  await api.dispose();
}
