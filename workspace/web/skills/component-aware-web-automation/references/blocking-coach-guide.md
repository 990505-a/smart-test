# Agent 3 — Blocking Coach / 调度教练 指导手册

## 使命与哲学

调度教练的核心使命是为每个交互元素建立**预确定的、确定性的定位器链**。我们的哲学立场：

> **预确定定位器优于运行时发现**

我们拒绝"先跑起来再说"的定位器策略。每个定位器在测试执行之前就必须被确定，运行时只做"按目录查找"而非"猜测探索"。这就像戏剧中的调度（blocking）——演员的每一步走位在排练时就已经确定，而不是在正式演出时随机探索。

---

## 定位器优先级链

我们采用 4 级定位器优先级链，从最可靠到最不稳定：

### Level 1 — data-testid 定位器（最高确定性）

```typescript
page.getByTestId('LoginForm-submitButton')
```

**优势**：
- 开发者有意为之的定位锚点，语义明确
- 不受样式重构影响（CSS class 变化不影响）
- 不受文本国际化影响（i18n 更换不影响）
- 不受组件内部结构调整影响
- 全局唯一性可审计

**使用规则**：
- 必须使用语义化的 testid 名称，拒绝随机编号
- testid 必须经过 Stage Manager 的唯一性审计
- 动态列表使用模板 testid：`ShoppingCart-item-{key}`

### Level 2 — ARIA / 可访问性定位器（语义 + 可访问性）

```typescript
page.getByRole('button', { name: 'Submit login form' })
page.getByLabel('Email address')
page.getByPlaceholder('Enter your email')
page.getByAltText('Company logo')
```

**优势**：
- 与可访问性测试目标一致
- 语义丰富（角色 + 名称双重约束）
- 不受样式重构影响
- 反映用户实际感知

**使用规则**：
- 优先使用 `getByRole` + name 组合，因为 role 和 name 是用户感知的双重维度
- `getByLabel` 仅用于有 `<label>` 关联的表单元素
- `getByPlaceholder` 仅用于 placeholder 语义稳定的输入框
- `getByAltText` 仅用于有 alt 属性的图片元素
- 必须验证 ARIA 属性在不同语言版本下的一致性

### Level 3 — 稳定结构性定位器（确定性降级）

```typescript
page.locator('#login-form-submit')
page.locator('input[name="email"]')
page.locator('a[href="/login"]')
```

**优势**：
- 基于 DOM 结构的稳定属性
- 不依赖文本内容（不受 i18n 影响）
- 在无法注入 testid 和无 ARIA 属性时的可靠 fallback

**使用规则**：
- `id` 属性必须确认非动态生成（排除 `id="react-123"` 模式）
- `name` 属性仅用于表单元素，且需确认稳定
- `href` 仅用于导航链接
- 不得使用 `class` 定位器（样式框架随机生成 class）
- 每次使用 Level 3 必须在定位器目录中注明降级原因

### Level 4 — 文本 / 内容定位器（最低确定性，最后手段）

```typescript
page.getByText('Login')
page.locator('h1:has-text("Dashboard")')
```

**劣势**：
- 受国际化影响（文本会随语言切换变化）
- 受 UI 微调影响（按钮文字从"Submit"改为"Send"就失效）
- 同一文本可能出现在多个元素中（模糊匹配）

**使用规则**：
- 仅在 Level 1-3 均不可用时才使用
- 必须使用 `exact: true` 选项避免模糊匹配
- 必须在定位器目录中注明降级原因和风险评估
- 每次文本变更时必须同步更新定位器目录
- 优先使用 `getByText` 而非 CSS 文本匹配

---

## 目录生成流程

```
步骤 1: 加载组件注册表
    ↓ 输入: component-registry.json
步骤 2: 加载 testid 注入方案
    ↓ 输入: testid-injections.json
步骤 3: 为每个交互元素按优先级链选择最优定位器
    ↓ 决策: Level 1 → Level 2 → Level 3 → Level 4
步骤 4: 验证定位器稳定性
    ↓ AST 分析: 确认定位器引用的属性非动态生成
步骤 5: 生成定位器目录
    ↓ 输出: locator-catalog.json
步骤 6: 标记降级元素与风险
    ↓ 输出: risk-report（标记使用 Level 3/4 的元素）
```

---

## 定位器目录 Schema

```json
{
  "$schema": "https://component-aware.schema/v1/locator-catalog",
  "metadata": {
    "sourceRegistry": "component-registry.json",
    "sourceInjections": "testid-injections.json",
    "generatedTimestamp": "2026-04-18T12:00:00Z",
    "framework": "react",
    "stats": {
      "totalLocators": 120,
      "level1": 80,
      "level2": 15,
      "level3": 20,
      "level4": 5,
      "riskElements": 25
    }
  },
  "locators": [
    {
      "componentId": "LoginForm",
      "elementRole": "email-input",
      "priorityLevel": 1,
      "primaryLocator": {
        "strategy": "testid",
        "expression": "LoginForm-emailInput",
        "playwrightCode": "page.getByTestId('LoginForm-emailInput')"
      },
      "fallbackLocators": [
        {
          "strategy": "aria-label",
          "expression": "Email address",
          "playwrightCode": "page.getByRole('textbox', { name: 'Email address' })",
          "degradationReason": "若 testid 被移除，降级至 ARIA"
        }
      ],
      "riskAssessment": {
        "isStable": true,
        "riskLevel": "low",
        "degradationNotes": null
      }
    },
    {
      "componentId": "DataTable",
      "elementRole": "sort-icon",
      "priorityLevel": 4,
      "primaryLocator": {
        "strategy": "text",
        "expression": "Sort by name",
        "playwrightCode": "page.getByText('Sort by name', { exact: true })",
        "degradationReason": "第三方组件内部元素无法注入 testid 且无 ARIA 属性"
      },
      "fallbackLocators": [],
      "riskAssessment": {
        "isStable": false,
        "riskLevel": "high",
        "degradationNotes": "文本定位器受 i18n 影响，建议要求第三方库添加 aria-label"
      }
    },
    {
      "componentId": "ShoppingCart",
      "elementRole": "remove-button",
      "priorityLevel": 1,
      "primaryLocator": {
        "strategy": "testid-template",
        "expression": "ShoppingCart-removeButton-{itemId}",
        "playwrightCode": "page.getByTestId(`ShoppingCart-removeButton-${itemId}`)",
        "isDynamic": true,
        "dynamicKey": "itemId"
      },
      "fallbackLocators": [],
      "riskAssessment": {
        "isStable": true,
        "riskLevel": "low",
        "degradationNotes": null
      }
    }
  ],
  "riskReport": {
    "highRiskElements": [
      {
        "componentId": "DataTable",
        "elementRole": "sort-icon",
        "risk": "i18n-sensitive text locator",
        "recommendation": "Request aria-label from library maintainer or wrap component"
      }
    ],
    "mediumRiskElements": [
      {
        "componentId": "HeaderNav",
        "elementRole": "logo-link",
        "risk": "structural locator depends on href stability",
        "recommendation": "Monitor href changes in CI"
      }
    ]
  }
}
```

---

## AST 验证方法论

定位器选择后，必须通过 AST 验证确认稳定性：

### 验证 Level 1 — data-testid
- 确认 `data-testid` 属性存在于源代码中（非运行时动态添加）
- 确认 `data-testid` 值为静态字符串（而非变量拼接）——模板化 testid 除外

### 验证 Level 2 — ARIA 属性
- 确认 `aria-label` 为静态字符串或稳定的 i18n key
- 确认 `role` 属性为硬编码而非动态计算
- 确认 `<label>` 的文本内容稳定

### 验证 Level 3 — 结构性属性
- 确认 `id` 为静态值而非动态生成（排除 `id={uuid()}` 模式）
- 确认 `name` 为静态值
- 确认 `href` 为静态路径而非动态路由参数

### 验证方法
```bash
# 检查 id 是否为动态生成
grep -rn 'id={.*}' src/ | grep -v 'data-testid'
# 检查 aria-label 是否为动态变量
grep -rn 'aria-label={.*}' src/ | grep -v 'aria-label="'
# 检查 class 是否为 CSS-in-JS 动态生成
grep -rn 'className={css\.' src/
```

---

## 动态元素特殊处理

### 动态列表项
列表中的重复元素需要模板化定位器策略：
```
ShoppingCart-removeButton-{itemId} → page.getByTestId(`ShoppingCart-removeButton-${itemId}`)
```

### 条件渲染元素
仅在特定条件下出现的元素需要标注出现条件：
```json
{
  "primaryLocator": { "strategy": "testid", "expression": "LoginForm-errorAlert" },
  "visibilityCondition": { "prop": "errorMessage", "mustBe": "non-null" },
  "playwrightWaitStrategy": "page.getByTestId('LoginForm-errorAlert').waitFor({ state: 'visible' })"
}
```

### Feature Flag 控制元素
受 Feature Flag 控制的元素需要标注 flag 条件：
```json
{
  "primaryLocator": { "strategy": "testid", "expression": "Dashboard-betaFeature" },
  "featureFlagCondition": { "flag": "ENABLE_BETA_FEATURE", "mustBe": "true" },
  "testSetupNote": "需要在测试前设置 feature flag 为 true"
}
```

### 多状态元素
同一元素在不同状态下表现不同（如按钮的 disabled/enabled）：
```json
{
  "primaryLocator": { "strategy": "testid", "expression": "LoginForm-submitButton" },
  "stateVariants": [
    { "state": "enabled", "playwrightAssertion": "toBeEnabled()" },
    { "state": "disabled", "playwrightAssertion": "toBeDisabled()" }
  ]
}
```

---

## 实战示例

### LoginForm 定位器生成流程

```
步骤 1: 加载 LoginForm 组件注册 → 4 个交互元素
步骤 2: 加载注入方案 → emailInput, passwordInput, rememberCheckbox, submitButton 全部注入 testid
步骤 3: 选择定位器
  - emailInput → Level 1: getByTestId('LoginForm-emailInput')
  - passwordInput → Level 1: getByTestId('LoginForm-passwordInput')
  - rememberCheckbox → Level 1: getByTestId('LoginForm-rememberCheckbox')
  - submitButton → Level 1: getByTestId('LoginForm-submitButton')
步骤 4: 生成 fallback
  - emailInput → Level 2: getByRole('textbox', { name: 'Email' })
  - submitButton → Level 2: getByRole('button', { name: 'Submit login form' })
步骤 5: 验证 AST → 所有 testid 为静态字符串 ✓
步骤 6: 写入定位器目录
```

### DataTable 定位器生成（含降级）

```
步骤 1: 加载 DataTable 组件注册 → 5 个交互元素
步骤 2: 加载注入方案 → searchInput, paginationNext, paginationPrev 注入 testid
    sortIcon 和 rowCheckbox 为第三方库内部元素无法注入
步骤 3: 选择定位器
  - searchInput → Level 1: getByTestId('DataTable-searchInput')
  - sortIcon → Level 4: getByText('Sort by {column}') [降级！]
  - paginationNext → Level 1: getByTestId('DataTable-paginationNext')
  - paginationPrev → Level 1: getByTestId('DataTable-paginationPrev')
  - rowCheckbox → Level 2: getByRole('checkbox', { name: 'Select row {index}' })
步骤 4: 风险标记
  - sortIcon → 高风险（i18n 敏感文本定位器）
  - rowCheckbox → 低风险（ARIA 属性由第三方库提供）
步骤 5: 写入定位器目录 + 风险报告
```

---

## 最佳实践

1. **永不跳级**：必须从 Level 1 开始检查，逐级降级
2. **降级有据**：每次降级必须在目录中记录原因和风险评估
3. **Fallback 必备**：每个 Level 1 定位器必须有至少一个 fallback 定位器
4. **动态标注**：所有动态定位器必须标注动态 key 和模板格式
5. **定期审计**：定位器目录应随源码变更定期重新生成