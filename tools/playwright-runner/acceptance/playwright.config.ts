import { defineConfig } from "@playwright/test";

/**
 * 验收用例的配置：单 worker、失败留 trace 与截图。
 * 产物落在 acceptance/artifacts/，跑完可以直接按文件名对照验收项。
 */
export default defineConfig({
  testDir: ".",
  globalSetup: "./global-setup.ts",
  globalTeardown: "./global-teardown.ts",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  workers: 1,
  retries: 0,
  forbidOnly: true,
  reporter: [["list"], ["html", { outputFolder: "artifacts/html-report", open: "never" }]],
  outputDir: "artifacts/test-results",
  use: {
    browserName: "chromium",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    actionTimeout: 20_000,
  },
});
