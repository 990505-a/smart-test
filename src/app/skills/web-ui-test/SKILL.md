---
name: web-ui-test
description: Web/H5 站点浏览器 UI 自动化测试技能。用 Playwright CLI 编写并执行 UI 用例：定位元素、点击输入、断言文本/数量/可见性、截图与 trace 存证。当用户要求对浏览器网页做 UI 自动化、写 Playwright 用例、验证某个网页功能是否正常、做 H5 站点的端到端测试时触发。不适用于游戏客户端（走 unity-auto-test）和纯 HTTP 接口（走接口自动化）。
---

# Web-UI Auto Test（Playwright CLI）

对浏览器站点做 UI 自动化的方法论与工具说明。执行引擎是**官方 Playwright CLI**，
由平台的 `playwright-runner` sidecar 承载（后端无 Node 运行时，故隔离成独立服务）。

## 核心理念

和 Unity 自动化同一套范式，只是作用对象从游戏控件换成浏览器 DOM：

```
定位（locator） → 操作（action） → 断言（assert） → 存证（screenshot/trace）
```

**用例的成败只在断言**。没有断言的 spec 是一串会自己通过的空操作；
为了让用例变绿而删断言，比用例失败更糟。

## 技能目录结构

以下路径均**相对于本 SKILL.md 所在目录**（下称 `SKILL_DIR`）。

```
SKILL_DIR/
├── SKILL.md                    ← 本文件
└── guides/                     ← 按需阅读，不要一次读完
    ├── playwright-cli.md       # CLI 与 runner 的行为、退出码、报告结构
    ├── locators.md             # 选择器策略（稳健定位的优先级与反例）
    ├── assertions.md           # 断言范式（web-first 断言、等待、反模式）
    ├── mobile-h5.md            # H5/移动站点专项（设备模拟、无限滚动、懒加载）
    └── artifacts.md            # 存证规范（截图/trace 命名与存放）
```

## 工具面

| 工具 | 用途 |
|---|---|
| `webui_runner_status` | 探活：CLI 版本 + 已装浏览器。**任何执行前先调** |
| `webui_generate_spec` | 自然语言测试意图 → spec 初稿（不执行） |
| `webui_run_spec` | **核心**：执行 spec 源码，回结构化结果 |
| `webui_screenshot` | 单 URL 截图。返回 `dataUri`（驼峰）可直接内联看 |
| `webui_cli` | 白名单 CLI 透传，只剩**没有专用工具**的三个：`install` / `pdf` / `cr` |
| `webui_save_script` | 跑通后入库；带 `script_id` 则是**覆盖更新**那条已有脚本 |
| `webui_get_script` | 按 id 读回**完整源码**（改库里的用例前必须先读） |
| `webui_list_scripts` | 列出已入库脚本（只有元数据，拿不到源码） |

> 查版本用 `webui_runner_status`、截图用 `webui_screenshot`、跑用例用
> `webui_run_spec`——别用 `webui_cli` 绕（白名单里已经没有那几个子命令了）。
> 它们返回结构化结果，比读 CLI stdout 可靠。

`webui_run_spec` 的可选参数（都会影响结论，别忽略）：

| 参数 | 说明 |
|---|---|
| `desktop` | `true` = 桌面浏览器（不注入设备模拟）。看桌面版页面必须用它 |
| `device` | 设备描述符，如 `iPhone 13` / `Pixel 5`；留空用平台默认 |
| `browsers` | 浏览器矩阵，如 `["chromium","webkit"]`，每个浏览器一个 project |
| `locale` | 站点语言，如 `zh-CN`（按 Accept-Language 出内容的站点必须给） |
| `grep` | 只跑标题匹配的用例，调试单条用例时用 |
| `spec_file` | spec 在运行目录里的相对路径，必须匹配 `**/*.spec.ts` |

## `webui_run_spec` 的返回结构

```
{
  status: "passed" | "failed" | "error",   # error = runner 不可达/CLI 超时
  exit_code: 0 | 1 | ...,
  report: {
    stats: { expected, unexpected, flaky, skipped, duration },
    tests: [ {
      id, title, fullTitle, file, line, tags, projectName,
      status,                               # passed | failed | skipped | timedOut
      duration, retry,
      error,                                # 失败堆栈（含 Expected/Received）
      errorLocation: { file, line, column },  # 失败在 spec 的第几行
      stdout,                               # spec 里 console.log 的输出
      attachments: [ { name, contentType, path } ]  # 该用例自己的截图/trace/录像
    } ]
  },
  artifacts: [ { name, path, size } ],      # 本次执行的全部产物
  html_report: "html-report",               # 官方 HTML 报告（含 trace 回放）已生成
  output: "✓ 首页加载  [passed, 1234ms]\n..."  # 人读版，含失败位置
}
```

**读结果的顺序**：先看 `status` → 再看 `report.tests[].status` 谁挂了 →
用 `errorLocation` 直接定位到 spec 第几行 → 再看 `error` 与 `output`。
`console.log` 的输出会原样出现在每条用例的 `stdout` 与 `output` 里，
所以「侦察 spec 打印 DOM 再据此写选择器」这条路是通的。

## 标准工作流

1. **探活**：`webui_runner_status`。不可用就停，不要盲跑。
2. **探路**：对目标 URL 先 `webui_screenshot`，确认页面可达、结构符合预期。
   需要知道真实 DOM 结构时，写一条「侦察 spec」把关键元素的 textContent/属性
   打印出来（`console.log` 会进 `output`），而不是凭猜测写选择器。
3. **设计用例**：按页面/模块拆测试点，四类必覆盖：
   - **正常路径**：核心功能可用（列表渲染、详情可进入）
   - **边界**：空结果、超长文本、最后一屏
   - **异常/空态**：404、无数据提示
   - **导航**：跳转与返回，URL 变化是否符合预期
4. **编写 spec**：遵守下面的硬性规范。
5. **执行与修正**：失败 → 读 `output` → 改选择器/断言 → 重跑。重跑预算与平台的
   自动修复预算一致（`WEB_UI_MAX_REPAIR`，默认初次 + 2 轮修正）；仍然失败就如实
   报告，不要无限重试同一份 spec。
6. **交付**：`webui_save_script` 入库；输出中文报告（用例清单、结果、失败原因、存证路径、遗留风险）。

### 改一条已入库的用例

库里的用例要改，**不要新建一份**，否则同一场景会有两条互相漂移的用例：

`webui_list_scripts` 找到 id → `webui_get_script` 读回源码 → 改 →
`webui_run_spec` 验证通过 → 带 `script_id` 调 `webui_save_script` 覆盖
（版本号自动 +1，修复历史保留）。

### 产物路径怎么写进报告

对话页的执行是**临时的、不入库的**：平台签不出分享链接（签名 URL 只对
`/web-ui-auto` 页里那些有执行记录的运行有效）。所以报告里写**运行目录相对路径**
即可（如 `artifacts/首页-热映列表.png`、`test-results/详情页/trace.zip`），
不要输出 `/api/v2/web-ui-auto/artifact/...` 这类地址。需要可分享的链接，
就用 `/web-ui-auto` 页把脚本跑一遍，那边的每次执行都有记录和签名 URL。

## spec 硬性规范

```typescript
import { test, expect } from '@playwright/test'

test.describe('豆瓣电影 · 首页', () => {
  test('首页应展示热映影片列表', async ({ page }) => {
    test.setTimeout(60000)
    await page.goto('/movie/')                       // 相对路径！baseURL 由 runner 注入

    const firstCard = page.locator('[class*="movie"]').first()
    await expect(firstCard).toBeVisible({ timeout: 15000 })

    await page.screenshot({ path: 'artifacts/首页-热映列表.png', fullPage: true })
  })
})
```

1. `import { test, expect } from '@playwright/test'` —— 少一个都会导致 whole file 报错。
2. **相对路径 goto**：`page.goto('/movie/')`。绝对域名在换环境时会失效，
   而且 runner 的 `baseURL` 就是为了消除这个重复。
3. **一用例一断言主题**：一条 `test()` 只验证一件事；拆细比写长更好定位。
4. **不用 `waitForTimeout` 硬等**。Playwright 的 `expect(...)` 自带重试轮询，
   `await expect(locator).toBeVisible()` 本身就是等待。硬等既慢又不稳。
5. **每条用例至少一张截图**：`await page.screenshot({ path: 'artifacts/<用例名>.png', fullPage: true })`。
6. 用例名用中文，描述「测什么」而不是「做什么操作」：
   `'搜索无结果时应展示空态提示'` ✅ / `'输入关键词'` ❌
7. 用例之间独立：不共享可变状态、不依赖执行顺序。
8. **不要用 `test.only` / `test.skip` 调试**。执行器开了 `forbidOnly`，
   残留 `.only` 会直接判失败；`.skip` 则让用例根本不产生结论——
   两者都会让"跑了多少条"这件事失真。要临时排除用例就如实改断言，别静默跳过。

## 常用断言速查

```typescript
await expect(page).toHaveTitle(/豆瓣电影/)
await expect(page).toHaveURL(/\/movie\//)
await expect(locator).toBeVisible()            // 最常用
await expect(locator).toHaveText('热映')
await expect(locator).toContainText('评分')
await expect(locator).toHaveCount(5)
await expect(locator).toHaveAttribute('href', /subject/)
await expect(locator).toBeEnabled()            // 按钮可点
```

细节与反例见 [guides/assertions.md](guides/assertions.md)。

## 铁律

- **不修改被测站点数据**：只读浏览 + 断言。不发评论、不登录、不下单、不点赞。
- **不删断言换绿**。站点数据本身会波动的（推荐位、榜单），断言「结构存在」
  （`toHaveCount` 大于 0、关键容器可见），不要断言「等于某个具体片名」。
- **失败如实上报**。给用户的报告必须包含失败用例与原因，不能只报通过率。
- **runner 不可用时如实说明**，不要假装执行过。
- **存证要给得出去**：报告平台上的执行记录时，带上 `errorLocation`、
  失败截图/trace 所在的执行记录，以及官方报告入口——「我跑过了」不是证据，
  能点开回放的 trace 才是。
