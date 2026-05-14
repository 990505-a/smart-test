# 场记指南 (Agent 7: Continuity Lead)

## 使命与哲学

场记是**质量守卫者**。它不只运行测试报告 pass/fail——它执行根因分类，区分三种根本不同的失败类型，并为每种触发适当的修复策略。

传统测试框架只告诉你"测试失败了"。场记告诉你**为什么失败**，以及**应该由谁来修复**。

> 核心洞察：并非所有失败都是 Bug。源代码有意变更导致的测试失败是**预期行为**，应该更新测试而非回滚代码。

---

## 失败分类体系（核心创新）

### Type A: 代码Bug — 应用确实坏了

**定义**: POM 方法找不到应该存在的元素，或业务逻辑产生了错误的输出。

**检测标准**:
- LocatorError: `data-testid="submit-btn"` 在页面上不存在，但源代码中组件定义仍然包含该 testid
- AssertionError: 组件渲染了但行为不符合预期（如：点击删除按钮后数据未删除）
- 页面显示了不应该显示的内容（如：viewer 看到了 admin 的删除按钮）

**示例**:
```
场景: UserTablePage.deleteRow(3)
预期: 第3行被删除，表格只剩2行
实际: 第3行仍在，表格仍为3行
分类: Type A — 删除API有Bug，后端返回500但前端未处理
```

**应对**: 创建 Bug 报告，通知开发团队，测试标记为 `known-bug`，不修改测试。

---

### Type B: 测试需要更新 — 源代码有意变更

**定义**: 源代码发生了有意的设计变更（组件重命名、prop 改变、路由移动），测试需要同步更新。

**检测标准**:
- LocatorError: `data-testid="submit-btn"` 不存在，检查源代码发现 testid 已改为 `"confirm-btn"`
- LocatorError: 组件文件路径变更（如 `UserTable.vue` → `DataTable.vue`）
- 页面结构变更但功能正确（如：侧边栏从固定改为可折叠）

**示例**:
```
场景: UserTablePage.assertDeleteButtonVisible()
预期: data-testid="delete-btn" 可见
实际: 元素不存在
源代码检查: testid 从 "delete-btn" 改为 "row-delete-btn"
分类: Type B — 组件重命名，测试需要更新定位器
```

**应对**: 触发自动修复流程（重新运行 Agent 1-6，仅受影响部分）。

---

### Type C: 环境问题 — 外部因素干扰

**定义**: 测试本身和应用本身都没问题，但外部环境导致临时性失败。

**检测标准**:
- TimeoutError: 元素在超时时间内未出现，但重试后出现（不稳定渲染）
- NetworkError: API 请求超时或返回间歇性错误
- 测试在本地通过但在 CI 环境失败（环境差异）

**示例**:
```
场景: DashboardPage.waitForReady()
首次执行: TimeoutError (30s超时)
重试执行: 成功 (2s加载完成)
分类: Type C — CI环境性能波动导致超时
```

**应对**: 重试测试（最多3次），调整超时阈值，标记为 `flaky` 供后续环境优化。

---

## 分类决策树

```
测试执行 → 结果?

├── PASS → ✅ 记录成功，无需分类
│
├── FAIL → 错误类型?
│   │
│   ├── LocatorError (元素找不到)
│   │   │
│   │   ├── 检查源代码: testid/组件是否存在?
│   │   │   ├── 源代码中存在 → Type A (渲染Bug，应显示但不显示)
│   │   │   └── 源代码中不存在/已变更 → Type B (测试需更新)
│   │   │
│   │   ├── 检查运行时: 元素是否在DOM中但隐藏?
│   │   │   ├── DOM中存在但hidden → 可能是 Type A (显示逻辑Bug)
│   │   │   └── DOM中不存在 → 继续检查源代码
│   │
│   ├── AssertionError (行为不符合预期)
│   │   │
│   │   ├── 业务逻辑错误 (数据未删除/表单未提交)
│   │   │   ├── 检查源代码: 逻辑是否变更?
│   │   │   │   ├── 逻辑未变更 → Type A (代码Bug)
│   │   │   │   └── 逻辑有意变更 → Type B (测试需更新断言)
│   │   │
│   │   ├── UI展示错误 (排序/颜色/文案不对)
│   │   │   ├── 检查源代码: UI规范是否变更?
│   │   │   │   ├── 规范未变更 → Type A (渲染Bug)
│   │   │   │   └── 规范有意变更 → Type B (测试需更新)
│   │
│   ├── TimeoutError (等待超时)
│   │   │
│   │   ├── 重试1次 → 结果?
│   │   │   ├── 通过 → Type C (环境不稳定)
│   │   │   ├── 仍然超时 → 检查源代码
│   │   │   │   ├── 组件定义正常 → Type C (严重环境问题)
│   │   │   │   ├── 组件已变更 → Type B
│   │   │   │   ├── 组件存在但渲染逻辑有Bug → Type A
│   │
│   ├── NetworkError (网络错误)
│   │   ├── API endpoint不可达 → Type C
│   │   ├── API返回错误但源代码期望成功 → 检查后端日志
│   │   │   ├── 后端有Bug → Type A (跨系统Bug)
│   │   │   ├── 后端有意变更 → Type B (API契约变更)
```

---

## Type B 自动修复工作流（8步骤）

当检测到 Type B 失败时，触发以下自动修复流程：

### Step 1: 识别受影响组件

```json
{
  "failedTest": "UserTable-admin-showDeleteOn-populated",
  "failedStep": "assertDeleteButtonVisible",
  "failedLocator": "data-testid='delete-btn'",
  "affectedComponent": "UserTable",
  "affectedFile": "src/components/UserTable.vue"
}
```

### Step 2: 找到变更源文件

通过 Git diff 或文件比对，定位源代码中具体发生了什么变更：

```bash
# 自动执行
git diff HEAD~1 -- src/components/UserTable.vue
# 发现: testid 从 "delete-btn" 改为 "row-delete-btn"
```

### Step 3: 重新运行 Agent 1（仅受影响组件）

只对变更的源文件重新执行静态分析：

```bash
extract-components.sh --file src/components/UserTable.vue --output ./test-output
# 更新 component-registry.json 中的 UserTable 条目
```

### Step 4: 重新运行 Agent 2（仅受影响组件）

检查新 testid 是否已覆盖所有交互元素：

```bash
inject-testids.sh --registry ./test-output/component-registry.json --repo ./src
# 输出: UserTable 已有 row-delete-btn，无需注入
```

### Step 5: 重新运行 Agent 3（仅受影响定位器）

更新定位器目录中 UserTable 的条目：

```json
{
  "component": "UserTable",
  "locators": {
    "deleteButton": {
      "priority1": "data-testid=row-delete-btn",
      "priority2": "role=button name=Delete",
      "priority3": "UserTable > Button.delete-action"
    }
  }
}
```

### Step 6: 重新运行 Agent 4（仅受影响 POM）

更新 UserTablePage POM 的定位器和方法：

```typescript
// 更新前
private deleteBtn = this.page.getByTestId('delete-btn');

// 更新后
private deleteBtn = this.page.getByTestId('row-delete-btn');
```

### Step 7: 重新执行修复后的测试

```bash
npx playwright test UserTable-admin-showDeleteOn-populated.spec.ts
# 结果: PASS ✅
```

### Step 8: 验证所有相关测试通过

检查同一组件的其他排列测试是否也需要更新：

```bash
npx playwright test tests/user-table/
# 全部通过 → 修复完成
# 有新的失败 → 重复 Step 3-7
```

---

## 执行报告 Schema

```json
{
  "executionId": "exec-2026-04-18-001",
  "timestamp": "2026-04-18T10:30:00Z",
  "pipelineVersion": "1.0.0",
  "statistics": {
    "totalTests": 24,
    "passed": 20,
    "failed": 3,
    "skipped": 1,
    "durationMs": 45000
  },
  "failures": [
    {
      "testName": "UserTable-admin-showDeleteOn-populated",
      "errorType": "LocatorError",
      "errorMessage": "Locator.getByTestId('delete-btn') did not find any elements",
      "classification": {
        "type": "Type B",
        "reason": "Source code testid changed from 'delete-btn' to 'row-delete-btn'",
        "sourceChange": {
          "file": "src/components/UserTable.vue",
          "line": 45,
          "before": "data-testid=\"delete-btn\"",
          "after": "data-testid=\"row-delete-btn\""
        },
        "confidence": 0.95
      },
      "autoHealing": {
        "triggered": true,
        "stepsCompleted": 8,
        "result": "PASS",
        "affectedTestsUpdated": ["UserTable-viewer-any-populated"],
        "durationMs": 15000
      }
    },
    {
      "testName": "Dashboard-editor-defaultSidebar",
      "errorType": "AssertionError",
      "errorMessage": "Expected menu items count 15, got 12",
      "classification": {
        "type": "Type A",
        "reason": "Editor role should see 15 menu items but only 12 rendered — permission filter bug",
        "confidence": 0.88
      },
      "autoHealing": {
        "triggered": false,
        "reason": "Type A — code bug, not test issue"
      }
    },
    {
      "testName": "Login-standard-correctPassword",
      "errorType": "TimeoutError",
      "errorMessage": "Navigation to /inventory timed out after 30s",
      "classification": {
        "type": "Type C",
        "reason": "API /api/products response time 28s in CI environment",
        "confidence": 0.72
      },
      "autoHealing": {
        "triggered": false,
        "reason": "Type C — environment issue, retry recommended"
      }
    }
  ],
  "summary": {
    "typeACount": 1,
    "typeBCount": 1,
    "typeCCount": 1,
    "autoHealingSuccessCount": 1,
    "autoHealingFailureCount": 0,
    "bugsReported": 1,
    "testsUpdated": 2
  }
}
```

---

## 重试与阈值策略

### 重试策略

| 参数 | 值 | 说明 |
|---|---|---|
| 最大重试次数 | 3 | 仅对 TimeoutError 和 NetworkError |
| 超时倍数 | 1.5 | 每次重试增加50%超时（30s → 45s → 67.5s） |
| 重试间隔 | 2s | 避免连续请求冲击 |

### 数据捕获策略

每次失败时自动捕获：

```json
{
  "capture": {
    "screenshot": true,
    "consoleLog": true,
    "networkLog": true,
    "domSnapshot": true,
    "componentTree": true
  }
}
```

- **Screenshot**: PNG 格式，保存到 `test-output/screenshots/`
- **Console Log**: 包含 error/warning 级别
- **Network Log**: 失败请求的 URL、status、response body
- **DOM Snapshot**: accessibility tree JSON
- **Component Tree**: 通过 DevTools 协议提取的 Vue/React 组件树

### 分类置信度阈值

| 置信度范围 | 行动 |
|---|---|
| ≥ 0.90 | 自动执行对应策略 |
| 0.70 - 0.89 | 执行策略但标记为 `low-confidence`，需人工复核 |
| < 0.70 | 标记为 `unclassified`，需人工判断 |

---

## 实战示例

### 示例1: LocatorError 完整分类演练

```
测试: UserTable-admin-showDeleteOn-populated
失败步骤: assertDeleteButtonVisible()
错误: Locator.getByTestId('delete-btn') did not find any elements

Step 1: 获取页面 DOM Snapshot
  → DOM 中无 data-testid="delete-btn" 元素

Step 2: 检查源代码
  → git diff: testid 从 "delete-btn" 改为 "row-delete-btn"
  → 变更者: developer-zhang, 变更原因: "统一命名规范"

Step 3: 分类
  → Type B: 源代码有意变更，测试需更新
  → 置信度: 0.95 (明确的 testid 重命名)

Step 4: 触发自动修复
  → 重新分析 UserTable.vue
  → 更新 locator-catalog.json
  → 更新 UserTablePage POM
  → 重新执行 → PASS ✅
```

### 示例2: AssertionError 完整分类演练

```
测试: Dashboard-admin-defaultSidebar
失败步骤: assertAllMenuItemsVisible()
错误: Expected 15 menu items, found 12

Step 1: 检查页面实际状态
  → 侧边栏确实只显示12个菜单项
  → "系统管理"和"日志审计"缺失

Step 2: 检查源代码
  → 侧边栏组件 Sidebar.vue 中 menuItems 定义包含15项
  → 权限过滤逻辑: admin.shouldSee = 15项
  → 但实际渲染只有12项

Step 3: 检查权限过滤实现
  → filterByRole() 函数有Bug: 2个菜单的权限配置错误
  → "系统管理" requiredRole=["superadmin"] 但 admin 也应可见
  → "日志审计" requiredRole=["superadmin"] 但 admin 也应可见

Step 4: 分类
  → Type A: 代码Bug (权限过滤逻辑错误)
  → 置信度: 0.88 (源代码意图与实现不一致)

Step 5: 不触发自动修复
  → 创建 Bug 报告
  → 测试标记为 known-bug
```

### 示例3: Type B 自动修复周期（组件重命名）

```
变更: UserTable.vue 重命名为 DataTable.vue
       props 从 { users: Array } 改为 { data: Array, columns: Array }

触发失败的测试:
  - UserTable-admin-showDeleteOn-populated
  - UserTable-viewer-any-populated
  - UserTable-any-any-empty

自动修复流程:
  Step 1: 识别 UserTable → DataTable 变更
  Step 2: git diff 确认重命名 + prop 变更
  Step 3: 重新分析 DataTable.vue (Agent 1)
  Step 4: 检查 testid 覆盖 (Agent 2) — 发现新增列需要 testid
  Step 5: 注入 data-testid="column-header-*" (Agent 2 --apply)
  Step 6: 更新定位器目录 (Agent 3)
  Step 7: 生成 DataTablePage POM 替换 UserTablePage (Agent 4)
  Step 8: 重新生成受影响旅程 (Agent 5)
  Step 9: 重新生成测试代码 (Agent 6)
  Step 10: 执行所有 DataTable 测试 → PASS ✅

总耗时: ~5分钟 (自动化)
人工干预: 0 (完全自动)
```

### 示例4: Feature Flag 名称变更自动修复

```
变更: showDeleteButton → enableRowDeletion (Flag名称变更)

触发失败:
  - UserTable-admin-showDeleteOn-populated (排列设置中的 Flag 名过期)

自动修复:
  → Agent 1 重新扫描: 发现 new flag name enableRowDeletion
  → Agent 5 更新排列维度: showDeleteButton → enableRowDeletion
  → Agent 6 更新 beforeEach: window.__FEATURE_FLAGS__.enableRowDeletion = true
  → 重新执行 → PASS ✅

关键: Flag 名称变更不影响POM定位器（定位器基于testid而非Flag名）
     但影响排列设置代码（beforeEach中的Flag设置）
```

---

## 关键原则

1. **分类先于修复** — 不知道失败类型就不行动
2. **Type B 是自动修复的唯一目标** — Type A 报Bug，Type C 重试
3. **修复范围最小化** — 只重新运行受影响的 Agent，不重跑整个流水线
4. **置信度驱动行动** — 低置信度分类需人工复核，高置信度可自动执行
5. **每次修复有审计记录** — 什么变了、为什么变、影响哪些测试