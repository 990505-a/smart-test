# Phase 4: Advanced TestCase - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-13
**Phase:** 04-Advanced TestCase
**Areas discussed:** Dynamic Model Switching, File Processing Expansion, Test Data Generation, Multi-format Export

---

## Dynamic Model Switching

### 模型切换方式

| Option | Description | Selected |
|--------|-------------|----------|
| 中间件替换 model | 检测图片时创建 Doubao Vision 替换 request.model | ✓ |
| 中间件修改 system_message | 注入多模态指令，依赖模型自身能力 | |
| Agent 创建时双模型 | 两个 Agent + 路由层选择 | |

**User's choice:** 中间件替换 model

### 检测机制

| Option | Description | Selected |
|--------|-------------|----------|
| 检测消息中的图片 | image_url content 块 + attachments image MIME | ✓ |
| 只检查 attachments | 范围窄但简单 | |
| 前端显式标记 | additional_kwargs.multimodal = true | |

**User's choice:** 检测消息中的图片

### 多模态开关位置

| Option | Description | Selected |
|--------|-------------|----------|
| ConfigDialog 中的开关 | Switch 控制 ENABLE_PDF_MULTIMODAL，与 API Key 配置放一起 | ✓ |
| 顶栏开关 | AgentTabs 旁全局开关 | |
| 纯后端自动检测 | 无 UI 开关，自动检测 | |

**User's choice:** ConfigDialog 中的开关

---

## File Processing Expansion

### 架构方式

| Option | Description | Selected |
|--------|-------------|----------|
| 统一 FileContextMiddleware | 根据 MIME 类型分派给不同处理器 | ✓ |
| 每个文件类型独立中间件 | 三个中间件串联 | |
| 扩展现有 PDF 中间件 | 不重命名，扩展 _extract 方法 | |

**User's choice:** 统一 FileContextMiddleware

### 图片解析方式

| Option | Description | Selected |
|--------|-------------|----------|
| 豆包 Vision 多模态解析 | 直接解析图片返回文字描述 | ✓ |
| LLMImageBlobParser 封装 | 作为 PyMuPDF4LLM 的 images_parser | |

**User's choice:** 豆包 Vision 多模态解析

### Excel 解析方式

| Option | Description | Selected |
|--------|-------------|----------|
| openpyxl → Markdown 表格 | 每个 sheet 转 Markdown 表格注入 system_message | ✓ |
| openpyxl → JSON 结构 | 精确但 token 消耗大 | |
| 自动选择格式 | 简单表格用 Markdown，复杂用 JSON | |

**User's choice:** openpyxl → Markdown 表格

---

## Test Data Generation

### 融入方式

| Option | Description | Selected |
|--------|-------------|----------|
| 独立 Skill | test-data-generator 独立目录和 SKILL.md，第 7 个 Skill | ✓ |
| 融入 test-case-design | 不创建新目录，增加现有 Skill 复杂度 | |

**User's choice:** 独立 Skill

### 生成粒度

| Option | Description | Selected |
|--------|-------------|----------|
| 具体数据值 | 如 "admin' OR 1=1 --"，用例直接可用 | ✓ |
| 数据模板 + 规则 | 如 "SQL注入字符串，包含 OR 1=1 模式" | |

**User's choice:** 具体数据值

---

## Multi-format Export

### 函数架构

| Option | Description | Selected |
|--------|-------------|----------|
| 统一导出函数 + format 参数 | export_test_cases(format="csv")，内部 switch 分派 | ✓ |
| 每种格式独立 @tool | export_to_csv, export_to_json, ... | |
| 保留 Excel + 新增多格式函数 | export_test_cases_to_excel + export_test_cases_multi | |

**User's choice:** 统一导出函数 + format 参数

### CSV 格式规范

| Option | Description | Selected |
|--------|-------------|----------|
| 标准 CSV（UTF-8 BOM） | 兼容 Excel/禅道/TestRail | ✓ |
| 多套 CSV 列映射 | 禅道中文名、TestRail 英文名 | |

**User's choice:** 标准 CSV（UTF-8 BOM）

### JSON 格式规范

| Option | Description | Selected |
|--------|-------------|----------|
| Jira Xray 格式 | {"testCases": [...]}，可直接导入 Jira | ✓ |
| 通用 JSON 数组 | 更通用但不兼容特定工具 | |

**User's choice:** Jira Xray 格式

---

## Claude's Discretion

- DynamicModelSelection 中间件的具体实现细节
- FileContextMiddleware 重构的内部处理器分派逻辑
- test-data-generator SKILL.md 的具体 Prompt 内容
- CSV/JSON/Markdown 导出的具体字段映射
- ConfigDialog Switch 开关的 UI 细节

## Deferred Ideas

None — discussion stayed within phase scope
