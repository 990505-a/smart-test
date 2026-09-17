/**
 * Web-UI 自动化页面的浏览器验收（真实驱动我们的前端，不只是打接口）。
 *
 * 为什么要有它：接口返回 200 不代表页面上看得见。下面每一步都断言「用户能看到的
 * 东西」——图表真的画出来了、签名 URL 的截图真的解码成功（naturalWidth > 0）、
 * 官方报告在新标签页里真的渲染出了测试树。每次跑都会留截图到 artifacts/。
 *
 * 运行（宿主机，前端在 5013、后端在 5012）：
 *   WEBUI_USER=admin WEBUI_PASS=xxx \
 *     npx playwright test --config acceptance/playwright.config.ts
 */

import { test, expect, type Page } from "@playwright/test";
import { readFileSync, rmSync } from "node:fs";
import { join } from "node:path";

const BASE = process.env.WEBUI_BASE ?? "http://127.0.0.1:5013";
const USER = process.env.WEBUI_USER ?? "";
const PASS = process.env.WEBUI_PASS ?? "";

test.describe.configure({ mode: "serial" });
test.use({ viewport: { width: 1512, height: 950 }, locale: "zh-CN" });

async function login(page: Page): Promise<void> {
  // 平台 2026-09 去掉了登录页：界面不需要登录，直接进工作台。
  // （API 侧的 /auth/login 仍保留，脚本拿 token 的路径见各 spec 里的 api.post）
  await page.goto(`${BASE}/chat`, { waitUntil: "domcontentloaded" });
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 30_000 });
}

test.beforeEach(async ({ page }) => {
  test.setTimeout(120_000);
  await login(page);
});

test("01 概览卡片与趋势图真的渲染出来了", async ({ page }) => {
  await page.goto(`${BASE}/web-ui-auto`, { waitUntil: "domcontentloaded" });

  await expect(page.getByText("用例脚本").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("用例通过率").first()).toBeVisible();
  await expect(page.getByText("平均单次耗时").first()).toBeVisible();
  // recharts 渲染成 SVG；它没画出来时页面只有空白盒子
  await expect(page.locator(".recharts-surface").first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("失败最多的用例").first()).toBeVisible();

  await page.screenshot({ path: "artifacts/01-overview.png", fullPage: true });
});

test("02 用例库列表：运行环境列、最近结果、搜索筛选", async ({ page }) => {
  await page.goto(`${BASE}/web-ui-auto`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText("Playwright 用例").first()).toBeVisible({ timeout: 30_000 });

  const scriptTable = page.locator("table").first();
  await expect(scriptTable.locator("thead")).toContainText("运行环境");
  await expect(scriptTable.locator("thead")).toContainText("最近结果");
  // 运行环境列要能看出设备（桌面 or iPhone 13）
  await expect(scriptTable.locator("tbody tr").first()).toContainText(/iPhone|桌面|Pixel|iPad/);
  // 最近结果要有结论，而不是「未执行过」
  await expect(scriptTable.locator("tbody tr").first()).toContainText(/通过|失败|错误|异常/);

  // 搜索过滤：用一个必然无结果的词，断言出现空态。
  // （不要用"行数变少"来断言：过滤到空时脚本表格会整个换成空态，
  //   `table.first()` 会滑到下面那张「最近执行」表上去。）
  const search = page.getByPlaceholder("搜索名称 / 模块 / 站点");
  await expect(scriptTable.locator("tbody tr").first()).toBeVisible({ timeout: 15_000 });
  await search.fill("zzz-绝不存在-zzz");
  await expect(page.getByText("没有匹配的用例")).toBeVisible({ timeout: 15_000 });
  await page.screenshot({ path: "artifacts/02-list-search.png", fullPage: true });
  await search.fill("");
  await expect(scriptTable.locator("tbody tr").first()).toBeVisible({ timeout: 15_000 });
});

test("03 编辑器：代码编辑器与修复历史面板", async ({ page }) => {
  await page.goto(`${BASE}/web-ui-auto`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText("Playwright 用例").first()).toBeVisible({ timeout: 30_000 });

  // 点用例名打开编辑器
  await page.locator("table").first().locator("tbody tr").first().locator("button").first().click();
  await expect(page.locator(".cm-editor")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".cm-content")).toContainText("@playwright/test");
  // 设备、浏览器矩阵、录像开关都在
  await expect(page.getByText("设备模拟").first()).toBeVisible();
  await expect(page.getByText("浏览器矩阵").first()).toBeVisible();
  await expect(page.getByText("录像").first()).toBeVisible();
  await expect(page.locator("select").filter({ hasText: "仅失败时保留" })).toHaveCount(1);
  await page.screenshot({ path: "artifacts/03-editor.png", fullPage: false });

  await page.getByRole("button", { name: /修复历史/ }).click();
  await expect(page.getByText(/没有自修复记录|v\d/).first()).toBeVisible({ timeout: 10_000 });
  await page.screenshot({ path: "artifacts/03b-repair-history.png", fullPage: false });
});

test("04 执行详情：失败用例展开、错误定位、截图与 trace 存证", async ({ page }) => {
  await page.goto(`${BASE}/web-ui-auto`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText("最近执行").first()).toBeVisible({ timeout: 30_000 });

  // 最近执行表里第一条（就是刚造的那条失败执行）
  const runsTable = page.locator("table").last();
  await expect(runsTable.locator("tbody tr").first()).toContainText("验收夹具");
  await runsTable.locator("tbody tr").first().getByRole("button", { name: /详情/ }).click();

  await expect(page.getByText(/用例结果（\d+）/)).toBeVisible({ timeout: 20_000 });
  // 失败用例默认展开：应直接看到失败原因与 spec 行号
  await expect(page.getByText("失败原因").first()).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/acceptance-fail\.spec\.ts:\d+/)).toBeVisible();
  await page.screenshot({ path: "artifacts/04-run-detail-failed.png", fullPage: true });

  // 产物：签名 URL 的截图必须真的解码成功
  await page.getByRole("button", { name: /产物存证/ }).click();
  const image = page.locator('img[src*="/artifact/"]').first();
  await expect(image).toBeVisible({ timeout: 20_000 });
  await expect
    .poll(async () => image.evaluate((el) => (el as HTMLImageElement).naturalWidth), {
      timeout: 20_000, message: "截图没有解码成功（签名 URL 可能返回了 403）",
    })
    .toBeGreaterThan(0);
  // 有失败视频与 trace
  await expect(page.locator("video").first()).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/trace\.zip/).first()).toBeVisible();
  await page.screenshot({ path: "artifacts/05-artifacts.png", fullPage: true });
});

test("05 官方报告新标签页打开并渲染测试树 + trace 回放", async ({ page }) => {
  await page.goto(`${BASE}/web-ui-auto`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText("最近执行").first()).toBeVisible({ timeout: 30_000 });

  const runsTable = page.locator("table").last();
  await runsTable.locator("tbody tr").first().getByRole("button", { name: /详情/ }).click();
  await expect(page.getByText(/用例结果（\d+）/)).toBeVisible({ timeout: 20_000 });

  const [report] = await Promise.all([
    page.context().waitForEvent("page"),
    page.getByRole("button", { name: /官方报告/ }).click(),
  ]);
  await report.waitForLoadState("domcontentloaded");
  await expect(report).toHaveTitle(/Playwright/i, { timeout: 30_000 });
  // 报告是 SPA：等它把测试树渲染出来（这一步依赖 data/*.json 相对路径取回成功）
  await expect(report.getByText(/acceptance-fail\.spec\.ts/).first())
    .toBeVisible({ timeout: 30_000 });
  await report.screenshot({ path: "artifacts/06-report.png", fullPage: false });

  // 点开这条用例 → 报告里应出现失败信息与 Trace 入口
  await report.getByText(/故意失败/).first().click();
  await expect(report.getByText(/这段文字不存在/).first()).toBeVisible({ timeout: 20_000 });
  await report.screenshot({ path: "artifacts/07-report-detail.png", fullPage: false });

  // 「View Trace」可能是新标签页，也可能在当前标签页里路由过去，两种都要接住
  const traceLink = report.getByRole("link", { name: /view trace/i }).first();
  await expect(traceLink).toBeVisible({ timeout: 20_000 });
  const popupPromise = report.context().waitForEvent("page", { timeout: 10_000 }).catch(() => null);
  await traceLink.click();
  const popup = await popupPromise;
  const viewer = popup ?? report;
  await viewer.waitForLoadState("domcontentloaded");
  await viewer.waitForTimeout(4000); // trace 查看器要先解析 zip 才画得出时间轴
  await viewer.screenshot({ path: "artifacts/08-trace-viewer.png", fullPage: false });

  // 要么 URL 落在 trace/ 下，要么页面里已经出现查看器自己的区块（Actions/Timeline）
  const traceUrl = viewer.url();
  const hasTraceChrome = await viewer
    .getByText(/Actions|Timeline|Metadata/)
    .first()
    .isVisible()
    .catch(() => false);
  expect
    .soft(traceUrl.includes("trace") || hasTraceChrome, `trace 查看器未就绪：url=${traceUrl}`)
    .toBeTruthy();
});

test("06 分享链接：全新浏览器上下文（无登录态）也能打开报告", async ({ browser, playwright }) => {
  // 走接口拿到签名（拿到签名的前提是已登录，这里用独立请求上下文登录）
  const api = await playwright.request.newContext({
    baseURL: process.env.WEBUI_API ?? "http://127.0.0.1:5012",
  });
  const loginResponse = await api.post("/api/v2/auth/login", {
    data: { username: USER, password: PASS },
  });
  expect(loginResponse.ok()).toBeTruthy();
  const token = (await loginResponse.json()).data.token as string;

  const runsResponse = await api.get("/api/v2/web-ui-auto/runs?limit=1", {
    headers: { "X-Auth-Token": token },
  });
  const run = (await runsResponse.json()).data[0] as { id: string; share_sig: string };
  const reportUrl = `${process.env.WEBUI_API ?? "http://127.0.0.1:5012"}`
    + `/api/v2/web-ui-auto/report/${run.id}/${run.share_sig}/index.html`;

  // 干净上下文：没有平台 token、没有 localStorage
  const anonymous = await browser.newContext();
  const page = await anonymous.newPage();
  await page.goto(reportUrl, { waitUntil: "domcontentloaded" });
  await expect(page).toHaveTitle(/Playwright/i, { timeout: 30_000 });
  await expect(page.getByText(/acceptance-fail\.spec\.ts/).first())
    .toBeVisible({ timeout: 30_000 });
  await page.screenshot({ path: "artifacts/09-shared-report-anonymous.png", fullPage: false });

  // 签名被改动过就必须 403
  const tampered = await page.request.get(reportUrl.replace(run.share_sig, "1700000000.deadbeef"));
  expect(tampered.status()).toBe(403);

  await anonymous.close();
  await api.dispose();
});

test("07 执行中能看到实时进度，跑完能收敛", async ({ page }) => {
  // 覆盖用户最直接的疑问：点了「执行」之后前端是不是一片空白。
  // 现在执行前会先落一条 running 记录，进度由 sidecar 边跑边写进运行目录。
  await page.goto(`${BASE}/web-ui-auto`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText("Playwright 用例").first()).toBeVisible({ timeout: 30_000 });

  // 用夹具自己的冒烟脚本：清空过数据的环境里，用例库是空的，
  // 依赖用户脚本的验收会在"干净环境"下直接失败（踩过）。
  const fixture = JSON.parse(
    readFileSync(join(test.info().config.rootDir, "artifacts", "fixture.json"), "utf8"),
  ) as { smokeName: string };
  const scriptTable = page.locator("table").first();
  const row = scriptTable.locator("tbody tr").filter({ hasText: fixture.smokeName }).first();
  await expect(row).toBeVisible({ timeout: 15_000 });
  await row.getByRole("button", { name: /^执行$/ }).click();

  // 1) 列表里立刻出现「运行中」——用户不用等结果出来才知道在跑
  await expect(row.getByText("运行中").first()).toBeVisible({ timeout: 25_000 });
  await page.screenshot({ path: "artifacts/14-running-list.png", fullPage: true });

  // 2) 从「历史」弹窗进详情看实时进度。
  //    不走行内那个「最近结果」按钮：它所在单元格被轮询不断重绘，
  //    Playwright 的可点击性检查要等元素稳定，可能一直等到用例跑完。
  await row.getByRole("button", { name: "历史" }).click();
  const runningRow = page.locator("table").last().locator("tbody tr").first();
  await expect(runningRow).toContainText("进行中");
  await runningRow.click();

  await expect(page.getByText("正在执行").first()).toBeVisible({ timeout: 25_000 });
  await expect(page.getByText(/用例 \d+\/\d+/).first()).toBeVisible({ timeout: 25_000 });
  await expect(page.getByText("CLI 输出（实时尾部）")).toBeVisible();
  await page.screenshot({ path: "artifacts/15-running-progress.png", fullPage: false });

  // 3) 进度必须真的在动：已完成数会从 0 涨上去
  await expect
    .poll(async () => {
      const text = await page.getByText(/用例 \d+\/\d+/).first().innerText();
      const match = text.match(/用例 (\d+)\/(\d+)/);
      return match ? Number(match[1]) : 0;
    }, { timeout: 60_000, message: "进度一直停在 0，说明没有实时数据" })
    .toBeGreaterThan(0);

  // 4) 跑完收敛：进度面板消失，用例结果出来
  await expect(page.getByText("正在执行")).toHaveCount(0, { timeout: 120_000 });
  await expect(page.getByText(/用例结果（\d+）/)).toBeVisible({ timeout: 30_000 });
  await page.screenshot({ path: "artifacts/16-finished.png", fullPage: false });
});

test("08 录像可播放、可拖动进度条", async ({ page }) => {
  // 失败用例会留下 video.webm；能播不等于能拖——拖动依赖服务端支持 Range 请求
  const fixture = JSON.parse(
    readFileSync(join(test.info().config.rootDir, "artifacts", "fixture.json"), "utf8"),
  ) as { name: string };
  await page.goto(`${BASE}/web-ui-auto`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText("最近执行").first()).toBeVisible({ timeout: 30_000 });
  const runsTable = page.locator("table").last();
  await runsTable.locator("tbody tr").filter({ hasText: fixture.name })
    .first().getByRole("button", { name: /详情/ }).click();
  await expect(page.getByText(/用例结果（\d+）/)).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: /产物存证/ }).click();

  const video = page.locator("video").first();
  await expect(video).toBeVisible({ timeout: 20_000 });
  await expect
    .poll(async () => video.evaluate((v) => (v as HTMLVideoElement).readyState), {
      timeout: 20_000, message: "录像一直没加载出元数据",
    })
    .toBeGreaterThan(0);

  const meta = await video.evaluate((v) => {
    const el = v as HTMLVideoElement;
    return {
      duration: el.duration,
      seekable: el.seekable.length,
      error: el.error?.message ?? null,
    };
  });
  expect(meta.error, "video 元素报错").toBeNull();
  expect(meta.seekable, "整段可拖动（Range 请求支持）").toBeGreaterThan(0);

  await video.evaluate((v) => { (v as HTMLVideoElement).currentTime = 1; });
  await page.waitForTimeout(700);
  expect(await video.evaluate((v) => (v as HTMLVideoElement).currentTime))
    .toBeGreaterThan(0.8);
  await page.screenshot({ path: "artifacts/13-video-playback.png", fullPage: false });
});

test("09 产物被清理时如实告知，而不是画一堆破图", async ({ page, playwright }) => {
  // 这条用例的由来：一次误删把运行目录删掉了，页面照旧渲染缩略图，用户只看到
  // 一片破图和 alt 文本，完全不知道发生了什么。产物缺失必须由界面说清楚。
  // 放在最后跑：前面几条需要真实的产物。
  // 这个包是 ESM：没有 __dirname，用 Playwright 给出来的 rootDir
  const rootDir = test.info().config.rootDir;
  const fixture = JSON.parse(
    readFileSync(join(rootDir, "artifacts", "fixture.json"), "utf8"),
  ) as { runId: string; name: string };

  const api = await playwright.request.newContext({
    baseURL: process.env.WEBUI_API ?? "http://127.0.0.1:5012",
  });
  const login = await api.post("/api/v2/auth/login", {
    data: { username: USER, password: PASS },
  });
  const token = (await login.json()).data.token as string;
  const runs = await api.get("/api/v2/web-ui-auto/runs?limit=20", {
    headers: { "X-Auth-Token": token },
  });
  const run = (await runs.json()).data.find(
    (item: { id: string }) => item.id === fixture.runId,
  ) as { runner_run_id: string } | undefined;
  expect(run, "找不到夹具执行记录").toBeTruthy();

  // 模拟清理：把这条执行的运行目录删掉（夹具是消耗品，删了不影响平台数据）
  const runsRoot = join(rootDir, "..", "..", "..", "workspace", "default",
                        "web-ui-auto", "runs");
  rmSync(join(runsRoot, run!.runner_run_id), { recursive: true, force: true });
  await api.dispose();

  await page.goto(`${BASE}/web-ui-auto`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText("最近执行").first()).toBeVisible({ timeout: 30_000 });
  const runsTable = page.locator("table").last();
  await runsTable.locator("tbody tr").filter({ hasText: fixture.name })
    .first().getByRole("button", { name: /详情/ }).click();
  await expect(page.getByText(/用例结果（\d+）/)).toBeVisible({ timeout: 20_000 });

  // 详情里必须出现「产物已被清理」的说明，且不再渲染任何指向已删产物的图片
  await expect(page.getByText(/产物文件已不在服务器上/).first()).toBeVisible({
    timeout: 15_000,
  });
  await page.getByRole("button", { name: /产物存证/ }).click();
  await expect(page.getByText(/产物文件已不在服务器上/).first()).toBeVisible();
  expect(await page.locator('img[src*="/artifact/"]').count(), "不应再有指向已删产物的图片")
    .toBe(0);
  await page.screenshot({ path: "artifacts/10-artifacts-pruned.png", fullPage: true });

  // 用例明细本身仍然有效：只有存证没了，执行结论还在
  await page.getByRole("button", { name: /用例结果/ }).click();
  await expect(page.getByText(/故意失败/).first()).toBeVisible({ timeout: 10_000 });
});

test("10 测评页的 Langfuse trace 链接是可打开的（带项目段）", async ({ page }) => {
  // 背景：Langfuse 的界面路由是 /project/<projectId>/traces/<traceId>。
  // 之前这里硬编码了空项目 id，生成的是 /traces/... —— 一条必然 404 的链接，
  // 而且点开才发现，页面上完全看不出来。
  await page.goto(`${BASE}/eval`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText("智能体测评")).toBeVisible({ timeout: 30_000 });

  const detailButton = page.getByRole("button", { name: "详情" }).first();
  await expect(detailButton).toBeVisible({ timeout: 30_000 });
  await detailButton.click();

  const traceLink = page.locator('a[href*="/traces/"]').first();
  await expect(traceLink).toBeVisible({ timeout: 30_000 });
  const href = await traceLink.getAttribute("href");
  expect(href, "trace 链接必须带 /project/<id>/ 前缀，否则 Langfuse 会 404")
    .toMatch(/\/project\/[^/]+\/traces\/[0-9a-f]+/);
  // 必须是宿主浏览器能解析的地址（容器内的 host.docker.internal 要换掉）
  expect(href).not.toContain("host.docker.internal");
  console.log("trace 链接:", href);
});

test("11 设置页能看/测 Langfuse 配置", async ({ page }) => {
  // 背景：Langfuse 的 key 以前只能改 .env（进容器改文件），设置页没有入口；
  // 更麻烦的是配错了没人知道——测评照旧显示"通过"，但一条 trace 都没上报。
  await page.goto(`${BASE}/settings`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText("Langfuse（测评追踪）")).toBeVisible({ timeout: 30_000 });

  // 地址显示的是宿主视角（能在浏览器里直接打开的那个），不是容器内的 host.docker.internal
  const baseUrl = page.locator("#langfuse_base_url");
  await expect(baseUrl).toBeVisible();
  const shown = await baseUrl.inputValue();
  expect(shown, "设置页应显示宿主可用的地址").not.toContain("host.docker.internal");
  expect(shown).toMatch(/^https?:\/\//);

  // secret 只回显掩码，不回显真值
  expect(await page.locator("#langfuse_secret_key").inputValue()).toMatch(/^\*+$/);
  // public key 可见，方便核对是哪个项目的 key
  expect(await page.locator("#langfuse_public_key").inputValue()).toContain("pk-lf-");

  // 模型设置里也有一个「测试连通」，所以要限定在 Langfuse 这张卡片内点
  const card = page.locator("#langfuse_base_url").locator("xpath=ancestor::div[@data-slot='card'][1]");
  await card.getByRole("button", { name: "测试连通" }).click();
  // 成功时 toast 里带项目名/项目 id —— 就是 trace 链接要用到的那个 id
  await expect(page.getByText(/连通正常/)).toBeVisible({ timeout: 30_000 });
  await page.screenshot({ path: "artifacts/18-settings-langfuse.png", fullPage: false });
});

test("12 设置页能看/测 LLM 裁判配置，并说清它是不是继承来的", async ({ page }) => {
  // 背景：judge 原来只能改 .env，设置页没有任何入口；测评页卡片上写着
  // "judge：glm-4.7"，用户翻遍设置也找不到在哪配——因为那是**回退**到主 LLM 的值。
  // 现在要求：卡片必须显示"当前实际使用哪个模型、是独立配置还是继承"。
  await page.goto(`${BASE}/settings`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText("LLM 裁判（测评打分）")).toBeVisible({ timeout: 30_000 });

  const card = page.locator("#judge_model").locator("xpath=ancestor::div[@data-slot='card'][1]");
  const text = await card.innerText();
  expect(text, "卡片必须写出实际生效的模型").toMatch(/当前实际使用：\S+/);
  expect(text, "卡片必须说明来源（独立配置 / 继承主 LLM）").toMatch(/独立配置|继承主 LLM/);
  // 留空即继承，这点必须写在占位符里，否则用户会以为"空 = 没配"
  expect(await page.locator("#judge_model").getAttribute("placeholder")).toContain("继承主 LLM");
  // API Key 同样只回显掩码（留空时是空串，配过则是 ********）
  const keyShown = await page.locator("#judge_api_key").inputValue();
  expect(keyShown === "" || /^\*+$/.test(keyShown), "API Key 不能回显真值").toBeTruthy();

  // 自检走的是真实打分通道（JSON 模式），成功时 toast 会带上模型与来源
  await card.getByRole("button", { name: "测试连通" }).click();
  await expect(page.getByText(/裁判可用/)).toBeVisible({ timeout: 60_000 });
  await page.screenshot({ path: "artifacts/19-settings-judge.png", fullPage: false });

  // 测评页也要说明来源，否则同一个困惑会从另一边再来一次
  await page.goto(`${BASE}/eval`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText(/judge：/).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/继承主 LLM|独立配置/).first()).toBeVisible({ timeout: 30_000 });
});
