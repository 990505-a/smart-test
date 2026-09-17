# 存证规范（artifacts）

用例跑完必须留下可复核的证据。没有存证的「通过」等于「我说通过了」。

## 三类存证

| 类型 | 产生方式 | 用途 |
|---|---|---|
| 截图 | spec 里显式 `screenshot({ path: 'artifacts/…' })` | 断言时刻的页面实际样子 |
| trace | config `trace: 'retain-on-failure'`（默认） | 失败时的完整回放（DOM 快照 + 网络 + 控制台） |
| test-results | Playwright 自动输出目录 | 自动截图 / 视频 |

`webui_run_spec` 返回的 `artifacts[]` 把三类都汇总了，每项是
`{ name, path, size }`，`path` 相对 run 目录。

## 截图命名

用**用例名**，不要用序号：

```typescript
await page.screenshot({ path: 'artifacts/首页-热映列表.png', fullPage: true })
await page.screenshot({ path: 'artifacts/搜索-空态提示.png', fullPage: true })
```

序号（`shot1.png`）过两天就没人知道对应哪条用例，
而用例名能和 `report.tests[].fullTitle`、报告里的条目直接对上。

## 什么时候截

1. **断言之后**——截到的是「断言成立时页面长这样」，这是证据；
   断言之前截得到的是「还没准备好的页面」，证明不了什么。
2. **关键中间态**（可选）——比如滚动后的第二屏、展开的筛选面板。
3. **失败时**——Playwright 的 `screenshot: 'only-on-failure'` 会兜底，
   不用自己写 try/catch。

```typescript
const cards = page.locator('[class*="subject-item"]')
await expect(cards.first()).toBeVisible()
await page.screenshot({ path: 'artifacts/首页-热映列表.png', fullPage: true })  // ✅ 断言后
```

## fullPage 的选择

- `fullPage: true`：截整个滚动区域。列表页、详情页用这个——能看到全部内容。
- `fullPage: false`（默认）：只截视口。验证「首屏长什么样」「某个元素在不在视野内」时用。
- 无限滚动页面 `fullPage: true` 可能截到很长的图（几十 MB）。这类页面改用视口截图，
  或先 `scrollTo(0,0)` 再截。

## 大小与超时

只有「单 URL 截图」(`webui_screenshot`) 会把图内联成 `data_uri` 返回，且限 ≤2MB；
用例执行产生的截图/视频/trace 一律走平台的签名 URL 取回（见下节），不受此限制。
截图默认是 PNG，390×664@3x 的满屏截图约 1–3MB，
`fullPage: true` 的长列表页可能超。需要小图时在 spec 里压：

```typescript
await page.screenshot({ path: 'artifacts/x.jpg', fullPage: true, type: 'jpeg', quality: 70 })
```

## 回取产物

平台侧（后端 / Web 页）通过**平台自己的签名路由**取文件，而不是 runner 的内部接口：

```
GET {平台}/api/v2/web-ui-auto/artifact/{run_id}/{artifacts[].path}?sig={share_sig}
GET {平台}/api/v2/web-ui-auto/report/{run_id}/{share_sig}/index.html   # 官方报告（含 trace 回放）
```

`share_sig` 由执行记录接口下发；`runner_run_id` 也会返回并落库在
`web_ui_script_runs.runner_run_id`，所以历史执行也能回看截图与 trace。
授权放在 URL 里是必须的：`<img>` / `<video>` / 新标签页由浏览器自己发请求，
带不上自定义请求头；签名只对那一条执行有效，默认 7 天过期。

## trace 的用法

`trace: 'retain-on-failure'`（默认）只在失败时保留，`test-results/**/trace.zip`。
用 `playwright show-trace trace.zip` 打开可以逐帧回放——
断言失败时「DOM 当时到底是什么样」一目了然。

需要 success 也留 trace（比如做演示）时传 `options.trace: 'on'`，
但每次 run 会多几 MB，别在批量回归里开。

## 报告里怎么写存证

```
| 用例 | 结果 | 存证 |
|---|---|---|
| 首页展示热映列表 | ✓ | artifacts/首页-热映列表.png |
| 搜索无结果展示空态 | ✓ | artifacts/搜索-空态提示.png |
| 详情页可进入并展示评分 | ✗ 选择器未命中 | test-results/详情页-*/trace.zip |
```

失败用例也要给存证路径——那正是最需要看的东西。
