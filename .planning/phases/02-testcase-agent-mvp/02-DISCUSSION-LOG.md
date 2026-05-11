# Phase 2: TestCase Agent MVP - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-11
**Phase:** 02-TestCase Agent MVP
**Areas discussed:** 工作流与技能设计, 中间件与PDF解析, 用例输出格式与导出, Skills加载机制

---

## 工作流与技能设计

### 工作流结构

| Option | Description | Selected |
|--------|-------------|----------|
| 直接实现 5 阶段 | 需求分析→策略→用例设计→数据构造→质量自检，MFQ&PPDCS 融入各 Skill Prompt | ✓ |
| 先融合 MFQ&PPDCS 6 步法 | 需求理解→PPDCS提取→KUFI分类→用例设计→覆盖评估→优化输出 | |
| 5阶段 + PPDCS/KUFI 融入各 Skill | 保持5阶段，PPDCS融入需求分析，KUFI融入策略，覆盖评估融入质量自检 | |

**User's choice:** 直接实现 5 阶段（推荐）
**Notes:** 与课堂代码和 ROADMAP 一致，MFQ&PPDCS 理论精华融入各 Skill 但不改变工作流结构

### Skill 数量

| Option | Description | Selected |
|--------|-------------|----------|
| 3 个核心 Skill（精简） | requirement-analysis、test-strategy、test-case-design | |
| 4 个 Skill（含格式化） | +output-formatter | |
| 5 个 Skill（一一对应） | requirement-analysis、test-strategy、test-case-design、quality-review、output-formatter | ✓ |

**User's choice:** 5 个 Skill（一一对应）

---

## 中间件与 PDF 解析

### 中间件分层

| Option | Description | Selected |
|--------|-------------|----------|
| 2 层：Skills + PDF | SkillsMiddleware → PDFContextMiddleware | ✓ |
| 3 层：Skills + PDF + Session | 额外增加会话隔离层 | |
| 2 层 + 会话内嵌 | Skills + PDF，会话隔离逻辑内置在 PDF 中间件 | |

**User's choice:** 2 层：Skills + PDF（推荐）
**Notes:** 简单清晰，会话隔离通过 thread_id 字典在 PDFContextMiddleware 内部管理

### PDF 解析方案

| Option | Description | Selected |
|--------|-------------|----------|
| PyMuPDF4LLM 转 Markdown | mode="page", extract_images=True，与 LLM 兼容性最佳 | ✓ |
| PyMuPDF 纯文本 | 简单但丢失格式和表格结构 | |
| MCP Docling 服务 | 质量最高但依赖外部服务 | |

**User's choice:** PyMuPDF4LLM 转 Markdown（推荐）

---

## 用例输出格式与导出

### 输出与导出方式

| Option | Description | Selected |
|--------|-------------|----------|
| 后端解析 + Excel 下载 | LLM→Markdown→后端解析→openpyxl Excel→下载链接 | ✓ |
| 纯 Markdown 展示 | 不生成 Excel，仅前端渲染 | |
| JSON + Excel 双输出 | LLM 生成 JSON，后端写 Excel + JSON API | |

**User's choice:** 后端解析 + Excel 下载（推荐）

### 编号规范

| Option | Description | Selected |
|--------|-------------|----------|
| 完整编号规范 | TC-[PROJECT]-[MODULE]-[NNN]，如 TC-STP-LOGIN-001 | ✓ |
| 简单递增编号 | TC-[NNN] | |
| 用户自定义编号 | 跟随用户输入模式 | |

**User's choice:** 完整编号规范（推荐）

---

## Skills 加载机制

### Skill 目录结构

| Option | Description | Selected |
|--------|-------------|----------|
| 统一目录 src/app/skills/ | 所有 Agent 共享，按功能命名 | ✓ |
| Agent 级目录 | 每个 Agent 有自己的 skills/ 子目录 | |
| 分层覆盖 | 共享目录 + Agent 级目录覆盖 | |

**User's choice:** 统一目录 src/app/skills/（推荐）

### 执行顺序控制

| Option | Description | Selected |
|--------|-------------|----------|
| 严格顺序执行 | 5 阶段按顺序强制执行，system prompt 约束 | ✓ |
| LLM 自主决定 | SkillsMiddleware 加载所有 Skill，LLM 自行决定顺序 | |
| 工具调用模式 | 每个 Skill 为一个工具，LLM 按需调用 | |

**User's choice:** 严格顺序执行（推荐）

---

## Claude's Discretion

- SKILL.md 的具体内容模板和 Prompt 设计
- PDFContextMiddleware 的不可变系统提示词模式实现细节
- Excel 导出的具体列名和样式参数
- Markdown 解析器的具体正则和字段提取逻辑

## Deferred Ideas

None — discussion stayed within phase scope
