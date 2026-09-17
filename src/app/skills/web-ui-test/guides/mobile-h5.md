# H5 / 移动站点专项

移动站（如 `m.douban.com`）和桌面站有几个容易踩的差异。

## 设备模拟

`webui_run_spec` 默认注入 `device: 'iPhone 13'`，它带来的是一整套：

| 属性 | 值 |
|---|---|
| viewport | 390 × 664 |
| userAgent | iPhone Safari UA |
| deviceScaleFactor | 3 |
| isMobile | true |
| hasTouch | true |

**为什么必须带 UA**：很多站点靠 UA 判断 `m.` 域名要返回哪个版本；
不带 UA 可能拿到桌面版 DOM，选择器全军覆没。

想看**桌面版**时用 `desktop: true`（`webui_run_spec` 的参数），它会完全不注入设备模拟；
也可以把 `options.device` 这个键整个去掉。注意不要用 `device: ""` 表达桌面——
在工具层那和「没指定」是同一个意思，会被平台默认值（iPhone 13）接管。

常用设备名：`iPhone 13`、`iPhone SE`、`Pixel 5`、`Galaxy S9+`、`iPad Mini`。
完整列表见 Playwright `devices` 导出。

## 带 UA + 语言

站点返回中文还是英文常由 `Accept-Language` 决定。要固定中文：

```json
{ "device": "iPhone 13", "locale": "zh-CN" }
```

`locale` 是 `webui_run_spec` 的独立参数（如 `locale="zh-CN"`），会注入到浏览器上下文；
入库的用例则写在 `options` 里（Web 页的编辑器也提供设备/浏览器选择）。
`browsers` 参数可传 `["chromium","webkit"]` 做浏览器矩阵。

## 骨架屏与懒加载

H5 站首屏常是「骨架屏 → 数据填充」，且图片/内容区滚动才加载。

```typescript
await page.goto('/movie/')
// 等骨架屏消失比等固定时间靠谱
await expect(page.locator('[class*="skeleton"], [class*="loading"]').first())
  .toBeHidden({ timeout: 20000 })
  .catch(() => {})          // 有些站没有骨架屏，等不到属正常
await expect(page.locator('[class*="subject-item"]').first()).toBeVisible()
```

**无限滚动**：断言「列表长度随滚动增加」这类行为：

```typescript
const items = page.locator('[class*="subject-item"]')
const before = await items.count()
await page.mouse.wheel(0, 3000)
await page.waitForTimeout(1500)                   // 滚动触发加载，这里只能硬等一小段
const after = await items.count()
expect(after).toBeGreaterThanOrEqual(before)      // 只断言「不减少」，不断言具体增量
```

滚动加载是少数**允许** `waitForTimeout` 的场景——因为没有可等待的事件目标。
但时间要短（≤2000ms），且断言要宽松。

## 底部 tab bar / 悬浮按钮遮挡

移动站普遍有固定底栏。它盖在内容之上，`click()` 会报
「element is not visible / intercepted」。

```typescript
// 只验证存在与文本 → 用 toBeVisible()，它不要求元素可点
await expect(page.locator('[class*="tab"]')).toBeVisible()

// 真要点：先滚到视口中间
await locator.scrollIntoViewIfNeeded()
await locator.click({ timeout: 10000 })
```

## 同一页面有两套 DOM

响应式站点常同时渲染移动版和桌面版节点，用 CSS toggle 切换。
`locator.count()` 会把隐藏的也数进去。

```typescript
// 用 :visible 过滤
const cards = page.locator('[class*="subject-item"]:visible')
```

## 外链跳转

H5 站点击卡片常跳到 App 或新标签页。断言跳转要看 URL 而不是页面上有没有内容：

```typescript
const [popup] = await Promise.all([
  page.waitForEvent('popup'),
  card.click(),
])
await popup.waitForLoadState('domcontentloaded')
await expect(popup).toHaveURL(/subject/)
```

或者在点击前记录 `page.url()`，点击后断言 `page.url()` 变化。

## 常见 H5 反爬与对策

| 现象 | 对策 |
|---|---|
| 首屏白屏很久 | 加 `waitForLoadState('domcontentloaded')` + 大 `timeout` |
| 直接 403 / 跳验证码 | 该路径不适合自动化，用例标 `test.fixme('站点反爬')` 并如实报告 |
| 内容按地理位置不同 | 断言结构不断言具体条目 |
| 字体/图片 404 但不影响断言 | 忽略，不要在用例里断言图片能加载 |
