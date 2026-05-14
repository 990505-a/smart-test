# 编舞师指南 (Agent 5: Choreographer)

## 使命与哲学

编舞师是流水线的**创意大脑**。它不只是规划"点击这个再点击那个"——它理解业务意图，枚举所有可能的状态排列，确保覆盖用户可能遇到的**每种渲染变体**。

传统测试方法只测试运行时可见的单一状态。编舞师通过源代码级别的条件渲染分析，识别出浏览器永远无法同时展示的**隐藏状态维度**，确保没有任何排列被遗漏。

> "浏览器一次只能展示一种渲染状态，忽略了 Feature Flags 和权限带来的多种排列组合。"
> — monday.com engineering blog

---

## 旅程规划流程

```
输入:
  component-registry.json (含 featureFlagGuards + conditionalRendering)
  route-config.json (路由配置)
  permission-model.json (权限模型)

处理:
  1. 识别所有状态维度 (Feature Flags × 权限 × 数据条件)
  2. 枚举完整排列
  3. 智能剪枝等价排列
  4. 为每个唯一排列规划旅程
  5. 生成覆盖矩阵

输出:
  journeys.json (旅程定义)
  coverage-matrix.json (覆盖矩阵)
```

---

## 状态排列枚举（核心方法论）

### 概念

单个页面根据以下维度可渲染为多种不同状态：

| 维度 | 类型 | 每维值数 | 来源 |
|---|---|---|---|
| Feature Flags | 开关型 | 2 (on/off) | component-registry `featureFlagGuards` |
| Permissions/Roles | 多值型 | N | permission-model `roles[]` |
| Data Conditions | 状态型 | 3-4 (空/部分/错误/加载) | conditionalRendering + data conditions |

### 排列公式

```
totalPermutations = ∏(dimension.values.length)
```

### 示例计算：电商用户表格

```json
{
  "dimensions": [
    {
      "name": "role",
      "values": ["admin", "editor", "viewer"],
      "source": "permission-model"
    },
    {
      "name": "showDeleteButton",
      "values": [true, false],
      "source": "feature-flag"
    },
    {
      "name": "dataState",
      "values": ["empty", "populated", "error"],
      "source": "conditional-rendering"
    }
  ]
}
```

```
totalPermutations = 3 × 2 × 3 = 18
```

### 智能剪枝：等价排列消除

关键洞察：某些排列虽然参数不同，但产生**相同的渲染结果**。

**剪枝规则**：

1. **权限覆盖标志位**: `viewer + showDeleteButton=true` ≡ `viewer + showDeleteButton=false`
   - 原因: viewer 权限下 deleteButton 被权限守卫隐藏，Feature Flag 状态无关
   
2. **数据空状态覆盖组件**: `empty + showPagination=true` ≡ `empty + showPagination=false`
   - 原因: 数据为空时表格不渲染，分页自然不可见

3. **错误状态覆盖一切**: `error + anyFlag + anyRole` → 仅显示错误页面
   - 原因: 错误状态通常完全替换正常渲染

**剪枝后结果**：

```
18 permutations → 剪枝后 8 unique renderings

剪枝详情:
  viewer + showDelete(true)  ≡  viewer + showDelete(false)  → 合并为1个
  viewer + showDelete(true) + empty ≡ viewer + showDelete(false) + empty → 合并
  error + any + any → 统一为1个错误页面
  
最终8个唯一渲染:
  1. admin  + showDelete(true)  + populated  → 完整表格+删除
  2. admin  + showDelete(false) + populated  → 完整表格无删除
  3. admin  + showDelete(true)  + empty      → 空表格+删除(隐藏)
  4. admin  + showDelete(false) + empty      → 空表格无删除
  5. editor + showDelete(true)  + populated  → 表格+编辑+删除
  6. editor + showDelete(false) + populated  → 表格+编辑无删除
  7. viewer + any               + populated  → 只读表格
  8. any     + any               + error     → 错误页面
```

---

## 旅程定义 Schema

```json
{
  "journeys": [
    {
      "id": "user-table-admin-delete-populated",
      "name": "Admin deletes a row in populated table with delete feature enabled",
      "description": "管理员在有数据的表格中删除一行，删除按钮可见",
      "permutation": {
        "role": "admin",
        "showDeleteButton": true,
        "dataState": "populated"
      },
      "uniqueRenderingId": "render-1",
      "steps": [
        {
          "step": 1,
          "action": "navigate",
          "pom": "UserTablePage",
          "method": "navigateTo",
          "args": []
        },
        {
          "step": 2,
          "action": "assert_visible",
          "pom": "UserTablePage",
          "method": "assertTablePopulated",
          "args": []
        },
        {
          "step": 3,
          "action": "assert_visible",
          "pom": "UserTablePage",
          "method": "assertDeleteButtonVisible",
          "args": []
        },
        {
          "step": 4,
          "action": "interact",
          "pom": "UserTablePage",
          "method": "deleteRow",
          "args": ["row-3"]
        },
        {
          "step": 5,
          "action": "assert_state",
          "pom": "UserTablePage",
          "method": "assertRowDeleted",
          "args": ["row-3"]
        }
      ],
      "expectedOutcome": "Row 3 deleted, table has one fewer row, success toast visible"
    }
  ],
  "coverageMatrix": {
    "sourceFile": "src/components/UserTable.vue",
    "totalPermutations": 18,
    "uniqueRenderings": 8,
    "journeysPlanned": 8,
    "coveragePercent": 100,
    "prunedPermutations": [
      {
        "original": "viewer + showDelete(true) + populated",
        "equivalentTo": "viewer + showDelete(false) + populated",
        "reason": "Permission guard overrides feature flag for viewer role"
      }
    ],
    "dimensionBreakdown": {
      "role": { "values": 3, "covered": 3 },
      "showDeleteButton": { "values": 2, "covered": 2 },
      "dataState": { "values": 3, "covered": 3 }
    }
  }
}
```

---

## 旅程类型分类

| 类型 | 优先级 | 说明 | 示例 |
|---|---|---|---|
| **Happy Path** | P1 | 核心业务流，最常见排列 | admin+正常数据+默认标志 |
| **Permission Boundary** | P2 | 不同角色的可见/可操作差异 | viewer看不到删除按钮 |
| **Feature Flag Toggle** | P2 | 标志开关导致的UI变化 | showDelete on/off |
| **Error Handling** | P3 | 错误状态的处理和恢复 | API错误→错误页面 |
| **Data Boundary** | P3 | 极端数据条件 | 空列表、单条数据 |
| **Cross-Page** | P4 | 涉及多个页面的流程 | 登录→浏览→结账→确认 |

---

## 基于优先级的旅程选择

当完整排列覆盖成本太高时，按以下优先级选择：

### P1: 必须覆盖（核心信心）

```
Happy path for each primary role × primary data state
例: admin+populated, editor+populated, viewer+populated
```

### P2: 应该覆盖（差异化信心）

```
Permission boundaries × Feature flag toggles
例: admin+showDelete(on) vs admin+showDelete(off)
```

### P3: 建议覆盖（边缘信心）

```
Error states × Empty data states
例: any+empty, any+error
```

### P4: 可选覆盖（完整信心）

```
Rare permutations, low-impact combinations
```

### P5: 不覆盖（不值得投入）

```
Impossible combinations, internal-only states
```

---

## 实战示例

### 示例1: 电商结账流程

```json
{
  "dimensions": [
    { "name": "role", "values": ["guest", "registered", "premium"] },
    { "name": "hasSavedAddress", "values": [true, false] },
    { "name": "cartState", "values": ["normal", "outOfStock", "couponApplied"] }
  ],
  "totalPermutations": 3 × 2 × 3 = 18,
  "uniqueRenderings": 12,
  "journeys": [
    {
      "id": "checkout-registered-saved-normal",
      "name": "Registered user with saved address checks out normal cart",
      "permutation": { "role": "registered", "hasSavedAddress": true, "cartState": "normal" },
      "steps": [
        { "step": 1, "pom": "CartPage", "method": "navigateTo" },
        { "step": 2, "pom": "CartPage", "method": "assertCartItemsVisible" },
        { "step": 3, "pom": "CartPage", "method": "proceedToCheckout" },
        { "step": 4, "pom": "CheckoutPage", "method": "assertSavedAddressVisible" },
        { "step": 5, "pom": "CheckoutPage", "method": "selectSavedAddress" },
        { "step": 6, "pom": "CheckoutPage", "method": "submitOrder" },
        { "step": 7, "pom": "OrderConfirmPage", "method": "assertOrderSuccess" }
      ]
    }
  ]
}
```

### 示例2: vue-element-admin 权限测试

```json
{
  "dimensions": [
    { "name": "role", "values": ["admin", "editor"] },
    { "name": "sidebarMode", "values": ["normal", "compact"] }
  ],
  "totalPermutations": 2 × 2 = 4,
  "uniqueRenderings": 4,
  "journeys": [
    {
      "id": "dashboard-admin-normal-sidebar",
      "permutation": { "role": "admin", "sidebarMode": "normal" },
      "steps": [
        { "pom": "LoginPage", "method": "loginAsAdmin" },
        { "pom": "DashboardPage", "method": "assertAllMenuItemsVisible" },
        { "pom": "DashboardPage", "method": "assertStatsCardsVisible" },
        { "pom": "DashboardPage", "method": "assertOrderTableVisible" }
      ]
    },
    {
      "id": "dashboard-editor-normal-sidebar",
      "permutation": { "role": "editor", "sidebarMode": "normal" },
      "steps": [
        { "pom": "LoginPage", "method": "loginAsEditor" },
        { "pom": "DashboardPage", "method": "assertEditorMenuItemsVisible" },
        { "pom": "DashboardPage", "method": "assertStatsCardsVisible" },
        { "pom": "DashboardPage", "method": "assertOrderTableHidden" }
      ]
    }
  ]
}
```

### 示例3: SauceDemo 登录测试

```json
{
  "dimensions": [
    { "name": "userType", "values": ["standard", "locked_out", "problem", "performance_glitch", "error", "visual"] },
    { "name": "passwordValidity", "values": ["correct", "wrong", "empty"] },
    { "name": "usernameState", "values": ["filled", "empty"] }
  ],
  "totalPermutations": 6 × 3 × 2 = 36,
  "uniqueRenderings": 10,
  "prunedPermutations": [
    { "original": "locked_out + correct", "equivalentTo": "locked_out + wrong", "reason": "Locked user always rejected regardless of password" },
    { "original": "any + empty_username", "equivalentTo": "any_type + empty_username", "reason": "Empty username always shows same error" }
  ],
  "journeys": [
    {
      "id": "login-standard-correct-filled",
      "permutation": { "userType": "standard", "passwordValidity": "correct", "usernameState": "filled" },
      "steps": [
        { "pom": "LoginPage", "method": "navigateTo" },
        { "pom": "LoginPage", "method": "fillUsername", "args": ["standard_user"] },
        { "pom": "LoginPage", "method": "fillPassword", "args": ["secret_sauce"] },
        { "pom": "LoginPage", "method": "submitLogin" },
        { "pom": "InventoryPage", "method": "assertProductsVisible" }
      ]
    },
    {
      "id": "login-locked-correct-filled",
      "permutation": { "userType": "locked_out", "passwordValidity": "correct", "usernameState": "filled" },
      "steps": [
        { "pom": "LoginPage", "method": "navigateTo" },
        { "pom": "LoginPage", "method": "fillUsername", "args": ["locked_out_user"] },
        { "pom": "LoginPage", "method": "fillPassword", "args": ["secret_sauce"] },
        { "pom": "LoginPage", "method": "submitLogin" },
        { "pom": "LoginPage", "method": "assertLockedOutError" }
      ]
    }
  ]
}
```

---

## 关键原则

1. **排列是事实，不是猜测** — 从源代码的条件渲染分析中确定性推导，而非运行时观察
2. **剪枝是科学，不是偷懒** — 等价排列有明确的因果推理（权限覆盖标志位）
3. **每个旅程对应一个排列** — 测试体中绝无 if/else，确定性执行
4. **覆盖矩阵是审计工具** — 让团队明确知道哪些排列被覆盖、哪些被剪枝、为什么