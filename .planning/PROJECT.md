# 智能测试平台 (Smart Test Platform)

## What This Is

基于 Agent + RAG + MCP + Skills + Tools 技术栈的企业级智能测试平台，覆盖测试用例自动生成、Web UI 自动化测试、RESTful API 自动化测试三大领域。平台通过 DeepAgents 框架整合多种专业技能（Skills），借助 RAG 知识库提供上下文增强，通过 MCP 协议标准化工具集成，为测试工程师提供从需求分析到测试报告的全流程 AI 辅助能力。

## Core Value

通过 AI 智能体 + 企业级 Skills 技能体系，自动生成高质量、可执行、可追溯的测试资产（用例/脚本/报告），大幅提升测试效率和覆盖率。

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

(None yet — ship to validate)

### Active

<!-- Current scope. Building toward these. -->

**测试用例生成智能体：**
- [ ] 基于文档链接的测试用例生成（MCP Docling 文档解析）
- [ ] PDF/图片/Excel 多文件上传解析（base64 → PyMuPDF4LLM → 多模态解析）
- [ ] 双模型动态切换（DeepSeek 文本 + 豆包 Vision 多模态）
- [ ] 6 个专业技能：需求分析、测试策略、用例设计、测试数据生成、质量评审、输出格式化
- [ ] 5 阶段强制工作流（需求分析 → 策略制定 → 用例设计 → 数据构造 → 质量自检）
- [ ] 洋葱中间件架构（PDF 上下文注入 + 动态模型选择 + RAG 上下文 + Skills 注入）
- [ ] RAG 知识库集成（LightRAG + RAGAnything，6 种查询模式）
- [ ] RAG MCP Server（7 个工具：问答/检索/图谱搜索/实体获取/标签/状态/健康检查）
- [ ] Excel 导出（多格式：Markdown/CSV/JSON，兼容禅道/TestRail/Jira Xray）
- [ ] 用例编号规范（TC-[PROJECT]-[MODULE]-[NNN]）
- [ ] 四维质量评估（完整性30% + 准确性25% + 有效性25% + 可执行性20%）
- [ ] 多工作空间 RAG 隔离（X-Space-Id 工作空间级别隔离，不同知识库空间）

**Web 自动化测试智能体：**
- [ ] Playwright CLI 集成（会话管理/存储状态/网络控制/多标签页/视频录制）
- [ ] Agent-Browser 模式（直接浏览器操作）
- [ ] 双模式自动检测（目标 URL → 探索性 QA；源码仓库 → 组件感知测试）
- [ ] 7-Agent 导演流水线（Script Analyst → Stage Manager → Blocking Coach → Set Designer → Choreographer → Assistant Director → Continuity Lead）
- [ ] 组件感知 Web 自动化（源码分析 → data-testid 注入 → POM 生成）
- [ ] 专业 QA 技能（探索/证据收集/性能/安全/无障碍/响应式/报告）
- [ ] 自动生成 TypeScript 测试脚本

**API 自动化测试智能体：**
- [ ] OpenAPI/Swagger 规范解析（$ref 引用解析、参数/响应/Schema 提取）
- [ ] MASTEST 学术方法论实现（arXiv:2511.18038）
- [ ] Graphify 代码知识图谱 MCP 集成（源码级接口信息获取）
- [ ] Playwright MCP Server API 测试集成
- [ ] 测试场景设计（正向/反向/边界/跨操作序列）
- [ ] Playwright TypeScript 脚本生成（含 test.step）
- [ ] 语法校验 + 覆盖率计算工具
- [ ] Human-in-the-Loop 人工反馈集成
- [ ] 测试报告图形化展示（antvis/chart-visualization-skills）

**前端聊天界面：**
- [ ] Next.js 16 + React 19 + Tailwind CSS + Shadcn/ui 聊天界面
- [ ] 流式对话（@langchain/langgraph-sdk 实时消息流）
- [ ] 文件上传（拖放 + 粘贴，支持 PDF/图片/Excel）
- [ ] RAG 开关按钮（动态控制 RAG MCP 工具调用）
- [ ] 多模态开关（ENABLE_PDF_MULTIMODAL 参数控制）
- [ ] 暗色/亮色主题切换
- [ ] 会话线程管理（状态过滤/无限滚动）
- [ ] 可调整面板布局（侧边栏展示任务和文件）
- [ ] URL 状态管理（nuqs）

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- 性能测试模块 — 课堂未完整实现，需要独立设计压测框架
- 代码级安全测试 — 需要静态分析工具集成（SonarQube/SAST），超出当前范围
- 移动端 App 自动化 — 需要 Appium/Device Farm，课堂聚焦 Web 端
- 多用户协作/权限管理 — 前端无后端用户系统，超出单用户场景
- CI/CD 集成 — Jenkins/GitHub Actions 流水线集成，属于 DevOps 范畴
- Hermes/OpenClaw 第三方 Agent 平台集成 — 部署和运维复杂，作为可选扩展

## Context

本项目整合了 2026-03-14 至 2026-05-07 共 12 周课堂学习的所有功能模块，从初始的 LangChain Agent + MCP 基础用例生成，逐步演进到 DeepAgents Skills 体系、RAG 知识库、Web/API 自动化测试的完整平台。

**核心架构模式：**
- ReAct Agent：推理 + 行动循环，LLM 自主决定工具调用
- 洋葱中间件：Skills → 模型选择 → PDF 上下文 → RAG 上下文，分层处理
- Skills 技能体系：模块化专业技能，SKILL.md 定义激活场景/执行步骤/输出模板
- 双模型策略：DeepSeek（文本低成本）+ 豆包 Vision（多模态）动态切换
- MCP 协议集成：标准化工具接口，Docling/Graphify/Playwright 外部服务
- RAG-First：强制知识检索优先，确保用例基于真实文档
- 多工作空间隔离：X-Space-Id 级别知识库空间隔离，无需用户登录认证
- Human-in-the-Loop：关键阶段人工审批，防止错误累积

**参考代码目录：**
- 2026-03-14-*: 基础 Agent + MCP + 前端
- 2026-03-21-*: PDF 中间件 + 双模型
- 2026-03-25-*: DeepAgents Skills 体系
- 2026-03-28-*: 专业级 Skills + RAG 概念
- 2026-04-08-*: RAGAnything 实现
- 2026-04-11-*: LightRAG + RAG MCP Server
- 2026-04-15-*: 多租户 RAG + JWT
- 2026-04-22-*: Web 自动化 + Playwright
- 2026-04-29-*: API 自动化 + Graphify
- 2026-05-07-*: MASTEST + 7-Agent 流水线

## Constraints

- **技术栈**: Python 3.13 后端 + Next.js 15 前端，与课堂代码保持一致
- **Agent 框架**: DeepAgents >= 0.5.5 作为主框架（LangGraph 为底层运行时）
- **LLM**: DeepSeek Chat（文本）+ 豆包 Vision（多模态），需配置 API Key
- **RAG**: LightRAG（NanoVectorDB + NetworkX + JSON 轻量存储）+ Ollama（qwen3-embedding:0.6b）
- **部署**: 轻量本地部署，仅需 Python + Ollama + Node.js 原生安装，不依赖 Docker
- **MCP 服务**: Docling（文档解析）、Graphify（代码图谱）、Playwright（自动化）
- **端口约定**: DeepAgents 服务 2026, 前端 3000, LightRAG Server 9621

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 使用 DeepAgents 为主框架 | 课堂后期主要框架，Skills/Middleware/MCP/Backend 企业级特性完善 | — Pending |
| 采用洋葱中间件架构 | Skills → 模型选择 → PDF 上下文 → RAG 上下文分层解耦，各层独立可扩展 | — Pending |
| LightRAG 二次开发而非从零构建 | 已有前端 + API + 知识图谱可视化，减少前端开发工作量 | — Pending |
| Playwright CLI 而非 MCP 模式 | CLI 模式只需 `execute` 一个工具，减少 token 消耗，大模型调用效率更高 | — Pending |
| 三域 Agent 架构（用例/Web/API） | 职责清晰，各域独立 Skills/Tools/Middleware，避免单智能体过于复杂 | — Pending |
| 本地部署 + 多工作空间 | 无需用户登录认证，通过 X-Space-Id 隔离不同知识库空间 | — Pending |

---

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-11 after initialization*
