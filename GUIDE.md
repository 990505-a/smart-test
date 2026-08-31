# 智能测试平台 — 快速入门指南

## 一、平台简介

智能测试平台是一个基于 AI Agent 的测试资产自动生成与管理系统。核心能力：

- **AI 对话生成测试用例** — 上传需求文档，Agent 自动分析并生成高质量测试用例
- **Web UI 自动化测试** — 基于 Playwright 的 Web 界面自动化测试
- **API 自动化测试** — RESTful API 接口自动化测试
- **测试管理** — 项目、文件夹、用例、执行记录的全生命周期管理
- **可视化报告** — 覆盖率、趋势、分布等多维度图表

## 二、系统架构

```
┌─────────────────────────────────────────────────────┐
│                   Next.js 前端 (:3000)                │
│   /chat   /projects   /cases   /runs   /reports     │
├────────────────┬────────────────────────────────────┤
│ LangGraph Agent│        FastAPI 后端 (:8000)         │
│   (:2026)      │   项目/用例/执行 CRUD + 文件上传     │
├────────────────┴────────────────────────────────────┤
│              SQLite 数据库 (本地文件)                  │
└─────────────────────────────────────────────────────┘
```

**三个服务：**

| 服务 | 端口 | 用途 |
|------|------|------|
| Next.js 前端 | 3000 | Web 界面，所有页面 |
| LangGraph Agent | 2026 | AI Agent 对话与工具调用 |
| FastAPI 后端 | 8000 | 数据管理 CRUD、文件上传 |

## 三、启动方式

```bash
# 1. 启动 LangGraph Agent 服务
cd smart-test-platform
langgraph dev --port 2026

# 2. 启动 FastAPI 后端（SQLite，无需安装数据库）
uvicorn src.app.fastapi_app:app --host 0.0.0.0 --port 8000

# 3. 启动前端
cd webui
npm run dev
```

打开 http://localhost:3000 即可使用。

## 四、功能详解

### 4.1 AI 对话（/chat）

平台的核心入口。通过自然语言与 AI Agent 对话，自动完成测试用例生成。

**操作流程：**

1. **选择 Agent** — 顶部标签切换三种 Agent：
   - **用例生成**（TestCase Agent）— 生成测试用例
   - **Web 测试**（Web Agent）— Web 自动化测试
   - **API 测试**（API Agent）— API 自动化测试

2. **上传需求文档** — 对话框支持上传文件：
   - PDF 文件（自动提取文本，支持多模态图片识别）
   - Word 文档（.docx）
   - Excel 表格（.xlsx）
   - 图片（PNG/JPG，需开启多模态模式）

3. **对话生成** — Agent 自动执行 5 阶段工作流：
   - ① 需求分析 → ② 测试策略 → ③ 用例设计 → ④ 质量评审 → ⑤ 输出格式化

4. **自动保存** — 生成的用例自动保存到数据库，对话中显示保存结果卡片

5. **历史记录** — 左侧面板查看历史对话线程，支持多轮对话

**配置项（点击右上角齿轮）：**

| 配置 | 说明 |
|------|------|
| Assistant ID | LangGraph Assistant ID |
| Workspace ID | 工作空间 ID |
| 多模态模式 | 开启后支持图片/PDF 图片识别（需要 OpenAI API Key） |

### 4.2 项目管理（/projects）

管理测试项目。每个项目包含文件夹和测试用例。

- **创建项目** — 填写名称和描述，系统自动生成标识符（如 PRJ-001）
- **编辑/删除** — 修改项目信息或删除（会级联删除下级数据）
- **分页浏览** — 支持翻页查看所有项目

### 4.3 文件夹管理（/folders）

按项目组织测试用例的文件夹树结构。

- **选择项目** — 下拉选择要管理的项目
- **树形结构** — 展示文件夹层级关系
- **创建文件夹** — 支持设置父文件夹，构建多级目录
- **拖拽排序** — 使用拖拽调整文件夹顺序和层级

### 4.4 测试用例（/cases）

查看和管理所有测试用例。

- **列表视图** — 分页展示用例，支持按项目/文件夹筛选
- **用例详情** — 点击进入编辑页面（/cases/[id]）
- **创建用例** — 手动创建单个测试用例
- **编辑模式** — 支持 BDD 模式（Given-When-Then）和标准模式切换
- **步骤编辑** — 增删改测试步骤，设置预期结果

**用例属性：**

| 属性 | 说明 |
|------|------|
| 标识符 | 自动生成（TC-XXXX） |
| 标题 | 测试用例名称 |
| 优先级 | P0/P1/P2/P3 |
| 状态 | draft/active/deprecated |
| 模板 | 标准/BDD |
| 标签 | 自定义标签分类 |

### 4.5 测试执行（/runs）

管理测试执行记录和查看执行结果。

- **选择项目** — 筛选项目的执行记录
- **统计卡片** — 显示总执行数、通过率等汇总指标
- **图表可视化**：
  - **通过率柱状图** — 每次执行的通过/失败/跳过/阻塞分布
  - **状态分布饼图** — 所有执行的总体状态占比
- **创建执行** — 选择项目，勾选用例创建测试执行
- **执行详情** — 弹窗查看每次执行的详细用例结果
- **更新状态** — 修改执行状态（新建/进行中/审核中/已完成/已关闭）

### 4.6 测试报告（/reports）

多维度测试数据可视化看板。

- **项目筛选** — 下拉选择要查看报告的项目
- **汇总统计** — 4 张统计卡片：
  - 总执行次数
  - 总测试用例数
  - 平均通过率
  - 失败用例数
- **三大图表**：
  - **覆盖率柱状图** — 每次执行的通过/失败/跳过/阻塞堆叠柱状图
  - **通过率趋势图** — 各次执行的通过率折线图（0-100%）
  - **状态分布饼图** — 所有用例的状态占比饼图

## 五、AI Agent 技能体系

Agent 内置 7 大技能，按工作流阶段自动调度：

| 技能 | 阶段 | 功能 |
|------|------|------|
| requirement-analysis | ① 需求分析 | 解析需求文档，提取测试点、功能模块、约束条件 |
| test-strategy | ② 策略制定 | 制定测试策略：范围、方法、优先级、风险评估 |
| test-case-design | ③ 用例设计 | 基于等价类/边界值/正交法等设计测试用例 |
| test-data-generator | ④ 数据生成 | 生成有效/边界/无效/安全四类测试数据 |
| quality-review | ⑤ 质量评审 | 评审用例完整性、覆盖率、可执行性，含人工确认检查点 |
| output-formatter | ⑥ 输出格式化 | 格式化为标准用例表格，自动保存到数据库 |
| wiki-query | 知识查询 | 通过 wiki-mcp 查询知识库中的测试规范和最佳实践 |

**中间件处理链：**

```
用户消息 → SkillsMiddleware（加载技能提示词）
         → DynamicModelSelection（检测图片自动切换 GPT-4o）
         → FileContextMiddleware（注入 PDF/图片/Excel 文档内容）
         → LLM（调用 DeepSeek/GPT-4o 生成回复）
```

## 六、Agent 工具

### 用例生成 Agent（TestCase）

| 工具 | 功能 |
|------|------|
| export_test_cases | 导出用例为 Excel/CSV/JSON/Markdown |
| save_test_cases_batch | 批量保存用例到数据库 |
| save_test_case_to_db | 保存单条用例到数据库 |
| list_project_test_cases | 查询项目的测试用例列表 |
| ensure_project | 获取或自动创建项目 |

### Web 测试 Agent（Web）

| 工具 | 功能 |
|------|------|
| detect_test_mode | 识别测试模式（QA/组件测试） |
| check_environment | 检查 Playwright CLI 环境 |
| ensure_output_dir | 创建带时间戳的输出目录 |

### API 测试 Agent（API）

| 工具 | 功能 |
|------|------|
| api_parser | 解析 API 规范文档 |
| playwright_mcp_server | 通过 MCP 调用 Playwright 执行接口测试 |

## 七、数据模型

```
Project（项目）
  └── Folder（文件夹）— 树形层级
        └── TestCase（测试用例）
              ├── TestStep（测试步骤）
              ├── Tag（标签）
              └── Attachment（附件）

TestRun（测试执行）
  └── TestRunTestCase（执行-用例关联）— 含执行状态
```

## 八、环境配置

在项目根目录创建 `.env` 文件：

```env
# LLM API Keys（必填）
DEEPSEEK_API_KEY=your_key_here

# 多模态（可选，需 OpenAI Key）
OPENAI_API_KEY=your_key_here
ENABLE_PDF_MULTIMODAL=true

# 服务地址
LANGGRAPH_API_URL=http://localhost:2026

# 数据库（SQLite，无需配置）
# 数据库文件自动创建在项目根目录: smart_test_platform.db
```

## 九、快速体验流程

```
1. 启动三个服务（见第三节）
2. 打开 http://localhost:3000 → 自动跳转到 /chat
3. 在 /chat 选择「用例生成」Agent
4. 上传一份需求文档（PDF/Word/Excel）
5. 发送 "请根据文档生成测试用例"
6. Agent 自动执行 5 阶段工作流并生成用例
7. 用例自动保存，点击结果卡片中的链接跳转到管理页面
8. 前往 /cases 查看生成的用例
9. 前往 /runs 创建测试执行
10. 前往 /reports 查看可视化报告
```

## 十、技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Next.js 15 + React 19 + Tailwind CSS 4 + shadcn/ui |
| 图表 | recharts |
| 数据管理 | SWR（缓存 + 自动重新验证） |
| 后端 | Python 3.12+ + FastAPI + SQLAlchemy 2.0 (async) |
| 数据库 | SQLite（本地开发）/ PostgreSQL（生产） |
| AI Agent | DeepAgents + LangGraph + LangChain |
| LLM | DeepSeek Chat（文本）+ GPT-4o（多模态） |
| 文档处理 | PyMuPDF4LLM（PDF）+ python-docx（Word）+ openpyxl（Excel） |
