# Playwright CLI 与 runner 行为说明

## 执行链路

```
webui_run_spec(spec 源码)
      │  HTTP POST /run  { files, spec, options, timeoutMs }
      ▼
playwright-runner (Node sidecar, :5015)
      │  1. 建临时运行目录，写入 spec 文件
      │  2. 软链 node_modules（ESM 不认 NODE_PATH）
      │  3. 生成 playwright.config.mjs（reporter/outputDir/baseURL/device）
      │  4. 执行 `playwright test --config ... <spec>`
      ▼
Playwright CLI：拉起 chromium → 跑 spec → 写 report.json + artifacts
      │  HTTP 200  { ok, exitCode, stats, tests[], artifacts[], stdout, stderr }
      ▼
webui_run_spec 归一化成 status / report / artifacts / output
```

**关键点**：runner 调的就是官方 CLI 二进制（`playwright test` / `playwright screenshot`），
不是 Playwright 的库 API。终端里 `npx playwright test` 能得到的结果，这里都能得到。

## `playwright test` 的退出码

| 退出码 | 含义 | 对应 `status` |
|---|---|---|
| 0 | 全部用例通过（含 skipped） | `passed` |
| 1 | 有用例失败 | `failed` |
| 其它 | CLI 自身错误（配置写错、文件不存在） | `failed`/`error` |
| — | 超时被杀 | `error`（`output` 里带「CLI 超时被杀」） |

`exit_code == 0` 但 `report.tests` 为空 → 通常是 **spec 文件名没被 `testMatch` 命中**。
默认 `testMatch` 是 `**/*.spec.@(js|mjs|ts)` 和 `**/*.test.@(js|mjs|ts)`；
`webui_run_spec` 默认 `spec_file='tests/spec.spec.ts'`，符合该模式。

## runner 注入的 config

调用者只需描述**意图**，不用自己写 config：

| 请求字段 | 作用 | 默认 |
|---|---|---|
| `options.baseURL` | `page.goto('/x')` 的前缀 | `script.target_url` → 平台默认站点 |
| `options.device` | 设备描述符（`iPhone 13`、`Pixel 5`…） | 平台默认（`iPhone 13`）；不传该键 = 桌面 |
| `options.locale` | 语言，影响站点返回的语言版本 | 设备默认（en-US） |
| `options.viewport` | `{width, height}` | 设备默认 |
| `options.browsers` | 浏览器矩阵，如 `["chromium","webkit"]`，每个浏览器一个 project | 只跑 chromium |
| `options.trace` | `on` / `off` / `retain-on-failure` | `retain-on-failure` |
| `options.screenshot` | Playwright 自动截图策略 | `only-on-failure` |
| `options.video` | 失败录像 | `retain-on-failure` |
| `options.htmlReport` | 是否生成官方 HTML 报告（自包含，含 trace 查看器） | 开 |
| `grep` | 只跑标题匹配的用例（CLI `--grep`） | 不过滤 |
| `options.testDir` / `testMatch` | 收集范围 | `.` / `**/*.spec.ts` |
| `testTimeoutMs` | 单条用例超时 | 90000（配置项 `WEB_UI_CASE_TIMEOUT_S`） |
| `timeoutMs` | 整个 CLI 调用的墙钟超时 | 300000（配置项 `WEB_UI_RUN_TIMEOUT_S`） |

自定义 config **不要**通过 spec 源码注入——runner 生成的 config 会被 `--config` 指定，
spec 里再写一份不会生效。需要什么能力就提需求到 `options`。

两个刻意的开关：

- **`forbidOnly: true`**：spec 里残留 `test.only` 会直接报错失败。只留一个 `.only`
  时其余用例会整片消失、而退出码仍是 0 —— 那会把「10 条用例全绿」变成假象。
- **`retries: 0`**：不靠重试把失败糊过去。要判不稳定请用 `--repeat-each` 多跑几次看结果，
  而不是让失败用例重试变绿。

## artifacts（存证）

跑完 run 目录下有三类产物：

- `artifacts/` —— spec 里手动 `screenshot({ path: 'artifacts/x.png' })` 存的文件
- `test-results/` —— Playwright 按策略自动产出的失败截图 / `trace.zip` / `video.webm` /
  `error-context.md`（失败时刻的 ARIA 快照）
- `html-report/` —— 官方 HTML 报告，**自包含**：截图与 trace 都在里面，点开可逐帧回放

`artifacts[].path` 是**相对 run 目录**的路径。平台侧回取走的是平台自己的签名路由
（不是 runner 的内部接口）：

```
GET {平台}/api/v2/web-ui-auto/artifact/{run_id}/{相对路径}?sig={share_sig}   单个产物
GET {平台}/api/v2/web-ui-auto/report/{run_id}/{share_sig}/index.html         官方报告
```

`share_sig` 由执行记录接口下发（`share_sig` 字段）。授权之所以放进 URL，是因为
`<img>` / `<video>` / 新标签页这些请求由浏览器自己发起，带不上自定义请求头；
签名只对那一条执行有效，换成别的 run_id 立刻 403。

## 白名单 CLI

`webui_cli(["<subcommand>", ...])` 只放行**没有专用工具**的三个：
`install` `pdf` `cr`。

`--version` / `screenshot` / `test` 曾经也在白名单里，现已移除——平台分别有
`webui_runner_status` / `webui_screenshot` / `webui_run_spec`，它们返回结构化
结果（CLI 版本 / `dataUri` / JSON 报告 + artifacts 清单），而裸 CLI 只有
stdout。用专用的那个。

`cr`（codegen）产出的是一份"录下来的操作"，选择器质量取决于录制时的点击，
**不能直接当用例用**，必须按 spec 硬性规范重写选择器与断言。

## 排查

| 现象 | 原因 | 处理 |
|---|---|---|
| `无法连接 playwright runner` | sidecar 没起 | compose 里 `playwright` 服务是否 healthy；本机开发跑 `node tools/playwright-runner/server.mjs` |
| `Executable doesn't exist at /ms-playwright/...` | 浏览器未安装/版本不匹配 | 镜像内 `playwright install chromium`；`@playwright/test` 版本须与镜像 tag 一致 |
| `Cannot find module '@playwright/test'` | node_modules 软链没建上 | runner 内部问题，看 runner 日志 |
| `Test not found` / 0 tests | `spec_file` 没匹配 `testMatch` | 文件名以 `.spec.ts` 结尾，或显式传 `options.testMatch` |
| `item focused with '.only' is not allowed` | spec 里留了 `test.only` | 删掉 `.only`（这是 forbidOnly 的预期行为） |
| 截图/视频/trace 打不开（403 或 `ERR_BLOCKED_BY_ORB`） | 签名过期，或 URL 少了 `/api/v2` 前缀 | 用接口下发的 `share_sig` 重新拼；签名默认 7 天有效 |
| 超时 | 站点慢或死等 | 加大 `timeout_s`；检查是否用了 `waitForTimeout` 硬等 |
