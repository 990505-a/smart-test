# Phase 2: TestCase Agent MVP - Context

**Gathered:** 2026-05-11
**Status:** Ready for planning

<domain>
## Phase Boundary

实现测试用例生成智能体的核心业务逻辑：
- 5 阶段强制工作流（需求分析 → 测试策略 → 用例设计 → 质量评审 → 输出格式化）
- 5 个 Skill 对应 5 个阶段，通过 SKILL.md 定义
- 洋葱中间件（SkillsMiddleware + PDFContextMiddleware）
- PDF 文档解析（PyMuPDF4LLM 转 Markdown）+ MD5 缓存
- Excel 专业格式导出（openpyxl）+ TC-[PROJECT]-[MODULE]-[NNN] 编号规范
- 会话隔离（thread_id 级别）

本阶段不实现 RAG（Phase 3）、双模型切换（Phase 4）、多格式导出（Phase 4）。
</domain>

<decisions>
## Implementation Decisions

### 工作流与技能设计
- **D-01:** 采用 5 阶段工作流（需求分析 → 测试策略 → 用例设计 → 质量评审 → 输出格式化），与 ROADMAP 一致，与课堂代码模式匹配
- **D-02:** 5 个 Skill 与 5 阶段一一对应：requirement-analysis、test-strategy、test-case-design、quality-review、output-formatter
- **D-03:** 严格顺序执行 — 5 个 Skill 按顺序强制执行，每个阶段必须完成后才进入下一阶段，通过 system prompt 约束
- **D-04:** MFQ&PPDCS 方法论的精华（PPDCS 五维分析、KUFI 分类、覆盖度评估）融入各 Skill 的 Prompt 设计中，但不改变 5 阶段工作流结构

### 中间件与 PDF 解析
- **D-05:** 洋葱中间件采用 2 层结构：SkillsMiddleware（外层，加载 SKILL.md）→ PDFContextMiddleware（内层，解析 PDF 注入系统提示）
- **D-06:** 会话隔离逻辑内置在 PDFContextMiddleware 内部，通过 thread_id 字典管理，不单独成层
- **D-07:** PDF 解析使用 PyMuPDF4LLM(mode="page", extract_images=True)，将 PDF 转为 Markdown 文本注入 Agent 系统提示
- **D-08:** MD5 哈希缓存机制避免重复解析同一文档

### 用例输出格式与导出
- **D-09:** LLM 生成 Markdown 格式用例 → 后端解析 Markdown 提取字段 → openpyxl 写入 Excel → 用户通过聊天界面下载文件
- **D-10:** 完整编号规范 TC-[PROJECT]-[MODULE]-[NNN]，用户在对话中提供项目名和模块名，Agent 自动生成编号
- **D-11:** Excel 专业格式：表头样式、边框、对齐、自动换行

### Skills 加载机制
- **D-12:** SKILL.md 文件统一放在 src/app/skills/ 目录，所有 Agent 共享
- **D-13:** SkillsMiddleware 从文件系统加载 SKILL.md 技能定义，注入到 Agent 系统提示中
- **D-14:** 5 阶段强制工作流实现（SKILL-07）通过 system prompt 约束，要求 Agent 严格按顺序执行

### Claude's Discretion
- SKILL.md 的具体内容模板和 Prompt 设计
- PDFContextMiddleware 的不可变系统提示词模式实现细节
- Excel 导出的具体列名和样式参数
- Markdown 解析器的具体正则和字段提取逻辑

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 项目规划
- `.planning/PROJECT.md` — 项目愿景、约束、技术栈
- `.planning/REQUIREMENTS.md` — Phase 2 需求（PARS-01, PARS-05, MIDW-01~03, MIDW-06, SKILL-01~03, SKILL-06, SKILL-07, EXPT-01~02, EXPT-04）
- `.planning/ROADMAP.md` — Phase 2 详细描述和成功标准
- `.planning/phases/01-core-infrastructure-frontend-shell/01-01-SUMMARY.md` — Phase 1 后端交付物

### MFQ&PPDCS 方法论参考
- `c:\Users\yuanyb\Downloads\测试用例生成模块_MFQ_PPDCS_重构与产物输出方案_v1.0.md` — MFQ&PPDCS 完整方法论（PPDCS 五维模型、KUFI 四象限、六步分析法、质量红线）。Skill Prompt 设计时参考此文档的理论框架和输出格式规范。

### 课堂参考代码
- `../2026-05-07-ai-test-agent-system/` — DeepAgents Agent 创建 + 三域架构最新参考
- `../2026-03-25-testing-agent-system/` — DeepAgents Skills 体系 + SkillsMiddleware 参考实现
- `../2026-03-21-*` — PDF 中间件 + 双模型参考

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Phase 1 TestCase agent stub（src/app/agents/testcase/agent.py）— 需要添加 middleware、tools、system_prompt
- config.py 的 Settings 类 — 已有 workspace_dir、deepseek_api_key 等字段
- llms.py 的 get_deepseek_model() — 已有 LLM 初始化
- 前端 useChat.ts — 已支持 additional_kwargs.attachments（PDF base64 上传）
- 前端 useFileUpload.ts — 已支持 PDF 拖拽上传
- graph.json — 已注册 testcase_agent

### Established Patterns
- create_deep_agent(model, tools, backend, middleware, system_prompt) — Agent 创建模式
- FilesystemBackend(root_dir=workspace_dir, virtual_mode=True) — 文件后端
- SKILL.md 文件定义技能 — 需要新建 src/app/skills/ 目录
- 洋葱中间件链式调用 — DeepAgents middleware 参数接受列表

### Integration Points
- agent.py 的 middleware=[] → 需要填充 [SkillsMiddleware, PDFContextMiddleware]
- agent.py 的 tools=[] → 可能需要添加 Excel 导出工具
- agent.py 的 system_prompt → 需要替换为测试用例生成的详细系统提示
- 前端 ChatInterface → 可能需要添加文件下载按钮或链接

</code_context>

<specifics>
## Specific Ideas

- MFQ&PPDCS 方法论中的 PPDCS 五维分析（Process/Product/Data/Configuration/Structure）应融入 requirement-analysis Skill 的 Prompt
- KUFI 四象限分类（Know/Understand/Familiar/Infer）应融入 test-strategy Skill 的设计技术选择矩阵
- 覆盖度评估（功能覆盖率 + 风险覆盖率）应融入 quality-review Skill
- 参考课堂代码中 SkillsMiddleware 的实现模式（文件系统加载 SKILL.md）

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope
</deferred>

---
*Phase: 02-testcase-agent-mvp*
*Context gathered: 2026-05-11*
