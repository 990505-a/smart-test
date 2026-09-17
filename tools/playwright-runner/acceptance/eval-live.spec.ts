/**
 * 测评（Eval）页面的浏览器验收：执行中的实时进度。
 *
 * 这条用例的由来：一个 6 条用例的批次要跑好几分钟，而结果**整轮跑完才入库**，
 * 页面上只有"用例 0/6"和一个转圈图标——用户分不清是在跑、卡住了、还是执行进程
 * 早就跟着容器重启一起没了。现在要求页面上能看见：跑到第几条、agent 正在调什么
 * 工具、日志输出到哪一行。
 *
 * 所以这里不看接口返回什么，而是真的起一个批次（smoke-webui，1 条用例，约 40–60s），
 * 然后在浏览器里断言用户能看见的东西。每一步留截图到 artifacts/。
 *
 * 运行方式见 README.md（WEBUI_USER/WEBUI_PASS 必填）。
 */

import { test, expect, type Page } from "@playwright/test";

const BASE = process.env.WEBUI_BASE ?? "http://127.0.0.1:5013";
const API = process.env.WEBUI_API ?? "http://127.0.0.1:5012";
const USER = process.env.WEBUI_USER ?? "";
const PASS = process.env.WEBUI_PASS ?? "";
const RELEASE = "acceptance";

test.describe.configure({ mode: "serial" });
test.use({ viewport: { width: 1512, height: 950 }, locale: "zh-CN" });

async function login(page: Page): Promise<void> {
  // 平台 2026-09 去掉了登录页：界面不需要登录，直接进工作台。
  await page.goto(`${BASE}/chat`, { waitUntil: "domcontentloaded" });
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 30_000 });
}

test("01 测评批次执行中看得到实时进度（逐条用例 + agent 步骤 + 日志尾）", async ({ page, playwright }) => {
  // 这条用例真跑一个 agent（冒烟集 1 条），时间取决于模型端点的忙闲：独占时
  // 约 50s，和其他批次抢资源时实测到过 250s。超时给足，验的是"看得见"不是"跑得快"。
  test.setTimeout(480_000);

  // 起一个真实批次（接口启动，界面观察）
  const api = await playwright.request.newContext({ baseURL: API });
  const loginResponse = await api.post("/api/v2/auth/login", {
    data: { username: USER, password: PASS },
  });
  expect(loginResponse.ok()).toBeTruthy();
  const token = (await loginResponse.json()).data.token as string;
  const started = await api.post("/api/v2/eval/run", {
    headers: { "X-Auth-Token": token },
    data: { dataset: "smoke-webui.yaml", agent: "webui_agent", concurrency: 1,
            release: RELEASE, gate: null },
  });
  expect(started.ok(), `启动批次失败: ${started.status()} ${await started.text()}`).toBeTruthy();
  const batchId = (await started.json()).data.id as string;

  await login(page);
  await page.goto(`${BASE}/eval`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText("测评批次").first()).toBeVisible({ timeout: 30_000 });

  // 列表上应立刻看到"运行中"（批次行是先落库再开跑的）
  const row = page.locator("table tbody tr", { hasText: `smoke-webui@${RELEASE}` }).first();
  await expect(row).toBeVisible({ timeout: 30_000 });
  await expect(row.getByText("运行中").first()).toBeVisible({ timeout: 15_000 });

  await row.getByRole("button", { name: /详情/ }).click();
  await expect(page.getByText(/^用例 \d+\/\d+/).first()).toBeVisible({ timeout: 20_000 });

  // 实时面板：正在执行 + 活动流 + 日志尾
  await expect(page.getByText("正在执行").first()).toBeVisible({ timeout: 25_000 });
  await expect(page.getByText("agent 在做什么（实时）").first()).toBeVisible();
  await expect(page.getByText("执行日志（实时尾部）").first()).toBeVisible();
  // 日志尾要有真内容（"批次开始"是执行侧写下的第一行）
  await expect(page.getByText(/批次开始 · smoke-webui/).first()).toBeVisible({ timeout: 30_000 });
  // 活动流里要有 agent 的一步步（模型生成 / 工具调用）——只等首条用例的事件
  await expect(
    page.getByText(/调用模型|调用 webui_run_spec|runner-001 开始/).first(),
  ).toBeVisible({ timeout: 90_000 });
  await page.screenshot({ path: "artifacts/11-eval-live-running.png", fullPage: true });

  // 跑完：实时面板收起，答案交给表头与用例表——
  // 「用例 1/1」来自批次详情接口（不是进度接口）：detail 的轮询在状态翻成终态
  // 时就停了，这里能变说明跑完那刻补拉了一次，否则它会永远停在「0/1」。
  await expect(page.getByText("用例 1/1").first()).toBeVisible({ timeout: 360_000 });
  await expect(page.locator("table").last().getByText("runner-001").first())
    .toBeVisible({ timeout: 20_000 });
  // 用例行真的落库了（跑一条落一条，而不是整轮结束才一次性写）
  await expect(page.getByText(/task_output_match/).first()).toBeVisible({ timeout: 20_000 });
  await page.screenshot({ path: "artifacts/12-eval-live-finished.png", fullPage: true });

  // 终态：批次记录不再是"运行中"
  const detail = await api.get(`/api/v2/eval/batches/${batchId}`, {
    headers: { "X-Auth-Token": token },
  });
  const payload = (await detail.json()).data as { status: string; done_cases: number };
  expect(payload.status, "批次应已收敛到终态").not.toBe("running");
  expect(payload.done_cases, "用例行应已落库").toBe(1);
  await api.dispose();
});
