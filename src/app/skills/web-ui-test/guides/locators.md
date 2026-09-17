# 选择器策略（locator）

选择器的稳健性直接决定用例是「资产」还是「负担」。优先级从高到低：

## 1. 语义角色（首选）

```typescript
page.getByRole('button', { name: '搜索' })
page.getByRole('link', { name: /详情/ })
page.getByRole('heading', { level: 1 })
page.getByRole('textbox', { name: '关键词' })
```

无障碍角色 + 可访问名，最接近「用户怎么找到它」，站点改样式不会挂。

## 2. 文本内容

```typescript
page.getByText('热映')
page.getByText('暂无数据', { exact: true })
page.locator('a', { hasText: '查看更多' })
```

适合文案稳定的入口。文案本身是需求的一部分时，用文本定位反而**更好**——
文案变了本来就应该报警。

## 3. 测试专用属性

```typescript
page.getByTestId('movie-card')        // data-testid="movie-card"
page.locator('[data-testid="rating"]')
```

站点自带的 `data-*` 也属于这一档：`[data-subject-id]`、`[data-role="title"]`。

## 4. 结构 + 类名组合（H5 站点的现实选择）

移动站往往没有语义 role 也没有 testid，退而求其次：

```typescript
// 类名含稳定片段（很多站点有 hash 后缀，用 *= 匹配）
page.locator('[class*="subject-item"]').first()
page.locator('ul li a[href*="/subject/"]')
```

要点：
- 用 `[class*="x"]` 而不是 `.x-hash123`（hash 会变）
- 用 `[href*="/movie/subject/"]` 这类**路由特征**定位，比类名更稳
- 加 `.first()` / `.nth(0)` 只在你确实只要第一个时才加，不要用它来「碰运气」

## 5. 兜底：先侦察再定位

**不确定结构时不要猜。** 写一条侦察 spec 把真实 DOM 打出来：

```typescript
test('侦察首页结构', async ({ page }) => {
  await page.goto('/movie/')
  await page.waitForLoadState('domcontentloaded')

  // console.log 的内容会出现在 webui_run_spec 的 output 里
  const links = await page.locator('a[href*="/subject/"]').all()
  console.log('subject 链接数:', links.length)
  for (const link of links.slice(0, 5)) {
    console.log('  href=', await link.getAttribute('href'),
                ' text=', (await link.textContent())?.trim().slice(0, 30))
  }
  const headings = await page.locator('h1,h2,h3').allTextContents()
  console.log('标题:', JSON.stringify(headings.slice(0, 10)))
})
```

拿到真实结构再写正式用例，比「写-跑-挂-猜」循环快得多。

## 反例（禁止）

```typescript
// ❌ 位置依赖：插入一个元素就全错位
page.locator('div > div:nth-child(3) > ul > li:nth-child(2)')

// ❌ 长 XPath
page.locator('/html/body/div[2]/div[3]/ul/li[1]/a')

// ❌ 依赖自动生成的 hash 类名
page.locator('.css-1x2y3z')

// ❌ 用可见文本当唯一锚点但文本来自数据（片名天天变）
page.getByText('肖申克的救赎')
```

最后一条的正确做法是断言**结构**：这个容器存在、里面有 N 个条目、每个条目有

```typescript
const cards = page.locator('[class*="subject-item"]')
await expect(cards.first()).toBeVisible()
expect(await cards.count()).toBeGreaterThan(3)
```

## 定位多个：先 `count()` 再 `nth()`

```typescript
const items = page.locator('[class*="subject-item"]')
await expect(items.first()).toBeVisible()      // 先等出现，count() 才有意义
const total = await items.count()
await items.nth(Math.min(2, total - 1)).click()
```

## 移动站的坑

- **触屏 vs 鼠标**：`device: 'iPhone 13'` 会带 `hasTouch: true`。
  `.click()` 仍然可用，但下拉菜单、hover 提示在触屏设备上不存在，别断言它们。
- **元素被遮挡**：底部 tab bar / 悬浮按钮常盖住内容。断言可见性用
  `toBeVisible()`（不要求可点击）；只有真要点才用 `click()`，必要时
  `await locator.scrollIntoViewIfNeeded()` 先滚动到视口内。
- **`:visible` 伪类**：`page.locator('.x:visible')` 可过滤掉 `display:none` 的重复节点
  （移动站经常同时渲染隐藏的桌面版 DOM）。
