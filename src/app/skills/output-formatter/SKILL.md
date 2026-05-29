---
name: output-formatter
description: 控制测试用例的最终输出格式与规范。确保所有生成的测试用例符合TC-[PROJECT]-[MODULE]-[NNN]编号规范，支持Markdown详细格式和Excel专业格式导出。当用户要求导出或格式化测试用例时激活。
---

# 测试用例输出格式规范 Skill

## 激活场景
- 生成最终测试用例前，确定输出格式
- 用户要求导出特定格式（Excel/Markdown）
- 需要将测试用例导入测试管理工具
- 需要格式化已有的测试用例

---

## 用例编号命名规范

```
格式：TC-[项目代码]-[模块缩写]-[序号]

项目代码：2-4位大写字母（如 CRM / OMS / USER）
模块缩写：2-6位大写字母（常用缩写见下表）
序号：    3位数字，从001开始

示例：
TC-CRM-LOGIN-001   -> CRM项目，登录模块，第1条
TC-OMS-ORDER-012   -> OMS项目，订单模块，第12条
TC-USER-AUTH-001   -> 用户系统，认证模块，第1条
```

**常用模块缩写对照表**：
| 业务模块 | 缩写 | 业务模块 | 缩写 |
|---------|------|---------|------|
| 用户登录 | LOGIN | 权限管理 | AUTH |
| 用户注册 | REG | 商品管理 | PROD |
| 个人信息 | PROFILE | 订单管理 | ORDER |
| 购物车 | CART | 支付结算 | PAY |
| 搜索功能 | SEARCH | 消息通知 | MSG |
| 文件上传 | UPLOAD | 数据导出 | EXPORT |
| 系统设置 | SYS | 报表统计 | REPORT |

---

## 输出格式一：标准Markdown格式（默认）

每个测试用例使用以下Markdown模板输出：

```markdown
---

### TC-[PROJECT]-[MODULE]-[NNN]：[用例标题]

> **模块**：[所属模块名] | **优先级**：[P0/P1/P2/P3] | **类型**：[用例类型] | **方法**：[设计方法]

**前置条件**：
- [条件1，具体且可验证]
- [条件2]

**测试步骤**：

| 步骤 | 操作描述 | 操作对象 |
|------|---------|---------|
| 1 | [具体操作，使用主动动词：输入/点击/选择/上传] | [操作的UI元素或接口] |
| 2 | [具体操作] | [操作对象] |
| N | [具体操作] | [操作对象] |

**测试数据**：
```
[字段名]: [具体值]     # [说明]
[字段名]: [具体值]
```

**预期结果**：
1. [UI层：页面/组件的状态变化，精确描述]
2. [接口层：HTTP状态码、响应体中的关键字段]
3. [数据层：数据库/缓存中的状态变化]
4. [日志层：关键操作日志记录（如需）]

**备注**：关联需求 `REQ-[ID]` | 风险级别：[高/中/低]
```

---

## 输出格式二：表格汇总格式（全模块概览）

生成完所有用例后，提供汇总表格供快速审查：

```markdown
## 测试用例汇总表

| 用例编号 | 用例标题 | 模块 | 优先级 | 类型 | 设计方法 | 前置条件 | 预期结果摘要 |
|---------|---------|------|--------|------|---------|---------|------------|
| TC-XXX-LOGIN-001 | 正确账号密码登录 | 用户登录 | P0 | 功能 | 等价类 | 账号已注册 | 跳转首页，显示用户名 |
| TC-XXX-LOGIN-002 | 错误密码登录 | 用户登录 | P1 | 功能 | 错误推测 | 账号已注册 | 提示密码错误，不跳转 |

**统计摘要**：
| 维度 | 数量 |
|------|------|
| 总用例数 | N |
| P0用例数 | N |
| P1用例数 | N |
| P2用例数 | N |
| P3用例数 | N |
| 功能测试 | N |
| 接口测试 | N |
| 安全测试 | N |
```

---

## 输出格式三：Excel格式（推荐导出）

当用户要求导出 Excel 文件时，使用 `export_test_cases_to_excel` 工具生成 `.xlsx` 文件。

### Excel 文件结构

| 列名 | 对应字段 | 说明 |
|------|---------|------|
| 用例编号 | `id` | TC-XXX-MODULE-NNN 格式 |
| 用例标题 | `title` | 简洁描述验证点 |
| 所属模块 | `module` | 功能模块名称 |
| 用例类型 | `type` | 功能/接口/安全/性能/兼容等 |
| 优先级 | `priority` | P0 / P1 / P2 / P3 |
| 前置条件 | `preconditions` | 支持列表或字符串，自动换行编号 |
| 测试步骤 | `steps` | 列表自动转换为 `序号. 操作 [对象]` 格式 |
| 测试数据 | `test_data` | 键值对自动换行，或直接文本 |
| 预期结果 | `expected_results` | 支持列表或字符串，自动换行编号 |
| 备注 | `remarks` | 需求编号、风险说明等 |

### 样式规范

- 首行为深蓝色（#366092）表头，白色粗体字体
- 所有单元格带有细边框
- 内容列自动换行，默认行高 60 磅、列宽自适应常见场景
- 文件保存路径由调用方指定，建议存放于 `./exports/测试用例_YYYYMMDD.xlsx`

### 调用示例（Python）

```python
from src.app.agents.testcase.tools import export_test_cases_to_excel

test_cases = [
    {
        "id": "TC-CRM-LOGIN-001",
        "title": "正确账号密码登录成功",
        "module": "用户登录",
        "type": "功能测试",
        "priority": "P0",
        "preconditions": ["账号已注册", "账号状态正常"],
        "steps": [
            {"seq": 1, "action": "打开登录页面", "target": "登录页URL"},
            {"seq": 2, "action": "输入用户名", "target": "用户名输入框", "data": "test001"},
            {"seq": 3, "action": "输入密码", "target": "密码输入框", "data": "Test@123"},
            {"seq": 4, "action": "点击登录按钮", "target": "登录按钮"},
        ],
        "test_data": {"username": "test001", "password": "Test@123"},
        "expected_results": [
            "HTTP响应码200，响应体包含 token 字段",
            "页面跳转至 /dashboard",
            "数据库 login_log 表新增一条记录"
        ],
        "remarks": "REQ-LOGIN-001 | 风险级别：低"
    }
]

export_test_cases_to_excel(test_cases, "./exports/CRM登录模块测试用例.xlsx")
```

---

## 格式选择建议

| 用途 | 推荐格式 |
|------|---------|
| 与用户对话/审查 | Markdown详细格式 |
| 快速全量概览 | Markdown表格汇总格式 |
| 导入禅道/Tapd/TestRail | Excel格式 |
| 导入Jira Xray | Excel格式（需额外映射） |
| 需要精美排版、直接发给业务方审阅 | Excel格式 |

> **默认行为**：未指定格式时，优先输出「Markdown详细格式」，每个模块完成后附带「表格汇总格式」
> **导出行为**：当用户明确说"导出Excel"或"生成Excel"时，优先调用 `export_test_cases_to_excel` 工具直接生成文件，而不是在对话中打印表格文本。

---

## 测试管理工具字段映射详表

### 禅道（Zentao）导入字段映射

| 禅道字段 | 本系统字段 | 映射规则 | 必填 |
|---------|-----------|---------|------|
| 用例编号 | `id` | 直接映射 | 是 |
| 用例标题 | `title` | 直接映射 | 是 |
| 所属模块 | `module` | 直接映射 | 是 |
| 用例类型 | `type` | 功能->功能测试，接口->接口测试 | 是 |
| 优先级 | `priority` | P0->1, P1->2, P2->3, P3->4 | 是 |
| 前置条件 | `preconditions` | 列表用换行符连接 | 否 |
| 步骤 | `steps` | 格式化为 `步骤N: 操作 [对象]` | 是 |
| 预期 | `expected_results` | 列表用换行符连接 | 是 |
| 关键词 | `design_method` | 映射为关键词标签 | 否 |
| 需求ID | `requirements` | 直接映射 | 否 |

### TestRail 导入字段映射

| TestRail字段 | 本系统字段 | 映射规则 | 必填 |
|-------------|-----------|---------|------|
| Title | `title` | 直接映射 | 是 |
| Section | `module` | 映射为 Section | 是 |
| Template | - | 固定为 "Test Case (Text)" | - |
| Type | `type` | 直接映射 | 否 |
| Priority | `priority` | P0->Critical, P1->High, P2->Medium, P3->Low | 是 |
| Preconditions | `preconditions` | 直接映射 | 否 |
| Steps | `steps` | 每条步骤单独一行，格式为 `Step N: action` | 是 |
| Expected Result | `expected_results` | 直接映射 | 是 |
| References | `requirements` | 直接映射 | 否 |

---

## 自动保存到数据库

在完成所有测试用例的格式化输出后，**必须**执行以下自动保存流程：

### 保存步骤
1. 调用 `ensure_project(project_name="需求中的项目或产品名称")` 获取或创建项目。**必须传递 project_name 参数**，用需求中的项目或产品名称命名（如 "紫薇养灵玉测试项目"），不要使用默认值 "AI Generated Project"
2. 将格式化后的所有测试用例转换为 `save_test_cases_batch` 所需的 JSON 格式
3. 调用 `save_test_cases_batch(project_id, test_cases)` 保存到数据库
4. 在回复中输出 `[SAVE_RESULT]...[/SAVE_RESULT]` 格式的保存结果

### 用例格式转换规则
将 Markdown 格式的测试用例提取为以下结构：
- `name`: 用例标题（不含编号前缀）
- `steps`: 每个步骤提取为 `{"action": "操作描述", "expected_result": "预期结果"}`
- `priority`: 从 P0/P1/P2/P3 映射为 critical/high/medium/low
- `description`: 用例描述或测试目的
- `preconditions`: 前置条件文本

### 注意事项
- 保存是非破坏性操作，直接执行无需询问用户确认
- 如果保存失败，输出 error 格式的 SAVE_RESULT 并建议用户在管理页面手动创建
- 每次保存后，用户可在「测试用例管理」页面查看已保存的用例
