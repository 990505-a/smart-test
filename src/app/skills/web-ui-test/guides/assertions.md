# 断言范式

Playwright 的 `expect(locator, ...)` 是 **web-first 断言**：它会自动重试直到超时，
所以它本身就是等待。这是它和「先 `waitForTimeout` 再取文本比较」的本质区别。

## Web-first 断言（必须用这类）

```typescript
await expect(locator).toBeVisible()
await expect(locator).toBeHidden()
await expect(locator).toBeAttached()          // 在 DOM 里，不一定可见
await expect(locator).toHaveText('热映')
await expect(locator).toContainText('评分')
await expect(locator).toHaveCount(5)
await expect(locator).toHaveAttribute('href', /subject/)
await expect(locator).toHaveClass(/active/)
await expect(locator).toBeEnabled()
await expect(page).toHaveTitle(/豆瓣电影/)
await expect(page).toHaveURL(/\/movie\//)
```

每一条都接受 `{ timeout: 15000 }`：站点慢就显式给，不要用 `waitForTimeout` 代替。

## 非重试断言（只用于已经稳定取到的值）

```typescript
const text = await locator.textContent()      // 立即取值，不重试
expect(text?.trim()).toBe('热映')
```

**前提**：取值前已经有 web-first 断言保证了元素就位，否则会拿到 `null`。

```typescript
// ✅ 正确顺序
await expect(page.locator('h1')).toBeVisible()
expect((await page.locator('h1').textContent())?.trim()).toContain('电影')

// ❌ 页面还没渲染完就取，随机失败
expect(await page.locator('h1').textContent()).toContain('电影')
```

## 结构断言 vs 内容断言

**站点数据天天变的**（推荐位、榜单、热映列表）→ 断言结构：

```typescript
const cards = page.locator('[class*="subject-item"]')
await expect(cards.first()).toBeVisible()
expect(await cards.count()).toBeGreaterThan(3)
// 每个卡片得有跳转链接和标题，这是结构契约
await expect(cards.first().locator('a')).toHaveAttribute('href', /subject/)
```

**站点固化的**（导航栏名称、按钮文案、页面标题）→ 断言内容：

```typescript
await expect(page.getByText('电影')).toBeVisible()
await expect(page).toHaveTitle(/电影/)
```

判断标准一句话：**这条内容变了算 bug 吗？** 算 → 内容断言；不算 → 结构断言。

## 等待的正确姿势

```typescript
// ✅ 等元素出现（自带重试）
await expect(page.locator('.loading')).toBeHidden({ timeout: 20000 })

// ✅ 等网络静默（列表页常用）
await page.waitForLoadState('networkidle')

// ✅ 等特定响应（确认数据真的请求了）
await page.waitForResponse((r) => r.url().includes('/api/') && r.status() === 200)

// ✅ 滚动触发懒加载后再断言
await page.locator('footer').scrollIntoViewIfNeeded()
await expect(page.locator('[class*="subject-item"]').last()).toBeVisible()

// ❌ 硬等——慢、不稳、还掩盖真实原因
await page.waitForTimeout(5000)
```

## 断言消息要能自证

失败时 `error` 字段会带上 Playwright 的期望/实际对比，这已经够用。
但如果断言依赖计算，自己补上下文：

```typescript
const count = await items.count()
expect(count, `首页应至少有 4 个影片卡片，实际 ${count}`).toBeGreaterThan(3)
```

## 空态 / 异常态怎么写

空态本身是「没有元素」，直接断言「没有」容易假绿（页面根本没加载完也满足）。
用「先确认页面骨架在了，再确认空态提示在了」两段式：

```typescript
await page.goto('/movie/search?q=zzzzzzzzzzzz')

await expect(page.locator('body')).toBeVisible()          // 骨架在
const empty = page.getByText(/没有找到|暂无|无结果/)
await expect(empty.first()).toBeVisible({ timeout: 15000 })  // 空态提示在
```

## 反模式

```typescript
expect(true).toBe(true)                       // ❌ 空断言，永远通过
await expect(page.locator('div')).toBeVisible()  // ❌ 太宽泛，任何页面都过
try { await expect(x).toBeVisible() } catch {} // ❌ 吞掉失败
test.skip()                                   // ❌ 悄悄跳过，等于没测
```
