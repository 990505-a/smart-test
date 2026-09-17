/**
 * 评测集在页面上的增删改（浏览器级验收）。
 *
 * 起因：评测集原本只能手写 `datasets/*.yaml`——缩进、块标量、字段名全靠记，
 * 写错一个缩进要等跑批次才发现。现在页面上能建、能改、能删，而**文件仍是唯一
 * 事实源**：保存要真的落盘、下拉里要立刻能选到、删除要真的把文件删掉。
 * 这三件事只测接口测不出来（接口 200 不等于界面上有），所以走浏览器。
 *
 * 这条用例不跑 agent，只验"写用例"这一步，几秒就能跑完。
 */

import { test, expect, type Page } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

const BASE = process.env.WEBUI_BASE ?? "http://127.0.0.1:5013";
const API = process.env.WEBUI_API ?? "http://127.0.0.1:5012";
const USER = process.env.WEBUI_USER ?? "";
const PASS = process.env.WEBUI_PASS ?? "";
const FILE = "acceptance-dataset.yaml";
const DATASETS_DIR = join(process.cwd(), "..", "..", "..", "datasets");
const DISK = join(DATASETS_DIR, FILE);

test.describe.configure({ mode: "serial" });
test.use({ viewport: { width: 1512, height: 950 }, locale: "zh-CN" });

async function login(page: Page): Promise<void> {
  // 平台 2026-09 去掉了登录页：界面不需要登录，直接进工作台。
  // （API 侧的 /auth/login 仍保留，脚本拿 token 的路径见各 spec 里的 api.post）
  await page.goto(`${BASE}/chat`, { waitUntil: "domcontentloaded" });
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 30_000 });
}

test("01 页面上新建 / 编辑 / 删除评测集，文件真的落盘", async ({ page, playwright }) => {
  test.setTimeout(120_000);
  const api = await playwright.request.newContext({ baseURL: API });
  const loginResponse = await api.post("/api/v2/auth/login", {
    data: { username: USER, password: PASS },
  });
  const token = (await loginResponse.json()).data.token as string;
  const headers = { "X-Auth-Token": token };

  try {
    await login(page);
    await page.goto(`${BASE}/eval`, { waitUntil: "domcontentloaded" });
    await expect(page.getByText("评测集（datasets/*.yaml）").first()).toBeVisible({ timeout: 30_000 });
    const list = page.locator("table").first();
    const before = await list.locator("tbody tr").count();

    // --- 新建 ---------------------------------------------------------------
    await page.getByRole("button", { name: /新建评测集/ }).click();
    const dialog = page.locator('[data-slot="dialog-content"]').last();
    await dialog.getByLabel(/文件名/).fill(FILE);
    await dialog.getByLabel(/评测集名 name/).fill("acceptance-dataset");
    await dialog.getByLabel(/说明 description/).fill("验收用例创建的评测集，跑完即删");
    await dialog.getByLabel(/第 1 条用例的 id/).fill("equivalence-001");
    // 故意写成两行：多行文本要落成 YAML 块标量（|），否则满屏转义没法读
    await dialog.getByLabel(/任务（input）/).fill(
      "用一句话说明「等价类划分」在测试设计里的作用。\n只回答一句话，不要展开。");
    await dialog.getByLabel(/答复须包含/).fill("等价类");
    await dialog.getByLabel(/工具报错预算/).fill("0");
    await dialog.getByText("LLM 裁判（judge）").click();
    await dialog.getByLabel(/评审标准/).fill("必须是一句话，且指出等价类划分把输入划成若干等价集合。");
    await page.screenshot({ path: "artifacts/13-dataset-editor.png", fullPage: true });
    await dialog.getByRole("button", { name: "创建" }).click();
    await expect(page.getByText(`已创建 ${FILE}`).first()).toBeVisible({ timeout: 15_000 });

    // 文件真的落盘了，而且是可读的 YAML（块标量、中文不转义、id 没被默认值顶掉）
    expect(existsSync(DISK), "评测集文件应写入 datasets/").toBeTruthy();
    const created = readFileSync(DISK, "utf8");
    expect(created).toContain("name: acceptance-dataset");
    expect(created).toContain("id: equivalence-001");
    expect(created).toContain("input: |-");
    expect(created).toContain("等价类");
    expect(created).toContain("pass: 0.7");
    await expect(list.locator("tbody tr")).toHaveCount(before + 1);

    // --- 编辑：再加一条用例 ---------------------------------------------------
    await page.getByRole("button", { name: `编辑 ${FILE}` }).click();
    await expect(page.getByText(new RegExp(`编辑评测集 · ${FILE}`)).first())
      .toBeVisible({ timeout: 15_000 });
    await page.getByRole("button", { name: /添加用例/ }).click();
    const dialog2 = page.locator('[data-slot="dialog-content"]').last();
    await dialog2.getByLabel(/第 2 条用例的 id/).fill("boundary-002");
    await dialog2.getByLabel(/任务（input）/).nth(1).fill("用一句话说明边界值分析的作用。");
    // 已存在的文件要能看原始 YAML（手改后仍能读回）
    await expect(page.locator("details pre").first()).toContainText("acceptance-dataset");
    await page.getByRole("button", { name: "保存" }).click();
    await expect(page.getByText("已保存").first()).toBeVisible({ timeout: 15_000 });
    await expect(async () => {
      expect(readFileSync(DISK, "utf8")).toContain("boundary-002");
    }).toPass({ timeout: 10_000 });

    // --- 保存后立刻能在「启动测评」里选到（不需要重建镜像）---------------------
    await page.getByRole("button", { name: /启动测评/ }).click();
    await expect(page.getByText("启动测评批次")).toBeVisible();
    await page.locator('[data-slot="select-trigger"]').first().click();
    await expect(page.getByRole("option", { name: /acceptance-dataset/ }).first())
      .toBeVisible({ timeout: 10_000 });
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await page.waitForTimeout(400);
    await page.screenshot({ path: "artifacts/14-dataset-in-picker.png", fullPage: false });

    // --- 删除 ---------------------------------------------------------------
    await page.getByRole("button", { name: `删除 ${FILE}` }).click();
    await expect(page.getByText(`删除「${FILE}」`)).toBeVisible();
    await page.getByRole("button", { name: "删除", exact: true }).click();
    await expect(page.getByText(`已删除 ${FILE}`).first()).toBeVisible({ timeout: 15_000 });
    await expect(async () => {
      expect(existsSync(DISK), "删除后文件不应还在磁盘上").toBeFalsy();
    }).toPass({ timeout: 10_000 });
    await expect(list.locator("tbody tr")).toHaveCount(before);
  } finally {
    // 失败也要把文件清掉，别在 datasets/ 里留垃圾
    if (existsSync(DISK)) {
      await api.delete(`/api/v2/eval/datasets/${FILE}`, { headers });
    }
    await api.dispose();
  }
});
