# Phase 4: Advanced TestCase - Context

**Gathered:** 2026-05-13
**Status:** Ready for planning

<domain>
## Phase Boundary

增强 TestCase Agent 的高级能力：
- 双模型动态切换中间件（DeepSeek 文本 + 豆包 Vision 多模态）
- 统一文件处理（PDF + 图片 + Excel），重构 PDFContextMiddleware 为 FileContextMiddleware
- 测试数据生成 Skill（test-data-generator），生成有效/边界/无效/安全攻击四类具体数据
- 多格式导出（CSV for 禅道/TestRail、JSON for Jira Xray、Markdown）
- 前端多模态开关（ConfigDialog 中的 ENABLE_PDF_MULTIMODAL Switch）

本阶段不实现 Web/API 自动化 Agent（Phase 5/6）、不实现多工作空间隔离（Phase 7）。

**重要发现：** quality-review (SKILL-05) 的四维评分（完整性30%+准确性25%+有效性25%+可执行性20%）已在 Phase 2 完整实现，Phase 4 无需重复。
</domain>

<decisions>
## Implementation Decisions

### Dynamic Model Switching (MIDW-04, PARS-06, UI-07)
- **D-01:** DynamicModelSelection 中间件通过替换 request.model 实现模型切换 — 检测到图片时创建 Doubao Vision 模型实例替换，纯文本时透传 DeepSeek
- **D-02:** 检测机制 — 扫描 HumanMessage 中的 image_url 类型 content 块和 additional_kwargs.attachments 中的 image/* MIME 类型，覆盖 PDF 中图片和直接上传的图片
- **D-03:** 多模态开关放在 ConfigDialog 配置对话框中 — 添加 Switch 组件控制 ENABLE_PDF_MULTIMODAL 参数，与现有 API Key 配置放在一起
- **D-04:** DynamicModelSelection 在洋葱中的位置 — SkillsMiddleware(外) → DynamicModelSelection(中) → FileContextMiddleware(内) → LLM

### File Processing Expansion (PARS-02, PARS-03)
- **D-05:** 将 PDFContextMiddleware 重构为统一的 FileContextMiddleware — 内部根据文件 MIME 类型分派给不同处理器（PDF → PyMuPDF4LLM、Image → 豆包 Vision、Excel → openpyxl）
- **D-06:** 图片使用豆包 Vision 多模态模型直接解析图片内容，返回文字描述注入 system_message
- **D-07:** Excel 使用 openpyxl 读取，将每个 sheet 转为 Markdown 表格注入 system_message
- **D-08:** 三种文件类型统一注入 system_message，保留 thread_id 会话隔离机制和 MD5 去重缓存

### Test Data Generation (SKILL-04)
- **D-09:** 创建独立的 test-data-generator Skill 目录和 SKILL.md — 成为第 7 个 Skill（与现有 5 + wiki-query 并列）
- **D-10:** 生成具体数据值（如 "admin' OR 1=1 --"、"user@example.com"），不仅仅是数据类别或规则描述
- **D-11:** 四类测试数据：有效数据（正常业务值）、边界数据（min/max/边界值）、无效数据（格式错误/类型不匹配）、安全攻击数据（SQL注入/XSS/越权）

### Multi-format Export (EXPT-03)
- **D-12:** 统一导出函数 export_test_cases（format 参数: excel/csv/json/markdown）— 替代现有独立的 export_test_cases_to_excel，内部按格式分派
- **D-13:** CSV 格式 — UTF-8 with BOM 编码，逗号分隔，双引号转义，10 列标准字段，兼容禅道/TestRail 导入
- **D-14:** JSON 格式 — Jira Xray 兼容格式（{"testCases": [{"testCaseKey": ..., "summary": ..., "steps": [...]}]}）

### Already Delivered (No Phase 4 Work Needed)
- **D-15:** quality-review (SKILL-05) 四维评分已在 Phase 2 完整实现（Completeness 30% + Accuracy 25% + Validity 25% + Executability 20%），含覆盖度评估、回退机制、基线对比。Phase 4 仅需标记为完成。

### Claude's Discretion
- DynamicModelSelection 中间件的具体实现（如何创建 Doubao 模型实例、如何检测 image_url content 块）
- FileContextMiddleware 重构的内部处理器分派逻辑
- test-data-generator SKILL.md 的具体 Prompt 内容和四类数据的生成指导
- CSV/JSON/Markdown 导出的具体字段映射和格式细节
- ConfigDialog 中 Switch 开关的 UI 细节

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 项目规划
- `.planning/PROJECT.md` — 项目愿景、约束、技术栈
- `.planning/REQUIREMENTS.md` — Phase 4 需求（PARS-02, PARS-03, PARS-06, MIDW-04, SKILL-04, SKILL-05, EXPT-03, UI-07）
- `.planning/ROADMAP.md` — Phase 4 详细描述和成功标准
- `.planning/phases/02-testcase-agent-mvp/02-CONTEXT.md` — Phase 2 交付物和决策（洋葱中间件、PDF 处理器、Excel 导出）
- `.planning/phases/02-testcase-agent-mvp/02-VERIFICATION.md` — Phase 2 验证结果
- `.planning/phases/03-rag-knowledge-system/03-CONTEXT.md` — Phase 3 决策（wiki-mcp 集成，无中间件变更）

### MFQ&PPDCS 方法论参考
- `c:\Users\yuanyb\Downloads\测试用例生成模块_MFQ_PPDCS_重构与产物输出方案_v1.0.md` — MFQ&PPDCS 完整方法论，test-data-generator Skill 设计参考

### 课堂参考代码
- `../2026-03-21-*` — PDF 中间件 + 双模型参考
- `../2026-03-25-testing-agent-system/` — DeepAgents Skills 体系参考
- `../2026-05-07-ai-test-agent-system/` — DeepAgents Agent 创建 + MCP 集成最新参考

### 已有代码（Phase 4 修改目标）
- `src/app/agents/testcase/agent.py` — Agent 创建代码，需添加 DynamicModelSelection 中间件、更新 tools 和 middleware 链
- `src/app/agents/testcase/tools.py` — Excel 导出工具，需重构为统一导出函数
- `src/app/middleware/pdf_context.py` — PDFContextMiddleware，需重构为 FileContextMiddleware
- `src/app/processors/pdf.py` — PDF 处理器，需新增 image_processor 和 excel_processor
- `src/app/core/config.py` — Settings 类，需添加豆包模型配置和 ENABLE_PDF_MULTIMODAL
- `src/app/skills/` — 现有 6 个 Skill 目录，需添加 test-data-generator/
- `webui/src/app/components/ConfigDialog.tsx` — 配置对话框，需添加多模态开关
- `webui/src/app/hooks/useChat.ts` — 聊天 hook，可能需传递 ENABLE_PDF_MULTIMODAL 参数

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/app/middleware/pdf_context.py` — PDFContextMiddleware 的会话隔离（thread_id dict）、MD5 去重、immutable system prompt pattern 全部保留，仅扩展文件类型支持
- `src/app/processors/pdf.py` — PDFProcessor 的缓存模式可直接扩展为多处理器架构
- `src/app/agents/testcase/tools.py` — export_test_cases_to_excel 的字段提取（_extract_field, _flatten_steps 等）可复用于 CSV/JSON/Markdown 导出
- `src/app/skills/output-formatter/SKILL.md` — 已有 TC-[PROJECT]-[MODULE]-[NNN] 编号规范，多格式导出可复用
- `src/app/core/config.py` — 已有 doubao_api_key 字段，需添加模型名等配置
- `webui/src/app/components/ConfigDialog.tsx` — 已有配置对话框框架，添加 Switch 即可

### Established Patterns
- 洋葱中间件链 — DynamicModelSelection 插入 Skills 和 FileContext 之间，3 层洋葱
- SKILL.md 文件格式 — YAML frontmatter (name + description) + Markdown 正文
- @tool 注册 — export_test_cases 统一函数替代原有独立 Excel 导出
- 会话隔离 — FileContextMiddleware 继承 PDFContextMiddleware 的 thread_id dict 模式
- 配置管理 — config.py BaseSettings + .env 环境变量

### Integration Points
- agent.py middleware 链 — 从 [skills_middleware, pdf_middleware] 变为 [skills_middleware, dynamic_model_middleware, file_middleware]
- agent.py tools — 从 [export_test_cases_to_excel] 变为 [export_test_cases]
- processors/ 目录 — 新增 image_processor.py 和 excel_processor.py
- skills/ 目录 — 新增 test-data-generator/SKILL.md
- webui ConfigDialog.tsx — 添加 ENABLE_PDF_MULTIMODAL Switch
- webui useChat.ts — 可能需要传递 enable_multimodal 参数到后端

</code_context>

<specifics>
## Specific Ideas

- DynamicModelSelection 中间件可参考 PDFContextMiddleware 注释中的预留位置设计
- test-data-generator Skill 应指导 Agent 在 test-case-design 阶段自动调用，作为用例设计的增强而非独立阶段
- 统一导出函数可保留原有 Excel 专业格式化逻辑，仅增加 CSV/JSON/Markdown 分支
- ConfigDialog 中 Switch 开关状态可通过 additional_kwargs.enable_multimodal 传递到后端中间件
- 豆包 Vision 模型初始化使用 langchain init_chat_model("doubao:doubao-vision") 或类似模式

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---
*Phase: 04-advanced-testcase*
*Context gathered: 2026-05-13*
