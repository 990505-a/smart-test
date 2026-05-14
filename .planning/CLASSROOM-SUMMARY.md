# 课堂内容总结 & 作业梳理

> 涵盖 2026-03-14 至 2026-05-13 共 13 节课，按时间线梳理每节课的核心内容、技术要点和作业要求。

---

## 第1节 2026-03-14 基于文档链接的测试用例生成

### 核心内容
- **技术栈确定**: Python 3.13 后端 + Node.js 前端
- **开发工具**: PyCharm（运行/手写代码）+ VSCode（AI Coding）
- **AI Coding 工具**: Augment Code / Kimi Code / Claude Code
- **Agent 框架选择**: LangChain + LangGraph API（放弃 FastAPI+Agent 手工集成）
- **LangGraph API 服务**: `uv add "langgraph-cli[inmem]"` + graph.json 配置 + start_server.py 启动

### 技术要点
1. **智能体发布**: 通过 LangGraph CLI 发布 Agent，提供 REST API 接口
2. **前端对接**: testing-deep-agents-ui 页面（yarn install + npm run dev）
3. **智能体与前端通信**: 前端 → LangGraph API → Agent
4. **MCP 工具集成**: Docling MCP（文档解析），`uvx --from docling-mcp docling-mcp-server --transport sse`

### 作业
- [x] 完成课堂所有功能：Agent + 前端 + Docling MCP
- [ ] 前端上传 PDF，借助 Docling MCP 完成指定任务（可选）

---

## 第2节 2026-03-21 图文并茂文档解析中间件

### 核心内容
- **消息类型**: HumanMessage / AIMessage / ToolMessage / SystemMessage
- **文件上传方式**: 前端 base64 编码（推荐） vs 后端上传接口（传统）
- **PDF 解析器开发**: PyMuPDF4LLMLoader + LLMImageBlobParser（图片理解）
- **中间件开发**: AgentMiddleware，拦截消息 → 解析 PDF → 注入 SystemMessage

### 技术要点
1. **文件格式**: base64 PDF 数据放在 HumanMessage.additional_kwargs.attachments 中
2. **PDF 解析**: PyMuPDF4LLMLoader 提取文本 + LLMImageBlobParser(GPT-4o) 解析图片
3. **中间件模式**: 拦截请求 → 提取附件 → 解析文档 → 追加到 SystemMessage
4. **多模态模型**: 豆包 Vision（火山方舟）用于图片理解

### 作业
- [x] 完成前后端部署运行，全面测试找 bug
- [x] 前端增加开启/关闭多模态解析按钮
- [ ] 对话中包含在线文档链接，解析链接对应的 PDF 文档（可选）

---

## 第3节 2026-03-25 DeepAgents 及 Skills 基础应用

### 核心内容
- **create_agent() 参数**: 系统提示词、工具、MCP、技能、中间件
- **Skills 规范**: https://agentskills.io/specification
- **Skill 创建工具**: skill-creator（Anthropic 官方）
- **前端多模态开关**: ENABLE_PDF_MULTIMODAL 参数通过 additional_kwargs 传递

### 技术要点
1. **前端传参**: 开关状态放入 HumanMessage.additional_kwargs，后端读取控制行为
2. **Skills = 子智能体**: 每个 Skill 是一个 SKILL.md 文件，描述特定领域知识
3. **SkillsMiddleware**: 自动加载 SKILL.md 文件到系统提示词

### 作业
- [x] 创建测试用例生成相关技能（5个 Skills）
- [x] 基于 DeepAgents 验证技能功能

---

## 第4节 2026-03-28 基于文档用例生成系统及 Skills

### 核心内容
- **目标**: 100% 企业落地可用的测试用例
- **5大 Skills 闭环**: 需求分析 → 测试点提取 → 用例编写 → 用例评审 → 用例输出
- **Skills 提示词模板**: 严格按照 agentskills.io 规范
- **自定义工具**: export_test_cases（Excel 导出）
- **多文件支持**: pdf + image 上传解析

### 技术要点
1. **Skills 质量标准**: 可执行性、完整性、可追踪性、一致性、可维护性、可评估性
2. **技能间数据流**: 上一技能输出作为下一技能输入
3. **端到端流程**: 上传文件 → 输入需求 → 磁盘输出 Excel
4. **系统提示词**: 基于 Skills 优化，明确 5 阶段强制流程

### 作业
- [x] 开发 Excel 导出工具
- [x] 支持上传多文件解析并问答
- [x] 基于 Ollama 部署 qwen3-embedding:0.6b 嵌入模型（选做）

---

## 第5节 2026-04-01 RAG 流程及 RAGAnything 基础

### 核心内容
- **RAG 概念**: Embedding（向量嵌入）→ 向量数据库 → 语义检索
- **RAG 流程**: 文档切分 → 嵌入转换 → 存储 → 召回（相似度查询）→ 上下文注入
- **RAGAnything**: https://github.com/HKUDS/RAG-Anything
- **Ollama 部署**: qwen3-embedding:0.6b 本地嵌入模型

### 技术要点
1. **嵌入模型**: 将文本转为 1024 维向量
2. **语义检索 vs 关键字检索**: "I love beijing" ≈ "我爱北京"
3. **Agentic RAG**: Agent 自主决定何时检索
4. **两种使用模式**: 直接多文件对话 + 通过知识库检索上下文对话

### 作业
- [x] 上传 PDF/图片进行向量化处理
- [x] 对话界面进行向量检索和对话
- [x] 多文件解析问答持续优化

---

## 第6节 2026-04-08 开源知识库 RAG 部署

### 核心内容
- **两种 RAG 方案对比**:
  - RAGAnything 定制开发：灵活但工作量大
  - LightRAG 二次开发（推荐）：已有前端 + API
- **LightRAG 部署**: lightrag-server（后端）+ lightrag_webui（前端）
- **处理流程**: 提取页面文本 → 向量嵌入 → 多模态处理（图片/表格）→ 知识图谱构建

### 技术要点
1. **LightRAG Server**: 端口 9621，支持文件上传、知识图谱查看、API 接口
2. **前端构建**: `bun install --frozen-lockfile` + `bun run build`
3. **RAGAnything 可集成到 LightRAG**: 增强多模态能力

### 作业
- [x] 部署 LightRAG 项目正常运行

---

## 第7节 2026-04-11 测试用例智能体集成

### 核心内容
- **前端增加 RAG 开关**: enable_rag 控制 Agent 是否调用 RAG MCP 工具
- **Context 机制**: 通过 context_schema 传递运行时参数
- **智能体功能总结**:
  1. 图片/PDF 上传编写用例
  2. 输入需求，自动调用 RAG MCP 完成上下文搜索
  3. 保存用例到 Excel

### 技术要点
1. **context_schema**: `@dataclass class Context: enable_rag: bool`
2. **前端传参**: context 参数传递给 agent.invoke()
3. **未开启 RAG**: 不应调用 rag mcp 工具
4. **开启 RAG**: 自动调用 rag mcp 工具获取上下文

### 作业
- [x] 实现测试用例智能体系统完整功能，验证用例生成质量

---

## 第8节 2026-04-15 测试用例智能体及 RAG 系统优化

### 核心内容
- **用例生成完整流程梳理**:
  1. 输入完整需求（纯文字）→ 直接与 LLM 对话（Skills）
  2. 上传图片 → base64 → 动态切换多模态模型
  3. 上传 PDF → base64 → 中间件解析 → ToolMessage
- **RAGMiddleware**: 控制 RAG 调用逻辑
- **系统提示词优化**: 清晰梳理业务流，每个任务对应相应技能

### 技术要点
1. **正常使用方式**: 上传图片或 PDF 时默认关闭 RAG
2. **RAG 开启方式**: 通过 RAGMiddleware 控制
3. **Skills 驱动业务流**: 用例生成及 RAG 检索的具体逻辑借助 Skills 实现

### 作业
- [x] 优化系统提示词，实现生产级可落地的用例生成智能体

---

## 第9节 2026-04-22 DeepAgents & Playwright-CLI Web 自动化

### 核心内容
- **Web 自动化方案对比**:
  - Selenium: 传统 DOM 解析 → 定位元素 → 编写脚本 → 运行
  - Playwright: 现代 Agent + CLI/MCP
  - 视觉模型: 成本高（生成+运行都依赖视觉模型）
- **Playwright 三种模式**:
  - Agents: 智能体直接控制
  - MCP: 22 个工具全部暴露给 LLM（token 消耗大）
  - **CLI（推荐）**: 只需 1 个 execute 工具，MCP 作为辅助
- **测试目标**: fecshop 电商系统（前后端）

### 技术要点
1. **CLI 优势**: 22 个命令封装为 1 个 execute 工具，大幅降低 token 消耗
2. **OpenClaw / Hermes**: Agent + CLI 的 Web 自动化方案
3. **hosts 配置**: 指向 fecshop 测试环境

### 作业
- [x] 基于 Playwright-CLI + DeepAgents 完成 fecshop 全面测试脚本

---

## 第10节 2026-04-25 Hermes Agent 部署及 Web 自动化优化

### 核心内容
- **Hermes Agent**: 浏览器自动化代理，支持 API Server 模式
- **OpenWebUI**: 开源 Web 界面，与 Hermes 对接
- **Web 自动化工具对比**: 内置 browser / playwright-cli / agent-browser / playwright-mcp

### 技术要点
1. **Hermes 部署**: Linux 环境，API Server 模式
2. **API Server 配置**: API_SERVER_ENABLED=true, API_SERVER_KEY
3. **与 OpenWebUI 集成**: 通过 API Key 连接

### 作业
- [x] 部署 Hermes Agent + OpenWebUI
- [x] 评估 playwright-cli vs agent-browser 效果
- [x] 优化 Web 智能体 Skills 及系统提示词

---

## 第11节 2026-04-29 接口自动化 MCP Server 及 Graphify 知识图谱

### 核心内容
- **接口自动化方案**:
  1. 基于 openapi.json
  2. 基于源码分析（Java Controller / Python FastAPI）
- **Playwright MCP**: `@executeautomation/playwright-mcp-server`（API 测试）
- **Graphify**: 代码知识图谱，通过 MCP 获取接口源码信息

### 技术要点
1. **Playwright API 测试**: 支持完整的 HTTP 方法（GET/POST/PUT/DELETE/PATCH）
2. **Graphify MCP**: 从源码提取 API 端点、数据模型、调用图
3. **Skill + MCP 结合**: 业务场景驱动 → 用例设计 → 脚本生成 → 测试执行 → 报告
4. **多框架访问**: 修改 .env 让任何智能体框架访问 Hermes

### 作业
- [x] 优化 playwright-mcp 的提示词及 Skills
- [x] 基于 Graphify 构建代码知识图谱
- [ ] Hermes 多框架访问配置

---

## 第12节 2026-05-07 论文及 RESTful 接口自动化落地

### 核心内容
- **MASTEST 方法论** (arXiv:2511.18038): 学术界 RESTful API 测试方法
- **Agent 框架代码结构**: llm + skills + tools + mcp + backend + system_prompt + middleware
- **测试报告可视化**:
  - Skills + CLI: antvis/chart-visualization-skills
  - MCP 工具: antvis/mcp-server-chart
- **Human-in-the-Loop**: 参考 DeepAgents 官方文档

### 技术要点
1. **mcp-swagger-parser**: npm 包解析 OpenAPI/Swagger 规范
2. **测试报告图形化**: 使用 Skills 生成图表（推荐）或 MCP 工具生成
3. **人工反馈**: 在关键节点暂停等待人工确认

### 作业
- [ ] playwright_api_tools 不需要的工具清理
- [ ] 测试报告图形化展示
- [ ] 加入人工反馈（Human-in-the-Loop）

---

## 第13节 2026-05-13 测试智能体平台前后端实现（最新）

### 核心内容
- **平台架构 = 前端页面 + 后端服务(FastAPI) + 智能体服务(LangGraph)**
- **三层服务架构**:
  1. 前端页面（Next.js, npm run dev, 端口 3000）
  2. 后端服务（FastAPI, main.py, 端口 8000）
  3. 智能体服务（LangGraph API, start_server.py, 端口 2026）
- **0→1 实现思路**: 参考 BrowserStack Test Management + 禅道
- **分层架构**: 前端界面 → Schema → API 接口层(api/v2) → 服务层 → Models → 数据库

### 技术要点
1. **FastAPI 后端**: 传统 CRUD + 业务逻辑，独立于 Agent
2. **LangGraph Agent**: 专注 AI 能力，通过 Skills + Tools + MCP 完成智能测试
3. **数据库**: PostgreSQL（主）+ MongoDB（灵活数据）
4. **文件存储**: MinIO 对象存储
5. **前端**: Next.js 14 + Radix UI + SWR + Monaco Editor
6. **关键数据模型**: Projects → Folders → TestCases/TestSteps → TestRuns → TestResults
7. **API 端点管理**: APIEndpoints + TestScenarios（多 API 工作流 + 数据依赖）
8. **Skills 系统**: planner/generator/scenario/executor/healer/reporter 六大技能

### 作业
- [ ] 完成智能测试平台前后端项目部署
- [ ] RESTful 接口智能体实现

---

## 技术演进时间线

```
03-14  Agent 基础 + LangGraph API + Docling MCP
  ↓
03-21  PDF 解析中间件 + 多模态（豆包 Vision）
  ↓
03-25  DeepAgents + Skills 体系
  ↓
03-28  5 大 Skills + Excel 导出 + 多文件支持
  ↓
04-01  RAG 概念 + RAGAnything + Ollama 嵌入
  ↓
04-08  LightRAG 部署 + 知识库系统
  ↓
04-11  RAG 开关 + 智能体集成
  ↓
04-15  系统提示词优化 + RAGMiddleware
  ↓
04-22  Playwright-CLI + Web 自动化
  ↓
04-25  Hermes Agent + OpenWebUI
  ↓
04-29  API 自动化 + Graphify 知识图谱
  ↓
05-07  MASTEST 论文 + 测试报告可视化 + HITL
  ↓
05-13  平台化：FastAPI + Next.js + LangGraph 三层架构
```

---

## 与 smart-test-platform 的差距分析

### 已完成（课堂内容已在项目中实现）
- ✅ LangGraph API + DeepAgents Agent 框架
- ✅ 3 层洋葱中间件（Skills → DynamicModel → FileContext）
- ✅ 7 大 TestCase Skills
- ✅ PDF/图片/Excel 解析中间件
- ✅ 动态模型切换（DeepSeek ↔ GPT-4o）
- ✅ Excel 多格式导出工具
- ✅ LightRAG + wiki-mcp 集成
- ✅ Web 自动化 Agent + Playwright CLI Skills
- ✅ 多 Agent 架构（testcase/web/api）
- ✅ 前端对话界面 + 文件上传 + Agent 切换

### 缺失（课堂有但项目未实现）
- ❌ **FastAPI 后端 CRUD**: 项目管理、用例存储、文件夹、测试执行
- ❌ **数据库持久化**: PostgreSQL Models + MongoDB 灵活存储
- ❌ **MinIO 文件存储**: 测试报告、附件管理
- ❌ **前端管理界面**: 项目列表、用例编辑器、文件夹导航、测试执行面板
- ❌ **API 端点管理**: OpenAPI 解析 → APIEndpoints 表 → 场景测试
- ❌ **测试场景编排**: 多 API 工作流 + 数据依赖映射
- ❌ **测试报告可视化**: 图形化展示（antvis Skills）
- ❌ **Human-in-the-Loop**: 人工反馈机制
- ❌ **Hermes Agent 集成**: 浏览器自动化代理
- ❌ **BDD 支持**: Gherkin 格式用例

### 需要升级的方向
1. **加入 FastAPI 后端**: 实现项目管理、用例 CRUD、测试执行的 REST API
2. **数据库 Schema**: 按课堂模型设计（Projects → Folders → TestCases → TestRuns）
3. **前端管理页面**: 项目列表、用例编辑、文件夹树、执行仪表盘
4. **Agent 结果持久化**: Agent 生成的用例自动保存到数据库
5. **测试报告可视化**: antvis 图表 + Skills 生成
6. **Human-in-the-Loop**: 关键节点暂停等待确认
