# 课堂 2026-05-20 代码 vs 我们的智能测试平台 — 完整对比报告

> 课堂源码目录: `D:\test_agent\2026-05-20-ai-test-agent-system-platform\`
> 我们的项目: `D:\test_agent\smart-test-platform\`

---

## 一、总体架构对比

| 维度 | 课堂 (2026-05-20) | 我们的项目 |
|------|-------------------|-----------|
| 数据库 | PostgreSQL + MongoDB + MinIO | SQLite |
| Agent 数量 | 2 个 (api_agent, web_agent) | 3 个 (testcase_agent, web_agent, api_agent) |
| Web 自动化 | Playwright MCP (浏览器直接控制) | deepagents Shell Backend (命令行方式) |
| MCP 集成 | GitNexus (代码分析) + Playwright (浏览器) | 无 |
| Skills | 14 个专业技能 (.claude/skills/) | 5 个旧 web skills |
| 中间件 | SkillsMiddleware + ContextInjection + ErrorHandler | SkillsMiddleware 仅 |
| 前端框架 | Next.js + Shadcn/ui + Monaco Editor | Next.js + Shadcn/ui |
| 部署 | 生产级 (Docker + 部署元数据) | 开发模式 (本地 SQLite) |

---

## 二、Agent 定义差异

### 2.1 API Agent

#### 课堂版本 (`backend/app/agents/api/agent.py`)

**LLM 配置**: `deepseek:deepseek-chat`

**工具注册**: 28+ 工具
- `batch_tools.py` — 批量操作
- `openapi_tools.py` — OpenAPI 解析
- `scenario_tools.py` — 场景测试
- `script_execution_tools.py` — 脚本执行
- `script_tools.py` — 脚本管理
- `test_artifacts_tools.py` — 测试产物管理
- `test_execution_tools.py` — 测试执行
- GitNexus MCP 工具 (通过 MCP 自动加载)

**Skills**: 6 个专业技能
- `api/planner` — 测试计划生成
- `api/generator` — 测试代码生成
- `api/executor` — 测试执行
- `api/healer` — 失败自修复
- `api/reporter` — 报告生成
- `api/scenario` — 场景测试编排

**中间件**:
- `SkillsMiddleware` — 技能加载
- `APIContextInjectionMiddleware` — 运行时上下文注入 (project_id, folder_id 等)

**系统提示词特点**:
- 引用 MASTEST 学术方法论 (arXiv:2511.18038)
- 7 类故障分类: TEST_BUG, API_CHANGE, AUTH_EXPIRED, DATA_ISSUE, ENV_ISSUE, FLAKY, REAL_BUG
- 强制自动保存: 生成的计划/脚本/场景必须保存到数据库
- 完整 4 工作流: 计划 → 生成 → 执行 → 修复

#### 我们的版本 (`src/app/agents/api/agent.py`)

**LLM 配置**: `deepseek:deepseek-chat`

**工具注册**: ~15 工具
- `db_tools.py` (9) — CRUD 操作
- `openapi_tools.py` (5) — OpenAPI 解析
- `execution_tools.py` (7) — 执行相关
- `scenario_tools.py` (10) — 场景管理

**Skills**: 无 (api agent 没有加载任何技能)

**中间件**: 无自定义中间件

**系统提示词**: 较简单，没有学术方法论、故障分类或自动保存要求

#### 差异总结:
- ❌ 缺少 GitNexus MCP 集成
- ❌ 缺少 6 个 API 专业技能
- ❌ 缺少 ContextInjectionMiddleware
- ❌ 系统提示词不够专业 (无 MASTEST 方法论)
- ❌ 缺少自动保存机制
- ❌ 缺少故障自修复工作流

---

### 2.2 Web Agent

#### 课堂版本 (`backend/app/agents/web_mcp/agent.py`)

**LLM 配置**: `deepseek:deepseek-chat`, extended token limit

**工具注册**: Playwright MCP 工具 + 本地工具
- Playwright MCP 通过 stdio 传输自动加载浏览器操作工具
- 本地工具: web 测试管理、脚本执行

**Skills**: 8 个专业技能
- `web_mcp/planner` — 测试规划
- `web_mcp/generator` — 脚本生成
- `web_mcp/executor` — 测试执行
- `web_mcp/healer` — 失败自修复 (最多重试 3 次)
- `web_mcp/reporter` — 报告生成
- `web_mcp/explorer` — 页面探索
- `web_mcp/prerequisite` — 依赖分析
- `web_mcp/case-designer` — 用例设计

**中间件**:
- `SkillsMiddleware`
- `WebContextInjectionMiddleware` — 项目/文件夹上下文注入
- `ToolErrorHandler` — 工具调用错误处理与恢复

**系统提示词特点**:
- 完整的 Web 测试工作流
- 自动修复机制 (最多 3 次重试)
- 浏览器会话管理
- 基于 MCP 的实时浏览器控制

#### 我们的版本 (`src/app/agents/web/agent.py`)

**LLM 配置**: `deepseek:deepseek-chat`

**工具**: 3 个自定义工具 + deepagents 内置工具
- `detect_test_mode` — 模式识别
- `check_environment` — 环境检查
- `ensure_output_dir` — 目录创建

**Skills**: 5 个旧技能 (pw-dogfood, component-aware 等)

**中间件**: 仅 `SkillsMiddleware`

**Backend**: CompositeBackend (shell + file), 不是 Playwright MCP

#### 差异总结:
- ❌ 完全不同的自动化方式 (Shell Backend vs Playwright MCP)
- ❌ 缺少 8 个 Web 专业技能
- ❌ 缺少 ToolErrorHandler
- ❌ 缺少 WebContextInjectionMiddleware
- ❌ 无浏览器会话管理
- ❌ 无自动修复能力

---

### 2.3 TestCase Agent (我们有，课堂没有)

我们有一个专门的 `testcase_agent` 用于基于文档的测试用例生成，课堂没有这个 agent。这是一个差异点但不是劣势 — 我们的功能更细分。

---

## 三、Graph 配置对比

### 课堂 (`graph.json`)
```json
{
  "graphs": {
    "api_agent": {
      "path": "./backend/app/agents/api/agent.py:agent"
    },
    "web_agent": {
      "path": "./backend/app/agents/web_mcp/agent.py:agent"
    }
  }
}
```

### 我们 (`graph.json`)
```json
{
  "graphs": {
    "testcase_agent": { "path": "./src/app/agents/testcase/agent.py:agent" },
    "web_agent": { "path": "./src/app/agents/web/agent.py:agent" },
    "api_agent": { "path": "./src/app/agents/api/agent.py:agent" }
  }
}
```

**差异**:
- 课堂只有 2 个 agent，我们有 3 个
- 课堂的 web_agent 用 Playwright MCP，我们的用 Shell Backend
- 课堂路径结构为 `backend/app/agents/`，我们的为 `src/app/agents/`

---

## 四、后端 API 端点对比

### 课堂新增端点 (我们没有)

| 端点文件 | 功能 |
|---------|------|
| `web_tests.py` | Web 测试管理 CRUD |
| `web_functions.py` | Web 功能/子功能管理 |
| `configurations.py` | 系统配置管理 |
| `documents.py` | 文档管理 |
| `test_plans.py` | 测试计划管理 |
| `test_results.py` | 测试结果管理 |
| `api_tests_extended.py` | 扩展 API 测试能力 |
| `attachments.py` | 文件附件上传 |

### 我们有、课堂没有的

| 端点文件 | 功能 |
|---------|------|
| `workspaces.py` | 工作空间管理 (Phase 13 新增) |

### 共有的

| 端点 | 课堂 | 我们 |
|------|------|------|
| `projects.py` | ✅ | ✅ |
| `folders.py` | ✅ | ✅ |
| `test_cases.py` | ✅ | ✅ |
| `test_runs.py` | ✅ | ✅ |
| `api_tests.py` | ✅ | ✅ |
| `scenarios.py` | ✅ | ✅ |

---

## 五、数据库模型对比

### 课堂独有的模型

| 模型 | 说明 |
|------|------|
| `team.py` | 团队管理 |
| `configuration.py` | 系统配置 |
| `web_function.py` | Web 功能定义 |
| `web_test.py` | Web 测试记录 |
| `attachment.py` | 文件附件 |

### 课堂的 MongoDB 模型 (我们完全没有)

| 模型 | 说明 |
|------|------|
| `api_test_log.py` | API 测试日志 |
| `attachment.py` | 附件存储 |
| `audit_log.py` | 审计日志 |
| `version_history.py` | 版本历史 |

### 我们独有的模型

| 模型 | 说明 |
|------|------|
| `workspace.py` | 工作空间 (Phase 13) |

### 共有模型

`project.py`, `folder.py`, `test_case.py`, `test_run.py`, `test_result.py`, `api_endpoint.py`, `api_test.py`, `test_scenario.py`

---

## 六、Skills 对比

### 课堂 Skills (14 个)

#### API 技能 (6 个)
| 技能 | 路径 | 功能 |
|------|------|------|
| planner | `.claude/skills/api/planner/` | 测试计划生成 |
| generator | `.claude/skills/api/generator/` | 测试代码生成 |
| executor | `.claude/skills/api/executor/` | 测试执行 |
| healer | `.claude/skills/api/healer/` | 失败自修复 |
| reporter | `.claude/skills/api/reporter/` | 报告生成 |
| scenario | `.claude/skills/api/scenario/` | 场景编排 |

#### Web MCP 技能 (8 个)
| 技能 | 路径 | 功能 |
|------|------|------|
| planner | `.claude/skills/web_mcp/planner/` | 测试规划 |
| generator | `.claude/skills/web_mcp/generator/` | 脚本生成 |
| executor | `.claude/skills/web_mcp/executor/` | 测试执行 |
| healer | `.claude/skills/web_mcp/healer/` | 失败自修复 |
| reporter | `.claude/skills/web_mcp/reporter/` | 报告生成 |
| explorer | `.claude/skills/web_mcp/explorer/` | 页面探索 |
| prerequisite | `.claude/skills/web_mcp/prerequisite/` | 依赖分析 |
| case-designer | `.claude/skills/web_mcp/case-designer/` | 用例设计 |

### 我们的 Skills (5 个旧 Web 技能)
| 技能 | 路径 | 功能 |
|------|------|------|
| pw-dogfood | `src/app/agents/web/skills/pw-dogfood/` | QA 探索测试 |
| component-aware-web-automation | `src/app/agents/web/skills/...` | 组件级自动化 |
| agent-browser | `src/app/agents/web/skills/...` | Agent Browser 参考 |
| playwright-cli | `src/app/agents/web/skills/...` | Playwright CLI 参考 |
| agent-browser-vs-playwright-cli | `src/app/agents/web/skills/...` | 框架选择指南 |

**差距**: 我们缺少 14 个专业测试技能，而且现有 5 个技能是参考资料而非工作流技能。

---

## 七、前端页面对比

### 课堂前端页面 (更完整)

| 页面路由 | 功能 |
|---------|------|
| `/` | 首页/仪表盘 |
| `/projects` | 项目列表 |
| `/projects/[id]/test-cases` | 测试用例管理 |
| `/projects/[id]/test-plans` | 测试计划 |
| `/projects/[id]/test-runs` | 测试执行 |
| `/projects/[id]/api-tests` | API 测试 |
| `/projects/[id]/web-tests` | Web 测试 |
| `/projects/[id]/scenario-tests` | 场景测试 |
| `/projects/[id]/reports` | 报告分析 |
| `/projects/[id]/fullstack-analysis` | 全栈分析 |
| 内置 LangGraph 聊天组件 | 多 Agent 对话 |
| Monaco 代码编辑器 | 脚本编辑/查看 |

### 我们的前端页面

| 页面路由 | 功能 |
|---------|------|
| `/` | 聊天页面 (Agent 对话) |
| `/projects` | 项目管理 |
| `/cases` | 测试用例 |
| `/folders` | 文件夹管理 |
| `/scenarios` | 测试场景 |
| `/runs` | 测试执行 |
| `/reports` | 测试报告 |

**差异**:
- ❌ 我们没有 Web 测试页面
- ❌ 我们没有测试计划页面
- ❌ 我们没有全栈分析页面
- ❌ 我们没有 Monaco 代码编辑器
- ❌ 我们的页面不以项目为维度组织
- ✅ 我们有独立的工作空间选择器

---

## 八、关键架构差异

### 8.1 数据库栈

| | 课堂 | 我们 |
|---|------|------|
| 关系数据库 | PostgreSQL | SQLite |
| 文档数据库 | MongoDB | 无 |
| 对象存储 | MinIO | 无 |
| 数据迁移 | Alembic | 无 |

### 8.2 MCP 集成

| MCP 服务 | 课堂 | 我们 |
|---------|------|------|
| GitNexus (代码分析) | ✅ stdio | ❌ |
| Playwright (浏览器) | ✅ stdio | ❌ |
| Docling (文档) | ❌ | ❌ |

### 8.3 自动化方式

| 方面 | 课堂 Web Agent | 我们的 Web Agent |
|------|---------------|-----------------|
| 浏览器控制 | Playwright MCP (直接) | Shell Backend + playwright-cli (间接) |
| 脚本语言 | TypeScript (Playwright) | TypeScript (Playwright) |
| 执行方式 | MCP 实时会话 | 命令行执行 |
| 错误恢复 | 自动修复 (3 次重试) | 无 |

---

## 九、优先对齐建议

按影响力排序：

### P0 — 核心能力缺失
1. **Skills 迁移** — 将课堂 14 个 Skills 复制到项目中并注册到 Agent
2. **API Agent 系统提示词升级** — 采用 MASTEST 方法论 + 故障分类 + 自动保存
3. **Web Agent 替换为 Playwright MCP** — Shell Backend → Playwright MCP

### P1 — 功能增强
4. **ContextInjectionMiddleware** — 注入 project_id/folder_id 上下文
5. **ToolErrorHandler** — 工具调用错误处理
6. **Web 测试管理 API + 前端** — web_tests, web_functions 端点和页面

### P2 — 完善度
7. **GitNexus MCP 集成** — 代码分析能力
8. **配置管理** — configurations 端点
9. **前端项目维度组织** — 以 /projects/[id]/ 为路由前缀

### P3 — 生产化
10. **PostgreSQL 迁移** — 从 SQLite 升级
11. **MongoDB 日志** — 审计和测试日志
12. **Alembic 迁移** — 数据库版本管理
