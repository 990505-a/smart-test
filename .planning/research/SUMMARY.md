# Project Research Summary

**Project:** Smart Test Platform (智能测试平台)
**Domain:** AI-Powered Intelligent Testing Platform (Agent + RAG + MCP + Skills)
**Researched:** 2026-05-11
**Confidence:** HIGH

## Executive Summary

多域AI测试平台，采用三域 Agent 架构（TestCase / Web / API），共享核心基础设施但独立运行。推荐技术栈：Python 3.13 + DeepAgents/LangGraph 后端、Next.js 15.4.4 + React 19 前端、LightRAG 知识库，Docker Compose 容器化部署。

**核心架构支柱：** Skills 架构（SKILL.md 文件）和洋葱中间件管道必须从第一天正确实现。多租户 RAG 隔离是最高风险架构关注点。

**推荐构建顺序：** 共享 LangGraph 服务器 + 前端 → TestCase Agent（核心价值）→ RAG 知识系统（最大差异化）→ Web/API 自动化 Agent（扩展域）→ 多租户加固。

## Key Findings

### Recommended Stack

- **DeepAgents >= 0.5.5**: Agent 框架，Skills/Middleware/MCP/Backend 开箱即用
- **LangGraph >= 0.4.x**: Agent 编排，状态机 + 中断处理
- **Next.js 15.4.4**: 前端（注意：PROJECT.md 中的 "Next.js 16" 不存在，最新稳定版为 15.4.4）
- **LightRAG + PostgreSQL**: RAG 引擎，向量 + 图谱 + KV 一体化存储
- **Playwright CLI**: 浏览器自动化（优于 MCP 模式的 token 效率）
- **Tailwind CSS 4 + Shadcn/ui**: UI 层

### Table Stakes (必须具备)

1. 文档解析（PDF/Word/Excel/Image）— PyMuPDF4LLM + Docling MCP
2. 测试用例生成 — 5 阶段强制工作流
3. 多格式导出（Excel/CSV/JSON/Markdown）— 测试团队必需
4. 聊天式对话界面 + 流式响应 — SSE via langgraph-sdk
5. 文件上传（拖放 + 粘贴）— PDF/图片/Excel/URL
6. OpenAPI/Swagger 规范导入 + $ref 解析
7. Playwright 脚本生成 — 可执行 TypeScript .spec.ts 文件
8. 覆盖率指标 — 数据类型 + 状态码覆盖率

### Differentiators (竞争优势)

1. RAG 知识库（6 种查询模式）— 最大护城河
2. Skills 架构（SKILL.md）— 模块化、可版本化的专业能力
3. 7-Agent 导演流水线 — 组件感知 Web 测试
4. MASTEST 学术方法论 — arXiv:2511.18038 验证
5. 双模型动态切换 — DeepSeek/Doubao 自动选择
6. 洋葱中间件管道 — Skills/Model/PDF/RAG 分层解耦
7. Human-in-the-Loop — LangGraph 中断机制

### Critical Pitfalls

1. **LLM 幻觉** — 强制 RAG-first + 来源归属 + 拒绝无上下文生成
2. **MCP 集成脆弱性** — 每工具超时 + 熔断器 + 健康检查
3. **多租户 RAG 数据泄露** — 从第一天设计 workspace_id 过滤
4. **长管道上下文耗尽** — 渐进式摘要 + 暂存模式
5. **中间件链顺序错误** — 配置强制顺序 + 上下文快照日志

## Recommended Phase Structure

| # | Phase | Rationale |
|---|-------|-----------|
| 1 | Core Infrastructure | 所有 Agent 依赖的 LangGraph 服务器 + 前端壳 |
| 2 | TestCase Agent MVP | 核心产品价值，上传文档→生成用例→导出 Excel |
| 3 | RAG Knowledge System | 最大竞争优势，LightRAG + MCP Server + 7 工具 |
| 4 | Advanced TestCase | 完整 6 技能 + 双模型 + 四维质量评估 + RAG 集成 |
| 5 | Web Automation Agent | Playwright CLI 双模式 + 专业 QA 技能 |
| 6 | API Automation Agent | MASTEST + OpenAPI 解析 + Human-in-the-Loop |
| 7 | Multi-Tenant Hardening | JWT 认证 + 工作空间隔离 + 生产就绪 |

## Confidence Assessment

| Area | Level | Notes |
|------|-------|-------|
| Stack | HIGH | 所有技术已验证（DeepAgents 0.5.5, Next.js 15.4.4） |
| Features | HIGH | 基于竞争对手分析 + 12 周参考代码 |
| Architecture | HIGH | 直接从工作代码库提取，非理论推导 |
| Pitfalls | HIGH | MASTEST 论文验证 + MCP 官方规范 |
| 7-Agent Pipeline | LOW | 新颖架构，无生产验证 |

---
*Research completed: 2026-05-11*
*Ready for roadmap: yes*
