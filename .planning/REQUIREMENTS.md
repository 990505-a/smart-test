# Requirements: 智能测试平台 (Smart Test Platform)

**Defined:** 2026-05-11
**Core Value:** 通过 AI 智能体 + 企业级 Skills 技能体系，自动生成高质量、可执行、可追溯的测试资产

## v1 Requirements

### 核心基础设施 (Infrastructure)

- [x] **INFRA-01**: 部署 LangGraph API 服务器（端口 2026），支持多 Agent 路由（graph.json 配置）
- [x] **INFRA-02**: 配置 DeepAgents 框架（>= 0.5.5），集成 FilesystemBackend + CompositeBackend
- [x] **INFRA-03**: 配置 LightRAG 轻量存储（NanoVectorDB 向量 + NetworkX 图 + JSON KV），不依赖外部数据库
- [x] **INFRA-04**: 部署 LightRAG Server（轻量模式），支持 6 种查询模式
- [ ] **INFRA-05**: 原生安装 Ollama（Windows exe），配置嵌入模型（qwen3-embedding:0.6b，1024 维度）
- [x] **INFRA-06**: 集成 MCP 协议（SSE/stdio 传输），配置 Docling/Graphify/Playwright MCP 服务
- [ ] **INFRA-07**: 实现 X-Space-Id 多工作空间隔离（不同知识库空间，无需用户登录认证）
- [ ] **INFRA-08**: 配置连接池（httpx.AsyncClient）、指数退避重试、熔断器模式

### 文档解析与多模态 (Parsing)

- [x] **PARS-01**: 实现 PDF 解析器（PyMuPDF4LLM，mode="page"，extract_images=True）
- [ ] **PARS-02**: 实现图片解析（豆包 Vision 多模态模型，LLMImageBlobParser）
- [ ] **PARS-03**: 实现 Excel 文件解析（openpyxl）
- [x] **PARS-04**: 实现 base64 → 文件转换管道（前端上传 → 后端解析）
- [x] **PARS-05**: MD5 哈希缓存机制避免重复解析
- [ ] **PARS-06**: 双模型动态切换中间件（检测图片 → 切换 Doubao Vision，纯文本 → DeepSeek）

### PDF 中间件 (Middleware)

- [x] **MIDW-01**: 实现 PDFContextMiddleware（从 HumanMessage attachments 提取 base64 PDF → 解析 → 注入 SystemMessage）
- [x] **MIDW-02**: 实现会话隔离（thread_id 级别独立的文档状态管理）
- [x] **MIDW-03**: 实现不可变系统提示词模式（构造函数注入，请求覆写模式）
- [ ] **MIDW-04**: 实现 DynamicModelSelection 中间件（洋葱模型第二层）
- [ ] **MIDW-05**: 实现 RAGMiddleware（动态注入/移除 RAG 工具 + 系统提示词修改）— Superseded by D-10/D-16: wiki-mcp tools loaded at agent creation time via MCP client, no middleware needed
- [x] **MIDW-06**: 实现 SkillsMiddleware（文件系统加载 SKILL.md 技能定义）

### Skills 技能体系 (Skills)

- [x] **SKILL-01**: 需求分析技能（requirement-analysis）— INVEST 原则、功能矩阵、风险识别
- [x] **SKILL-02**: 测试策略技能（test-strategy）— 测试类型选择矩阵、优先级策略、回归计划
- [x] **SKILL-03**: 用例设计技能（test-case-design）— 六大测试设计技法（等价类/边界值/判定表/状态迁移/场景法/错误推测）
- [x] **SKILL-04**: 测试数据生成技能（test-data-generator）— 有效/边界/无效/安全攻击数据
- [ ] **SKILL-05**: 质量评审技能（quality-review）— 四维评估（完整性30%+准确性25%+有效性25%+可执行性20%）
- [x] **SKILL-06**: 输出格式化技能（output-formatter）— Markdown/CSV/JSON 多格式输出
- [x] **SKILL-07**: 5 阶段强制工作流实现（需求分析 → 策略制定 → 用例设计 → 数据构造 → 质量自检）
- [x] **SKILL-08**: RAG 知识查询技能（rag-query）— 混合检索策略 + 严格引用要求

### RAG 知识库系统 (RAG)

- [ ] **RAGS-01**: RAG MCP Server（7 个工具）— Superseded by D-11: wiki-mcp provides 6 tools via stdio MCP
- [ ] **RAGS-02**: 多工作空间隔离（workspace_id 过滤，NanoVectorDB + NetworkX 目录级隔离）
- [ ] **RAGS-03**: RAG-first 强制策略（无检索不设计，拒绝无上下文生成）— Superseded by D-12: Agent queries wiki on demand
- [ ] **RAGS-04**: 6 种查询模式支持（local/global/hybrid/naive/mix/bypass）— Superseded by D-13: wiki-mcp has its own query capabilities
- [ ] **RAGS-05**: 文档状态监控（处理进度跟踪，异步处理管道）— Superseded by D-14: wiki-mcp reads pre-built files

### Excel 导出与格式化 (Export)

- [x] **EXPT-01**: Excel 导出工具（openpyxl，专业样式：表头/边框/对齐/自动换行）
- [x] **EXPT-02**: 用例编号规范（TC-[PROJECT]-[MODULE]-[NNN]）
- [x] **EXPT-03**: 多格式兼容导出（CSV for 禅道/TestRail、JSON for Jira Xray、Markdown）
- [x] **EXPT-04**: 字段映射与数据提取（支持多种嵌套格式）

### Web 自动化测试 (Web)

- [ ] **WEB-01**: Web Agent 双模式自动检测（目标 URL → 探索性 QA；源码仓库 → 组件感知测试）
- [ ] **WEB-02**: Playwright CLI 集成（会话管理、存储状态、网络控制、多标签页、视频录制）
- [ ] **WEB-03**: 探索性 QA 技能（playwright-cli）— 6 阶段专业 QA 流程
- [ ] **WEB-04**: Agent-Browser 模式（agent-browser 技能）
- [ ] **WEB-05**: 专业 QA 技能（pw-dogfood）— 系统探索/证据收集/性能/安全/无障碍/响应式
- [ ] **WEB-06**: 7-Agent 导演流水线（Script Analyst → Stage Manager → Blocking Coach → Set Designer → Choreographer → Assistant Director → Continuity Lead）
- [ ] **WEB-07**: 组件感知测试技能（component-aware-web-automation）— 源码分析 → data-testid 注入 → POM 生成
- [ ] **WEB-08**: 自动生成 TypeScript 测试脚本（含 trace/screenshots 证据）

### API 自动化测试 (API)

- [ ] **API-01**: OpenAPI/Swagger 规范解析器（$ref 引用解析、参数/响应/Schema 提取）
- [ ] **API-02**: MASTEST 学术方法论实现（arXiv:2511.18038）
- [ ] **API-03**: 测试场景设计（正向/反向/边界/跨操作序列）
- [ ] **API-04**: Playwright TypeScript 脚本生成（含 test.step、soft assertions）
- [ ] **API-05**: 语法校验工具（check_script_syntax）
- [ ] **API-06**: 覆盖率计算工具（compute_coverage，数据类型 + 状态码覆盖率）
- [ ] **API-07**: Graphify 代码知识图谱 MCP 集成（源码级接口信息获取）
- [ ] **API-08**: Human-in-the-Loop 集成（LangGraph interrupts，关键阶段人工审批）
- [ ] **API-09**: 测试报告图形化展示（antvis/chart-visualization-skills）

### 前端聊天界面 (Frontend)

- [x] **UI-01**: Next.js 15.4.4 + React 19 + Tailwind CSS 4 + Shadcn/ui 项目搭建
- [x] **UI-02**: 流式对话界面（@langchain/langgraph-sdk，SSE 实时消息渲染）
- [x] **UI-03**: 文件上传（拖放 + 粘贴，支持 PDF/JPEG/PNG/GIF/WebP）
- [x] **UI-04**: 图片 → base64 → image_url 块（OpenAI 兼容格式）
- [x] **UI-05**: PDF → base64 → additional_kwargs.attachments
- [ ] **UI-06**: RAG 开关按钮（enableRag 状态）— Superseded by D-15: Wiki tools always available, no toggle needed
- [ ] **UI-07**: 多模态开关（ENABLE_PDF_MULTIMODAL 参数控制）
- [x] **UI-08**: 会话线程管理（状态过滤、无限滚动、时间分组）
- [x] **UI-09**: 可调整面板布局（react-resizable-panels，侧边栏任务/文件）
- [x] **UI-10**: 多 Agent 路由切换（TestCase/Web/API Agent 选择）
- [x] **UI-11**: 暗色/亮色主题切换
- [x] **UI-12**: URL 状态管理（nuqs）
- [ ] **UI-13**: 中断处理（Interrupt），支持工具调用审批
- [ ] **UI-14**: 子智能体可视化展示

## v2 Requirements

### 性能与安全

- **PERF-01**: 性能测试模块集成（JMeter/k6 压测）
- **PERF-02**: 代码级安全测试（SAST 静态分析）
- **PERF-03**: 视觉回归测试（Applitools/像素对比）

### 集成与扩展

- **INTG-01**: CI/CD 流水线集成（GitHub Actions/Jenkins）
- **INTG-02**: 移动端 App 自动化（Appium/Device Farm）
- **INTG-03**: Hermes/OpenClaw 第三方 Agent 平台对接
- **INTG-04**: 多用户协作/权限管理系统

## Out of Scope

| Feature | Reason |
|---------|--------|
| 性能/负载测试模块 | 需要 JMeter/k6 集成，属于独立产品范畴 |
| 代码级安全测试（SAST） | 需要 SonarQube/Checkmarx 集成，超出测试平台核心范围 |
| 移动端 App 自动化 | 需要 Appium + Device Farm，课堂聚焦 Web 端 |
| CI/CD 流水线集成 | Jenkins/GitHub Actions 编排，属于 DevOps 范畴 |
| 视觉回归测试 | Applitools 主导此领域，ROI 不高 |
| 无代码测试构建器 | 偏离 AI-Agent 驱动的核心理念 |
| 测试管理系统（TMS） | 平台生成测试资产导入现有 TMS，不替代 TMS |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 1 | Complete |
| INFRA-02 | Phase 1 | Complete |
| INFRA-03 | Phase 1 | Complete |
| INFRA-04 | Phase 1 | Complete |
| INFRA-05 | Phase 1 | Pending |
| INFRA-06 | Phase 1 | Complete |
| INFRA-07 | Phase 7 | Pending |
| INFRA-08 | Phase 7 | Pending |
| PARS-01 | Phase 2 | Complete |
| PARS-02 | Phase 4 | Pending |
| PARS-03 | Phase 4 | Pending |
| PARS-04 | Phase 1 | Complete |
| PARS-05 | Phase 2 | Complete |
| PARS-06 | Phase 4 | Pending |
| MIDW-01 | Phase 2 | Complete |
| MIDW-02 | Phase 2 | Complete |
| MIDW-03 | Phase 2 | Complete |
| MIDW-04 | Phase 4 | Pending |
| MIDW-05 | Phase 3 | Superseded (D-10/D-16) |
| MIDW-06 | Phase 2 | Complete |
| SKILL-01 | Phase 2 | Complete |
| SKILL-02 | Phase 2 | Complete |
| SKILL-03 | Phase 2 | Complete |
| SKILL-04 | Phase 4 | Complete |
| SKILL-05 | Phase 4 | Pending |
| SKILL-06 | Phase 2 | Complete |
| SKILL-07 | Phase 2 | Complete |
| SKILL-08 | Phase 3 | Complete |
| RAGS-01 | Phase 3 | Superseded (D-11) |
| RAGS-02 | Phase 7 | Pending |
| RAGS-03 | Phase 3 | Superseded (D-12) |
| RAGS-04 | Phase 3 | Superseded (D-13) |
| RAGS-05 | Phase 3 | Superseded (D-14) |
| EXPT-01 | Phase 2 | Complete |
| EXPT-02 | Phase 2 | Complete |
| EXPT-03 | Phase 4 | Complete |
| EXPT-04 | Phase 2 | Complete |
| WEB-01 | Phase 5 | Pending |
| WEB-02 | Phase 5 | Pending |
| WEB-03 | Phase 5 | Pending |
| WEB-04 | Phase 5 | Pending |
| WEB-05 | Phase 5 | Pending |
| WEB-06 | Phase 5 | Pending |
| WEB-07 | Phase 5 | Pending |
| WEB-08 | Phase 5 | Pending |
| API-01 | Phase 6 | Pending |
| API-02 | Phase 6 | Pending |
| API-03 | Phase 6 | Pending |
| API-04 | Phase 6 | Pending |
| API-05 | Phase 6 | Pending |
| API-06 | Phase 6 | Pending |
| API-07 | Phase 6 | Pending |
| API-08 | Phase 6 | Pending |
| API-09 | Phase 6 | Pending |
| UI-01 | Phase 1 | Complete |
| UI-02 | Phase 1 | Complete |
| UI-03 | Phase 1 | Complete |
| UI-04 | Phase 1 | Complete |
| UI-05 | Phase 1 | Complete |
| UI-06 | Phase 3 | Superseded (D-15) |
| UI-07 | Phase 4 | Pending |
| UI-08 | Phase 1 | Complete |
| UI-09 | Phase 1 | Complete |
| UI-10 | Phase 1 | Complete |
| UI-11 | Phase 1 | Complete |
| UI-12 | Phase 1 | Complete |
| UI-13 | Phase 6 | Pending |
| UI-14 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 59 total
- Mapped to phases: 59
- Unmapped: 0 ✓

---
*Requirements defined: 2026-05-11*
*Last updated: 2026-05-12 after Phase 3 completion*
