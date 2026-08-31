---
name: testcase-workflow
description: 测试用例生成的通用工作流技能：需求澄清与需求包 → 风险覆盖规划 → 可追踪用例草稿 → 确定性 Lint → 隔离上下文复核 → 人工批准发布。收到生成测试用例、从需求到用例、制定测试方案等任务时触发。
---

# 测试用例生成工作流

流程仍可概括为 **分析 → 设计 → 交付**，但每个阶段增加了可验证的质量控制点：

```text
需求证据 → 需求包/验收例子 → 风险与覆盖计划 → 用例草稿
→ 确定性 Lint → 隔离上下文二次复核 → 人工批准 → 发布
```

Skill 提供测试方法和领域检查项；流程状态、Lint 门禁和发布权限由平台代码控制。不要把一次 LLM 自评称为独立评审，也不要把飞书导出称为内部发布。

## 阶段一：需求澄清与需求包

1. 读取上传文件：聊天上传的 PDF/Markdown 通常先保存到 `/uploads/{thread_id}/`，消息只提供路径引用；需要调用 `read_file` 读取完整文本。不要假定文本已经自动嵌入上下文。
2. 先读取本 Skill 和命中的模块方法论 Skill，再按需检索 `/repo/` 代码和配置。产品规则必须有需求、代码或其他来源证据；无法确认的内容不能当作事实。
3. 调用 `save_requirement_package(project_name, package)`，至少保存：
   - 需求目标、范围与明确排除项；
   - 唯一 `REQ-*`、验收例子、前置条件、输入约束和可观察结果；
   - 风险 `RISK-*`、涉及角色和状态；
   - `source_manifest`（上传文件/代码路径及可用的来源 hash）；
   - `assumptions`、`unresolved_questions` 和每个问题是否 `blocking`；
   - `coverage_plan`（每个 REQ 的正向、负向、边界、异常/恢复、并发等计划）。
4. 缺少业务事实时优先向用户提澄清问题。高风险未决问题必须标记为 blocking，不能直接批准；用户要求继续时只能生成带显式假设的草稿。每次生成或修复结束时，必须把所有 unresolved_questions 编号后在聊天中逐条向用户提问（说明每条影响的 REQ/CASE），答案通过聊天回复获得——用例页面只读展示问题，不提供作答入口。
5. 需求包的最小结构示例：

```json
{
  "package_id": "PKG-TDCZ-001",
  "strict": true,
  "requirements": [{
    "id": "REQ-TDCZ-001",
    "summary": "...",
    "acceptance_criteria": ["..."],
    "risk": "P0",
    "source_refs": ["需求文档第3节", "repo:src/...:42"]
  }],
  "coverage_plan": [{
    "requirement_id": "REQ-TDCZ-001",
    "scenarios": ["positive", "negative", "boundary", "recovery"],
    "case_ids": [],
    "not_applicable_reason": ""
  }],
  "scope": {"in": [], "out": []},
  "assumptions": [],
  "unresolved_questions": [],
  "source_manifest": []
}
```

## 阶段二：用例设计

1. 根据需求包和覆盖计划设计，不要跳过覆盖计划直接写最终用例。
2. 每条用例都要能追溯到需求和风险。没有需求依据的候选行为要标为假设或待确认。
3. 模块 Skill 冲突时以模块 Skill 的领域规则为准，但仍必须遵守平台的可追踪元数据和发布门禁。
4. 通用方法包括等价类、边界值、异常路径、决策表、状态转换、权限、并发和恢复。无模块 Skill 时，每个明确功能点至少设计正向、负向和边界场景；数量不是质量证明。
5. 紧耦合模块的跨模块状态流转、阶段衔接和统一结算由主 Agent 统一设计；松耦合模块可以用 task 并行，但 task 不是评审 Agent。
6. 每一步必须是 QA 能执行的动作，每一步尽量有可观察的预期结果；预期不得用“正常处理”“适当提示”等无法判定的占位语。

## 阶段三：可追踪 Markdown 草稿

保留现有 Markdown 树结构，标题层级仍对应飞书导图。每个可识别用例标题下紧邻一行独立 HTML comment：

```markdown
#### 活动进行中展示正确排行榜 [P0]
<!-- CASE: CASE-TDCZ-001; REQ: REQ-TDCZ-001; RISK: RISK-TDCZ-001 -->

前置：活动已开始，账号已有积分

- 打开排行榜 ⇒ 展示当前赛季排行榜
- 核对服务端数据 ⇒ 页面排名与返回数据一致
```

约束：

- `CASE` 每个用例恰好一个且全文唯一；`REQ`、`RISK` 至少一个，可用英文逗号引用多个且不可重复。
- ID 使用大写 ASCII 短横线格式，例如 `CASE-TDCZ-001`、`REQ-TDCZ-001`、`RISK-TDCZ-001`。
- comment 必须独占一行，不能与标题同行、不能放在列表项或代码围栏内。
- 标题保持纯业务标题，不放 `CASE-*`、`REQ-*`、`RISK-*` 或旧式 `TC-*`；不要把 ID 放进步骤或可见表格，以免污染飞书节点。
- 使用 `前置：` 和 `- 操作 ⇒ 预期`；2 个空格缩进表示嵌套步骤。
- `✅/❌/⚠️` 和 `>` 批注是人工反馈标注，不等于正式批准状态。

## 阶段四：保存、Lint 与二次复核

1. 阶段开始时调用 `get_beijing_timestamp()` 并在文档名中复用同一时间戳。
2. 调用 `save_case_document(project_name, content)` 保存完整 Markdown 草稿。续传前必须 `read_case_document`，再整体覆盖保存；平台返回 revision、hash 和 Lint 摘要。
3. 保存后调用 `lint_case_document(project_name, strict=true)`。发现错误时修复后最多重试 2 轮；Lint 失败可以保留草稿，但不得声称通过或可发布。
4. Lint 通过后调用 `review_case_document(project_name)`。Reviewer 使用隔离上下文，只输出需求覆盖、事实依据、可执行性、矛盾、重复、边界/异常/权限/并发/恢复问题清单，不输入生成 Agent 的自评或思考过程。
5. Reviewer 存在 `blocker/high` 时，修复或回到需求澄清；最多复核 2 轮。仍未解决时交给人工，不得靠继续猜测通过。
6. `get_case_workflow_status(project_name)` 可查询 `draft/generated/in_review/changes_requested/approved/released`、Lint 和 Review 状态。Agent 不得使用批准工具冒充用户批准。

## 阶段五：人工批准与发布

平台状态遵循：

```text
draft → generated → in_review → approved → released
                 ↘ changes_requested → draft
```

批准/发布的前置条件由后端强制检查：

- Lint 无 blocking error；
- 高风险未决问题已处理或由责任人接受；
- Review 无 blocker/high；
- 批准时 revision/hash 与评审基线一致。

人工在 `/cases` 页面批准具体版本后，才可以发布。飞书导出只是外部展示同步，不代表内部发布；只有用户明确批准后才建议导出。

## Human-in-the-Loop

生成、保存、Lint、查询是草稿流程，可自动执行；覆盖已发布版本、批准、发布、删除等具有不可逆影响的动作必须由用户明确确认。当前页面中的人工 `✅/❌/⚠️` 继续用于反馈和自进化，但不替代正式 review/approve 状态。
