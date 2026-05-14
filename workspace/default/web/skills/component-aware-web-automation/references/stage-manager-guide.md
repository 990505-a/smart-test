# Agent 2 — Stage Manager / 舞台经理 指导手册

## 使命与哲学

舞台经理的核心使命是确保每个交互元素拥有**确定性的定位标识符**。我们的哲学立场：

> **上游注入优于运行时降级**

在源代码层面注入 `data-testid` 是最高质量的定位策略。运行时降级（如 CSS 选择器、文本匹配）是不得已的妥协，而非首选方案。我们在上游解决问题，下游才能安心表演。

---

## 标识符审计流程

每个交互元素必须经过 4 级优先级检查：

### 优先级 Level 1 — 现有语义属性
检查元素是否已有可用的语义属性：
- `aria-label`（最优，兼具可访问性与定位能力）
- `aria-labelledby`（引用关联标签）
- `role` + `accessible-name` 组合
- `<label>` 关联的表单元素（通过 for/id 或嵌套）

**判定规则**：若元素已有 `aria-label` 且语义准确 → 无需注入，标记为 `uses-existing-aria-label`

### 优先级 Level 2 — 现有 data-testid
检查元素是否已有 `data-testid`：
- 名称是否遵循语义命名约定（而非随机编号）
- 是否在整个应用内唯一

**判定规则**：
- 名称语义准确 + 全局唯一 → 无需注入，标记为 `uses-existing-testid`
- 名称语义模糊（如 `test-123`）→ 需要重命名，标记为 `rename-existing-testid`
- 名称全局冲突 → 需要重命名，标记为 `resolve-conflict`

### 优先级 Level 3 — 稳定结构性属性
检查是否有稳定的结构性属性可用：
- `id` 属性（需确认非动态生成）
- `name` 属性（表单元素专属）
- `href` 属性（导航链接专属）
- 特定的 `class` 组合（需确认非样式框架随机生成）

**判定规则**：若属性稳定且语义明确 → 标记为 `uses-structural-attribute`，记录 fallback 定位器

### 优先级 Level 4 — 需要注入
以上三级均不满足 → 必须注入 `data-testid`

---

## 注入命名约定

### 核心公式

```
ComponentName-elementRole-semanticDescriptor
```

### 各部分说明

| 部分 | 说明 | 示例 |
|------|------|------|
| ComponentName | 组件名称，PascalCase | LoginForm, DataTable, ShoppingCart |
| elementRole | 元素交互角色，camelCase | submitButton, emailInput, sortIcon, paginationNext |
| semanticDescriptor | 语义区分符（可选），camelCase | primary, secondary, confirmDialog, errorAlert |

### 命名示例

```
LoginForm-emailInput            — 登录表单邮箱输入框
LoginForm-passwordInput         — 登录表单密码输入框
LoginForm-submitButton          — 登录表单提交按钮
LoginForm-rememberCheckbox      — 登录表单记住我复选框
LoginForm-errorAlert            — 登录表单错误提示

DataTable-sortIcon-columnName   — 数据表格排序图标（按列名区分）
DataTable-paginationNext        — 数据表格下一页按钮
DataTable-paginationPrev        — 数据表格上一页按钮
DataTable-searchInput           — 数据表格搜索输入框
DataTable-rowCheckbox-rowIndex  — 数据表格行选择复选框

ShoppingCart-removeButton-itemId — 购物车移除按钮（按商品区分）
ShoppingCart-quantityInput-itemId — 购物车数量输入框
ShoppingCart-checkoutButton      — 购物车结算按钮
```

### 唯一性保证规则

1. **全局唯一**：同一 `data-testid` 不得出现在两个不同组件中
2. **列表项处理**：动态列表中的元素使用索引或唯一 key：`ItemList-item-0`, `ItemList-item-{key}`
3. **重复角色处理**：同一组件内多个同角色元素用语义区分符：`Form-submitButton-primary`, `Form-submitButton-secondary`
4. **禁止编号**：不得使用 `test-1`, `test-2` 等无语义编号

---

## 各框架注入模式

### React 注入模式

```tsx
// 注入前
<button type="submit" disabled={isLoading}>
  Login
</button>

// 注入后
<button type="submit" disabled={isLoading} data-testid="LoginForm-submitButton">
  Login
</button>

// 列表项注入
{items.map((item, index) => (
  <div key={item.id} data-testid={`ShoppingCart-item-${item.id}`}>
    <button data-testid={`ShoppingCart-removeButton-${item.id}`}>Remove</button>
  </div>
))}
```

### Vue 注入模式

```vue
<!-- 注入前 -->
<button type="submit" :disabled="isLoading" @click="handleSubmit">
  Login
</button>

<!-- 注入后 -->
<button type="submit" :disabled="isLoading" @click="handleSubmit" data-testid="LoginForm-submitButton">
  Login
</button>

<!-- 动态 testid -->
<div v-for="item in items" :key="item.id" :data-testid="`DataTable-row-${item.id}`">
  <button :data-testid="`DataTable-removeButton-${item.id}`">Remove</button>
</div>
```

### Angular 注入模式

```html
<!-- 注入前 -->
<button type="submit" [disabled]="isLoading" (click)="handleSubmit()">
  Login
</button>

<!-- 注入后 -->
<button type="submit" [disabled]="isLoading" (click)="handleSubmit()" data-testid="LoginForm-submitButton">
  Login
</button>

<!-- 动态 testid -->
<div *ngFor="let item of items; trackBy: trackById"
     [attr.data-testid]=" 'ShoppingCart-item-' + item.id ">
  <button [attr.data-testid]=" 'ShoppingCart-removeButton-' + item.id ">Remove</button>
</div>
```

### Svelte 注入模式

```svelte
<!-- 注入前 -->
<button type="submit" disabled={isLoading} on:click={handleSubmit}>
  Login
</button>

<!-- 注入后 -->
<button type="submit" disabled={isLoading} on:click={handleSubmit} data-testid="LoginForm-submitButton">
  Login
</button>

<!-- 动态 testid -->
{#each items as item (item.id)}
  <div data-testid="ShoppingCart-item-{item.id}">
    <button data-testid="ShoppingCart-removeButton-{item.id}">Remove</button>
  </div>
{/each}
```

---

## 输出 Schema

```json
{
  "$schema": "https://component-aware.schema/v1/testid-injections",
  "metadata": {
    "sourceRegistry": "component-registry.json",
    "repo": "https://github.com/org/project",
    "framework": "react",
    "auditTimestamp": "2026-04-18T12:00:00Z",
    "stats": {
      "totalElements": 120,
      "existingAriaLabels": 15,
      "existingTestIds": 20,
      "renamedTestIds": 5,
      "newInjections": 80,
      "conflictResolutions": 3
    }
  },
  "injections": [
    {
      "componentId": "LoginForm",
      "filePath": "src/components/LoginForm.tsx",
      "element": {
        "elementType": "input",
        "role": "email-input",
        "originalCode": "<input type=\"email\" value={email} onChange={...}>"
      },
      "auditResult": "needs-injection",
      "injectedTestId": "LoginForm-emailInput",
      "injectionCode": "<input type=\"email\" value={email} onChange={...} data-testid=\"LoginForm-emailInput\">",
      "priority": "level-4"
    },
    {
      "componentId": "LoginForm",
      "filePath": "src/components/LoginForm.tsx",
      "element": {
        "elementType": "button",
        "role": "submit-button",
        "originalCode": "<button type=\"submit\" aria-label=\"Submit login form\">"
      },
      "auditResult": "uses-existing-aria-label",
      "injectedTestId": null,
      "fallbackLocator": "aria-label=Submit login form",
      "priority": "level-1"
    }
  ]
}
```

---

## 边界情况

### 动态 ID 冲突
当组件被复用在不同页面时，可能出现 `data-testid` 全局冲突。解决方案：
- **页面级命名**：`LoginPage-LoginForm-submitButton` vs `DashboardPage-LoginForm-submitButton`
- **组件级命名**：保持组件级命名不变，但在定位器目录中注明页面上下文

### 第三方组件无法注入
第三方库的内部元素无法直接注入 `data-testid`。解决方案：
- 使用第三方组件暴露的 props 传递 `data-testid`：`<DatePicker data-testid="Form-datePicker">`
- 使用包裹层注入：`<div data-testid="Form-datePicker-wrapper"><DatePicker /></div>`

### SSR / 静态生成页面
SSR 生成的 HTML 中 `data-testid` 需要确保被正确渲染：
- Next.js：确认 `data-testid` 不被 `next/config` 过滤
- Nuxt：确认 `data-testid` 在 SSR 模式下被包含

### Shadow DOM
Shadow DOM 内的元素无法被外部 `querySelector` 定位。解决方案：
- 使用 `piercing` 定位策略：`page.locator('[data-testid="xxx'] >>> internal-selector')`
- 在 Shadow DOM host 上注入 `data-testid`，然后穿透内部

### 同一元素多个 testid
一个元素不得有多个 `data-testid`。若同一元素需在不同上下文中定位，使用单一 testid 并在定位器目录中建立多映射关系。

---

## 最佳实践

1. **最小侵入原则**：优先利用现有语义属性，只在必要时注入
2. **语义命名优先**：testid 名称必须传达业务语义，而非技术实现
3. **全局唯一性审计**：注入完成后运行唯一性检查脚本
4. **代码风格一致**：注入时保持项目原有代码风格（缩进、引号、分号）
5. **可回滚性**：所有注入操作记录在 `testid-injections.json`，支持一键回滚