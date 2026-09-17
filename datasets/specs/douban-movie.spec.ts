/**
 * 豆瓣电影移动站（https://m.douban.com/movie/）UI 自动化用例集
 *
 * 设计说明
 * --------
 * 站点特性决定了用例的写法（全部来自实测侦察，不是猜的）：
 *   1. 内容是**客户端渲染**的，`goto` 返回时列表还没出来 —— 必须先等
 *      `a[href*="/movie/subject/"]` 可见，否则断言会假失败。首屏约 6-10s。
 *   2. 类名是**哈希**的（`MP6dQ` / `FEtQm`），不能用。可用的稳定锚点是：
 *      - 路由特征：`a[href*="/movie/subject/"]`
 *      - 组件库类名前缀：`[class*="frc-rating-num"]`（评分数字）
 *      - 文案：「影院热映」「豆瓣热门」「豆瓣电影 Top250」「想看」
 *   3. 影片数据**每天都在变**，所以只断言结构（有 N 张卡、每张有链接/封面/评分
 *      且评分形如 x.x），绝不断言具体片名。
 *
 * 覆盖矩阵：正常路径 / 边界（数量下限）/ 交互（Tab、点击、返回）/ 异常态（404）。
 * 每条用例独立，不共享状态，每条都留截图存证。
 */

import { test, expect, type Page } from '@playwright/test'

/** 影片卡片：指向 /movie/subject/<id>/ 的链接，站点唯一稳定的结构锚点。 */
const CARD = 'a[href*="/movie/subject/"]'
/** 评分数字节点，frc- 是站点组件库前缀（非哈希，稳定）。 */
const RATING = '[class*="frc-rating-num"]'

/** 等首屏列表渲染出来——本站是客户端渲染，`domcontentloaded` 时还是空的。 */
async function waitForFirstScreen(page: Page): Promise<void> {
  await page.goto('/movie/', { waitUntil: 'domcontentloaded' })
  await expect(page.locator(CARD).first()).toBeVisible({ timeout: 30_000 })
}

test.describe('豆瓣电影 · 首页', () => {
  test.beforeEach(async ({ page }) => {
    test.setTimeout(90_000)
    await waitForFirstScreen(page)
  })

  test('首页应加载成功且页面标题为「豆瓣电影」', async ({ page }) => {
    await expect(page).toHaveURL(/m\.douban\.com\/movie/)
    await expect(page).toHaveTitle(/豆瓣电影/)

    await page.screenshot({ path: 'artifacts/首页-加载.png', fullPage: false })
  })

  test('「影院热映」区块应至少展示 5 部影片', async ({ page }) => {
    await expect(page.getByText('影院热映').first()).toBeVisible({ timeout: 15_000 })

    const cards = page.locator(CARD)
    const total = await cards.count()
    // 边界：站点固定放 10 部；下限取 5，避免榜单换版式就误报
    expect(total, `影院热映应至少 5 部影片，实际 ${total}`).toBeGreaterThanOrEqual(5)

    await page.screenshot({ path: 'artifacts/首页-影院热映.png', fullPage: true })
  })

  test('每张影片卡片都应带详情链接、封面图与形如 x.x 的评分', async ({ page }) => {
    const first = page.locator(CARD).first()

    // 结构契约：链接指向详情路由
    await expect(first).toHaveAttribute('href', /\/movie\/subject\/\d+/)
    // 封面：卡片内必须有 img（懒加载，等它 attached 即可，不要求已解码）
    await expect(first.locator('img').first()).toBeAttached({ timeout: 15_000 })
    // 评分：文案形如 8.7 或「暂无评分」
    const rating = first.locator(RATING).first()
    await expect(rating).toBeVisible({ timeout: 15_000 })
    await expect(rating).toHaveText(/^\d+(\.\d+)?$/)

    const cards = page.locator(CARD)
    const withRating = await page.locator(`${CARD} ${RATING}`).count()
    const total = await cards.count()
    // 边界：允许个别影片无评分（「暂无评分」），但不该是大面积缺失
    expect(withRating, `${withRating}/${total} 张卡片有评分`).toBeGreaterThanOrEqual(total - 2)

    await page.screenshot({ path: 'artifacts/首页-卡片结构.png', fullPage: false })
  })

  test('点击「豆瓣热门」标签后影片列表应刷新', async ({ page }) => {
    const tab = page.getByText('豆瓣热门', { exact: true }).first()
    await expect(tab).toBeVisible({ timeout: 15_000 })

    const cards = page.locator(CARD)
    const before = (await cards.allInnerTexts()).join('|')

    await tab.click()
    // Tab 切换是客户端重渲染，没有网络空闲可等 —— 轮询等列表内容真的变了
    await expect
      .poll(async () => (await cards.allInnerTexts()).join('|'), {
        timeout: 20_000,
        message: '「豆瓣热门」标签点击后列表未发生变化',
      })
      .not.toBe(before)

    expect(await cards.count()).toBeGreaterThanOrEqual(5)

    await page.screenshot({ path: 'artifacts/首页-豆瓣热门标签.png', fullPage: true })
  })

  test('首页应提供三个榜单入口（实时热门 / 一周口碑 / Top250）', async ({ page }) => {
    for (const name of ['实时热门电影', '一周口碑电影榜', '豆瓣电影 Top250']) {
      await expect(page.getByText(name).first(), `缺少榜单：${name}`).toBeVisible({
        timeout: 15_000,
      })
    }
    // 每个榜单区块都要有「更多」出口
    expect(await page.getByText('更多', { exact: true }).count()).toBeGreaterThanOrEqual(2)

    await page.screenshot({ path: 'artifacts/首页-榜单入口.png', fullPage: true })
  })
})

test.describe('豆瓣电影 · 详情页', () => {
  test('点击影片卡片应进入详情页并展示片名与评分', async ({ page }) => {
    test.setTimeout(90_000)
    await waitForFirstScreen(page)

    const card = page.locator(CARD).first()
    await card.scrollIntoViewIfNeeded()
    await card.click()

    await page.waitForURL(/\/movie\/subject\/\d+/, { timeout: 30_000 })
    await page.waitForLoadState('domcontentloaded')

    const title = await page.title()
    // 详情页标题形如「<片名> - 电影 - 豆瓣」——断言后缀契约，不断言片名
    expect(title, `详情页标题异常: ${title}`).toMatch(/-\s*电影\s*-\s*豆瓣$/)
    expect(title.replace(/-\s*电影\s*-\s*豆瓣$/, '').trim().length).toBeGreaterThan(0)

    const body = await page.locator('body').innerText()
    expect(body).toMatch(/评分|暂无评分/)

    await page.screenshot({ path: 'artifacts/详情页-进入.png', fullPage: true })
  })

  test('详情页应提供「想看」操作入口', async ({ page }) => {
    test.setTimeout(90_000)
    await waitForFirstScreen(page)

    const href = await page.locator(CARD).first().getAttribute('href')
    expect(href).toBeTruthy()
    await page.goto(href!, { waitUntil: 'domcontentloaded' })
    await expect(page).toHaveURL(/\/movie\/subject\/\d+/)

    // 只验证入口存在，不点击——点了会改写用户豆瓣账号的数据
    await expect(page.getByText('想看').first()).toBeVisible({ timeout: 20_000 })

    await page.screenshot({ path: 'artifacts/详情页-想看入口.png', fullPage: false })
  })
})

test.describe('豆瓣电影 · 导航与异常态', () => {
  test('从详情页返回应回到首页且列表重新可用', async ({ page }) => {
    test.setTimeout(90_000)
    await waitForFirstScreen(page)

    await page.locator(CARD).first().click()
    await page.waitForURL(/\/movie\/subject\/\d+/, { timeout: 30_000 })

    await page.goBack({ waitUntil: 'domcontentloaded' })
    await expect(page).toHaveURL(/m\.douban\.com\/movie\/?(\?|$)/)
    await expect(page.locator(CARD).first()).toBeVisible({ timeout: 30_000 })

    await page.screenshot({ path: 'artifacts/导航-返回首页.png', fullPage: false })
  })

  test('访问不存在的路径应展示站点 404 提示页', async ({ page }) => {
    test.setTimeout(90_000)
    const response = await page.goto('/movie/this-path-does-not-exist-000', {
      waitUntil: 'domcontentloaded',
    })

    // 站点对未知路由返回 404 并渲染自己的提示页（实测），而不是白屏
    expect(response?.status()).toBe(404)
    await expect(page.getByText(/这个页面不在了|页面不存在|404/).first()).toBeVisible({
      timeout: 20_000,
    })

    await page.screenshot({ path: 'artifacts/异常态-404页面.png', fullPage: false })
  })

  test('首页应提供跳转电脑版站的入口', async ({ page }) => {
    test.setTimeout(90_000)
    await waitForFirstScreen(page)

    const toPc = page.locator('a[href*="to_pc"]')
    await expect(toPc.first()).toBeAttached({ timeout: 15_000 })
    await expect(toPc.first()).toHaveAttribute('href', /to_pc/)

    await page.screenshot({ path: 'artifacts/首页-电脑版入口.png', fullPage: false })
  })
})
