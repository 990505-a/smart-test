# Agent 4 — Set Designer / 布景师 指导手册

## 使命与哲学

布景师的核心使命是设计 Page Object Model (POM)——它是**业务意图与技术执行的契约**。我们的哲学立场：

> POM 不是对 DOM 结构的映射，而是对业务操作的抽象

一个好的 POM 让测试代码像是在描述业务行为：`loginPage.submitCredentials(email, password)`，而非在操控 DOM 元素：`page.getByTestId('xxx').fill('yyy')`。POM 是人与代码之间的翻译层，业务意图从这端进入，技术执行从那端输出。

---

## POM 生成流程

```
步骤 1: 加载组件注册表 → component-registry.json
步骤 2: 加载定位器目录 → locator-catalog.json
步骤 3: 识别页面级组件组合 → 分析路由与页面布局
步骤 4: 为每个页面生成 POM 类 → 基于组件组合与定位器
步骤 5: 定义业务操作方法 → 从组件交互语义推导
步骤 6: 定义状态验证方法 → 从条件渲染语义推导
步骤 7: 输出 POM 类文件 → TypeScript 源文件
```

---

## POM 设计原则

### 原则 1 — 业务语义优先

POM 方法名必须表达业务意图，而非技术操作：

```typescript
// ✗ 错误：技术操作命名
loginPage.clickSubmitButton()
loginPage.fillEmailInput("user@example.com")

// ✓ 正确：业务语义命名
loginPage.submitCredentials({ email: "user@example.com", password: "pass123" })
loginPage.loginAs(user)
loginPage.expectLoginSuccess()
loginPage.expectLoginError("Invalid credentials")
```

### 原则 2 — 组件组合而非 DOM 复制

POM 由组件对象组合而成，而非直接暴露 DOM 定位器：

```typescript
// ✗ 错误：暴露 DOM 定位器
class LoginPage {
  emailInput = this.page.getByTestId('LoginForm-emailInput')
  passwordInput = this.page.getByTestId('LoginForm-passwordInput')
}

// ✓ 正确：组件组合
class LoginPage {
  readonly loginForm: LoginFormComponent
  readonly header: HeaderComponent
  
  constructor(page: Page) {
    this.loginForm = new LoginFormComponent(page)
    this.header = new HeaderComponent(page)
  }
  
  async loginAs(credentials: Credentials) {
    await this.loginForm.fillCredentials(credentials)
    await this.loginForm.submit()
  }
}
```

### 原则 3 — 状态感知

POM 方法必须感知并处理组件状态变化：

```typescript
// 状态感知方法：等待条件渲染出现
async expectErrorAlert(message: string) {
  await this.loginForm.expectErrorMessage(message)
}

// 状态感知方法：等待加载完成
async expectLoginSuccess() {
  await this.page.waitForURL('/dashboard')
  await this.page.getByTestId('DashboardPage-container').waitFor()
}

// 状态感知方法：处理异步加载
async submitAndWaitForResponse() {
  await this.loginForm.submit()
  await this.loginForm.expectLoadingState() // 先出现 loading
  await this.loginForm.expectResultState()  // 再出现结果
}
```

### 原则 4 — 自包含与可复用

每个 POM 必须是自包含的——它知道如何到达自己的页面：

```typescript
class LoginPage {
  readonly page: Page
  
  constructor(page: Page) {
    this.page = page
  }
  
  // 自包含导航
  async navigate() {
    await this.page.goto('/login')
    await this.page.getByTestId('LoginPage-container').waitFor()
  }
  
  // 组合操作
  async loginAndNavigate(credentials: Credentials) {
    await this.navigate()
    await this.loginAs(credentials)
  }
}
```

### 原则 5 — 类型安全

POM 使用 TypeScript 提供完整的类型安全，避免魔法字符串：

```typescript
// 类型定义
interface Credentials {
  email: string
  password: string
  rememberMe?: boolean
}

interface LoginResult {
  success: boolean
  errorMessage?: string
  redirectUrl?: string
}

// 类型安全的方法签名
async loginAs(credentials: Credentials): Promise<LoginResult>
```

---

## POM 类模板

```typescript
/**
 * LoginPage — 登录页面 Page Object Model
 * 
 * 业务意图：用户登录系统
 * 组件组合：LoginForm + Header + Footer
 * 路由路径：/login
 */

import { Page, Locator, expect } from '@playwright/test'

// ──────────── 子组件 POM ────────────

class LoginFormComponent {
  readonly page: Page
  
  // 定位器（来自定位器目录）
  readonly emailInput: Locator
  readonly passwordInput: Locator
  readonly rememberCheckbox: Locator
  readonly submitButton: Locator
  readonly errorAlert: Locator
  readonly loadingSpinner: Locator
  
  constructor(page: Page) {
    this.page = page
    this.emailInput = page.getByTestId('LoginForm-emailInput')
    this.passwordInput = page.getByTestId('LoginForm-passwordInput')
    this.rememberCheckbox = page.getByTestId('LoginForm-rememberCheckbox')
    this.submitButton = page.getByTestId('LoginForm-submitButton')
    this.errorAlert = page.getByTestId('LoginForm-errorAlert')
    this.loadingSpinner = page.getByTestId('LoginForm-loadingSpinner')
  }
  
  // ── 业务操作 ──
  
  async fillCredentials(credentials: Credentials): Promise<void> {
    await this.emailInput.fill(credentials.email)
    await this.passwordInput.fill(credentials.password)
    if (credentials.rememberMe) {
      await this.rememberCheckbox.check()
    }
  }
  
  async submit(): Promise<void> {
    await this.submitButton.click()
  }
  
  async clearCredentials(): Promise<void> {
    await this.emailInput.clear()
    await this.passwordInput.clear()
    await this.rememberCheckbox.uncheck()
  }
  
  // ── 状态验证 ──
  
  async expectLoadingState(): Promise<void> {
    await expect(this.loadingSpinner).toBeVisible()
    await expect(this.submitButton).toBeDisabled()
  }
  
  async expectResultState(): Promise<void> {
    await expect(this.loadingSpinner).toBeHidden()
    await expect(this.submitButton).toBeEnabled()
  }
  
  async expectErrorMessage(message: string): Promise<void> {
    await expect(this.errorAlert).toBeVisible()
    await expect(this.errorAlert).toContainText(message)
  }
  
  async expectNoError(): Promise<void> {
    await expect(this.errorAlert).toBeHidden()
  }
  
  async expectSubmitButtonEnabled(): Promise<void> {
    await expect(this.submitButton).toBeEnabled()
  }
  
  async expectSubmitButtonDisabled(): Promise<void> {
    await expect(this.submitButton).toBeDisabled()
  }
}

// ──────────── 页面 POM ────────────

interface Credentials {
  email: string
  password: string
  rememberMe?: boolean
}

interface LoginResult {
  success: boolean
  errorMessage?: string
  redirectUrl?: string
}

export class LoginPage {
  readonly page: Page
  readonly loginForm: LoginFormComponent
  readonly container: Locator
  
  constructor(page: Page) {
    this.page = page
    this.loginForm = new LoginFormComponent(page)
    this.container = page.getByTestId('LoginPage-container')
  }
  
  // ── 导航 ──
  
  async navigate(): Promise<void> {
    await this.page.goto('/login')
    await this.container.waitFor()
  }
  
  // ── 业务操作 ──
  
  async loginAs(credentials: Credentials): Promise<LoginResult> {
    await this.loginForm.fillCredentials(credentials)
    await this.loginForm.submit()
    await this.loginForm.expectLoadingState()
    
    // 等待结果状态
    const errorVisible = await this.loginForm.errorAlert.isVisible()
    if (errorVisible) {
      const message = await this.loginForm.errorAlert.textContent()
      return { success: false, errorMessage: message ?? 'Unknown error' }
    }
    
    await this.page.waitForURL('/dashboard')
    return { success: true, redirectUrl: '/dashboard' }
  }
  
  async loginAndExpectError(credentials: Credentials, expectedError: string): Promise<void> {
    await this.loginForm.fillCredentials(credentials)
    await this.loginForm.submit()
    await this.loginForm.expectErrorMessage(expectedError)
  }
  
  async quickLogin(email: string, password: string): Promise<void> {
    await this.navigate()
    await this.loginAs({ email, password })
  }
  
  // ── 状态验证 ──
  
  async expectPageVisible(): Promise<void> {
    await expect(this.container).toBeVisible()
  }
  
  async expectLoginFormVisible(): Promise<void> {
    await expect(this.loginForm.emailInput).toBeVisible()
    await expect(this.loginForm.passwordInput).toBeVisible()
    await expect(this.loginForm.submitButton).toBeVisible()
  }
  
  async isOnLoginPage(): Promise<boolean> {
    return this.page.url().includes('/login')
  }
}
```

---

## 多页面组合模式

### 跨页面操作流程

```typescript
class UserWorkflow {
  readonly loginPage: LoginPage
  readonly dashboardPage: DashboardPage
  readonly settingsPage: SettingsPage
  
  constructor(page: Page) {
    this.loginPage = new LoginPage(page)
    this.dashboardPage = new DashboardPage(page)
    this.settingsPage = new SettingsPage(page)
  }
  
  async loginAndGoToSettings(credentials: Credentials): Promise<void> {
    await this.loginPage.navigate()
    await this.loginPage.loginAs(credentials)
    await this.dashboardPage.navigate()
    await this.dashboardPage.openSettings()
    await this.settingsPage.expectPageVisible()
  }
  
  async loginAndVerifyDashboard(credentials: Credentials): Promise<void> {
    await this.loginPage.quickLogin(credentials.email, credentials.password)
    await this.dashboardPage.expectWelcomeMessage(credentials.email)
  }
}
```

### 共享组件模式

多个页面共享同一组件时，组件 POM 可复用：

```typescript
// Header 在所有页面都存在
class HeaderComponent {
  readonly page: Page
  readonly logoLink: Locator
  readonly navigationMenu: Locator
  readonly userAvatar: Locator
  readonly logoutButton: Locator
  
  constructor(page: Page) {
    this.page = page
    this.logoLink = page.getByTestId('Header-logoLink')
    this.navigationMenu = page.getByTestId('Header-navigationMenu')
    this.userAvatar = page.getByTestId('Header-userAvatar')
    this.logoutButton = page.getByTestId('Header-logoutButton')
  }
  
  async logout(): Promise<void> {
    await this.logoutButton.click()
  }
  
  async navigateTo(section: string): Promise<void> {
    await this.navigationMenu.getByText(section, { exact: true }).click()
  }
}

// 多个页面复用 Header
class DashboardPage {
  readonly header: HeaderComponent
  readonly sidebar: SidebarComponent
  constructor(page: Page) {
    this.header = new HeaderComponent(page)
    this.sidebar = new SidebarComponent(page)
  }
}
```

---

## Feature Flag 与权限变体

### Feature Flag 变体

```typescript
class DashboardPage {
  readonly betaFeature: Locator
  
  constructor(page: Page, featureFlags: Record<string, boolean> = {}) {
    this.betaFeature = page.getByTestId('Dashboard-betaFeature')
    // ... 其他定位器
  }
  
  // Feature flag 条件方法
  async enableBetaFeature(): Promise<void> {
    // 通过 API 或 localStorage 设置 flag
    await this.page.evaluate(() => {
      localStorage.setItem('ENABLE_BETA_FEATURE', 'true')
    })
  }
  
  async expectBetaFeatureVisible(): Promise<void> {
    await this.enableBetaFeature()
    await this.page.reload()
    await expect(this.betaFeature).toBeVisible()
  }
  
  async expectBetaFeatureHidden(): Promise<void> {
    await expect(this.betaFeature).toBeHidden()
  }
}
```

### 权限变体

```typescript
interface UserRole {
  role: 'admin' | 'editor' | 'viewer'
}

class AdminPanelPage {
  readonly adminControls: Locator
  readonly editorControls: Locator
  readonly viewerContent: Locator
  
  constructor(page: Page) {
    this.adminControls = page.getByTestId('AdminPanel-adminControls')
    this.editorControls = page.getByTestId('AdminPanel-editorControls')
    this.viewerContent = page.getByTestId('AdminPanel-viewerContent')
  }
  
  async expectControlsForRole(role: UserRole['role']): Promise<void> {
    switch (role) {
      case 'admin':
        await expect(this.adminControls).toBeVisible()
        await expect(this.editorControls).toBeVisible()
        break
      case 'editor':
        await expect(this.adminControls).toBeHidden()
        await expect(this.editorControls).toBeVisible()
        break
      case 'viewer':
        await expect(this.adminControls).toBeHidden()
        await expect(this.editorControls).toBeHidden()
        break
    }
  }
}
```

---

## POM 组织约定

### 文件命名
```
pages/
  LoginPage.ts          — 页面 POM（PascalCase）
  DashboardPage.ts
  SettingsPage.ts
components/
  LoginFormComponent.ts — 组件 POM（PascalCase + Component）
  HeaderComponent.ts
  DataTableComponent.ts
workflows/
  UserWorkflow.ts       — 跨页面流程 POM（PascalCase + Workflow）
  CheckoutWorkflow.ts
  RegistrationWorkflow.ts
types/
  credentials.ts        — 共享类型定义
  user-roles.ts
  test-data.ts
```

### 导出规则
- 每个 POM 文件导出唯一的类（不导出多个类）
- 组件 POM 可在同一文件内定义，但不导出
- 页面 POM 必须导出
- 类型定义文件导出 interface/type

### 依赖规则
- 组件 POM 不依赖页面 POM（方向：页面 → 组件）
- Workflow POM 可依赖多个页面 POM
- POM 不依赖测试框架的 test context（仅依赖 Page 对象）

---

## 实战示例

### React 项目 POM 生成

```
项目: React SPA（Next.js）
页面: LoginPage, DashboardPage, SettingsPage

步骤 1: 加载注册表 → 识别 LoginForm, Header, DashboardGrid, SettingsForm
步骤 2: 加载定位器目录 → Level 1 全覆盖
步骤 3: 组合分析
  LoginPage = Header + LoginForm
  DashboardPage = Header + Sidebar + DashboardGrid
  SettingsPage = Header + SettingsForm
步骤 4: 生成 LoginFormComponent.ts → fillCredentials, submit, expectError
步骤 5: 生成 HeaderComponent.ts → logout, navigateTo
步骤 6: 生成 LoginPage.ts → loginAs, loginAndExpectError, quickLogin
步骤 7: 生成 DashboardPage.ts → openSettings, expectWelcomeMessage
步骤 8: 生成 SettingsPage.ts → updateProfile, expectSaved
```

### Vue 项目 POM 生成

```
项目: Vue SPA（Vuetify）
页面: ProductListPage, CartPage, CheckoutPage

步骤 1: 加载注册表 → 识别 DataTable, ShoppingCart, CheckoutForm, Header
步骤 2: 加载定位器目录 → DataTable sortIcon 为 Level 4 降级
步骤 3: 组合分析
  ProductListPage = Header + DataTable + SearchBar
  CartPage = Header + ShoppingCart
  CheckoutPage = Header + CheckoutForm
步骤 4: 生成 DataTableComponent.ts → sortBy, search, selectRow, navigatePage
步骤 5: 生成 ShoppingCartComponent.ts → removeItem, updateQuantity, expectTotal
步骤 6: 生成 CartPage.ts → proceedToCheckout, expectCartTotal
步骤 7: 生成 CheckoutWorkflow.ts → fullCheckoutFlow, checkoutAsGuest
```

### Angular 项目 POM 生成

```
项目: Angular SPA（Angular Material）
页面: AdminPage, UserManagementPage, RoleManagementPage

步骤 1: 加载注册表 → 识别 AdminSidebar, UserTable, RoleEditor, MatDialog
步骤 2: 加载定位器目录 → MatDialog 内部需穿透 Shadow DOM
步骤 3: 组合分析
  AdminPage = AdminSidebar + DashboardWidget
  UserManagementPage = AdminSidebar + UserTable + MatDialog
步骤 4: 生成 MatDialogComponent.ts → confirm, cancel, expectOpen, expectClosed
步骤 5: 生成 UserManagementPage.ts → addUser, editUser, deleteUser, expectUserList
步骤 6: 生成 RoleManagementPage.ts → createRole, assignPermission
```

---

## 最佳实践

1. **业务语义命名**：方法名使用业务语言而非技术语言
2. **组件组合优先**：页面 POM 由组件 POM 组合，而非直接暴露定位器
3. **状态感知**：所有异步操作包含状态等待，不依赖隐式等待
4. **类型安全**：使用 TypeScript interface 定义所有参数和返回值
5. **自包含导航**：每个页面 POM 包含 `navigate()` 方法
6. **单一职责**：每个 POM 只负责一个页面或一个组件的业务抽象