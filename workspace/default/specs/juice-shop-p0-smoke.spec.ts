import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

const EMAIL = 'admin@juice-sh.op'
const PASSWORD = 'admin123'
const WRONG_PASSWORD = 'WrongPass999'
const PRODUCT = 'Apple Juice (1000ml)'

/** 关闭欢迎横幅与 Cookie 横幅（若出现），避免遮挡被测元素；未出现则忽略 */
async function dismissBanners(page: Page): Promise<void> {
  await page
    .getByRole('button', { name: 'Close Welcome Banner' })
    .click({ timeout: 4000 })
    .catch(() => {})
  await page
    .getByRole('button', { name: 'Me want it!' })
    .click({ timeout: 4000 })
    .catch(() => {})
}

test.describe('Juice Shop P0 冒烟', () => {
  // ── 1. 登录成功（REQ-AUTH-002 / CASE-JS-005）───────────────────────────
  test('REQ-AUTH-002 正确凭据登录成功且出现用户菜单', async ({ page }) => {
    test.setTimeout(90000)
    await page.goto('/#/login')
    const emailInput = page.locator('#email')
    await expect(emailInput).toBeVisible({ timeout: 20000 })
    await dismissBanners(page)

    await emailInput.fill(EMAIL)
    await page.locator('#password').fill(PASSWORD)
    await page.locator('#loginButton').click()

    // 登录成功：会话令牌写入本地存储（v20 登录成功无提示条）
    await page.waitForFunction(() => !!localStorage.getItem('token'), undefined, { timeout: 15000 })
    // 已离开登录页，跳转到搜索页
    await expect(page).toHaveURL(/#\/search/, { timeout: 15000 })

    // 用户菜单出现：展开账户菜单，显示当前登录邮箱与登出入口
    const accountBtn = page.locator('#navbarAccount')
    await expect(accountBtn).toBeVisible()
    await accountBtn.click()
    const menu = page.locator('.cdk-overlay-container')
    await expect(menu.getByText(EMAIL)).toBeVisible({ timeout: 10000 })
    await expect(page.locator('#navbarLogoutButton')).toBeVisible()

    await page.screenshot({ path: 'artifacts/01-登录成功-用户菜单出现.png', fullPage: true })
  })

  // ── 2. 登录失败（REQ-AUTH-002 / CASE-JS-006）───────────────────────────
  test('REQ-AUTH-002 错误密码登录失败且停留在登录页', async ({ page }) => {
    test.setTimeout(90000)
    await page.goto('/#/login')
    const emailInput = page.locator('#email')
    await expect(emailInput).toBeVisible({ timeout: 20000 })
    await dismissBanners(page)

    await emailInput.fill(EMAIL)
    await page.locator('#password').fill(WRONG_PASSWORD)
    await page.locator('#loginButton').click()

    // 出现明确错误提示
    await expect(page.getByText('Invalid email or password.')).toBeVisible({ timeout: 10000 })
    // 仍停留在登录页：URL 不变、表单仍可见、无会话令牌
    await expect(page).toHaveURL(/#\/login/)
    await expect(emailInput).toBeVisible()
    await expect(page.locator('#password')).toBeVisible()
    await expect(page.locator('#loginButton')).toBeVisible()
    expect(await page.evaluate(() => localStorage.getItem('token'))).toBeNull()

    await page.screenshot({ path: 'artifacts/02-登录失败-错误提示且停留登录页.png', fullPage: true })
  })

  // ── 3. 商品搜索（REQ-CAT-002 / CASE-JS-010）────────────────────────────
  test('REQ-CAT-002 搜索apple命中Apple与Pineapple商品且条目数大于0', async ({ page }) => {
    test.setTimeout(90000)
    await page.goto('/#/')
    const searchBox = page.locator('#searchQuery input')
    await expect(searchBox).toBeVisible({ timeout: 20000 })
    await dismissBanners(page)

    await searchBox.fill('apple')
    await searchBox.press('Enter')

    // 已进入搜索结果页
    await expect(page).toHaveURL(/#\/search\?q=apple/, { timeout: 15000 })
    // 本版本商品名渲染在 mat-card .info-box .name
    const names = page.locator('mat-card .info-box .name')
    await expect(names.first()).toBeVisible({ timeout: 15000 })

    // 结果条目数 > 0
    const nameList = await names.allInnerTexts()
    expect(nameList.length).toBeGreaterThan(0)

    // 子串模糊匹配：结果中包含名称含 apple 与 pineapple 的商品（大小写不敏感）
    const lowered = nameList.map((n) => n.toLowerCase())
    expect(lowered.some((n) => n.includes('apple'))).toBe(true)
    expect(lowered.some((n) => n.includes('pineapple'))).toBe(true)
    // 每条结果的名称都应命中关键字（验证确实是 apple 的搜索结果）
    for (const n of lowered) {
      expect(n.includes('apple')).toBe(true)
    }

    console.log(`搜索结果 ${nameList.length} 条:`, nameList.join(' | '))
    await page.screenshot({ path: 'artifacts/03-搜索apple结果.png', fullPage: true })
  })

  // ── 4. 购物车（REQ-CART-001 / CASE-JS-016）────────────────────────────
  test('REQ-CART-001 加入购物车后商品存在且数量为1', async ({ page }) => {
    test.setTimeout(90000)
    await page.goto('/#/')
    await page.locator('mat-card').first().waitFor({ state: 'visible', timeout: 20000 })
    await dismissBanners(page)

    // 商品卡片上的加购按钮（aria-label="Add to Basket"）
    const appleCard = page.locator('mat-card', { hasText: PRODUCT }).first()
    await expect(appleCard).toBeVisible({ timeout: 10000 })

    // 初始角标数量为 0
    const cartBtn = page.getByRole('button', { name: 'Show the shopping cart' })
    await expect(cartBtn).toContainText('0')

    // 加入购物车
    await appleCard.getByRole('button', { name: 'Add to Basket' }).click()

    // 成功反馈提示条出现
    await expect(
      page.getByText(`Placed ${PRODUCT} into basket.`, { exact: false })
    ).toBeVisible({ timeout: 10000 })

    // 角标数量 0 -> 1
    await expect(cartBtn).toContainText('1', { timeout: 10000 })

    // 打开购物车页核对
    await cartBtn.click()
    await expect(page).toHaveURL(/#\/basket/, { timeout: 15000 })

    // 购物车行存在且商品名正确
    const row = page.locator('mat-row', { hasText: PRODUCT })
    await expect(row).toBeVisible({ timeout: 15000 })
    await expect(row.locator('.mat-column-product')).toContainText(PRODUCT)

    // 数量列显示 1
    const qtyText = (await row.locator('.mat-column-quantity span.cell-initial-font').innerText()).trim()
    expect(qtyText).toBe('1')

    // 总价行出现且包含单价 1.99
    await expect(page.getByText(/Total Price:.*1\.99/)).toBeVisible({ timeout: 10000 })

    await page.screenshot({ path: 'artifacts/04-购物车-商品存在数量1.png', fullPage: true })
  })
})
