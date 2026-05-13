# Phase 5: Web Automation Agent - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-13
**Phase:** 05-web-automation-agent
**Areas discussed:** 双模式检测与入口, Playwright CLI 集成, Skills 与工作流设计, 7-Agent 导演流水线

---

## 双模式检测与入口

| Option | Description | Selected |
|--------|-------------|----------|
| LLM 智能检测 | Agent system prompt 包含规则，LLM自行判断 URL vs 源码仓库 | ✓ |
| 前端手动选择 | 前端增加模式选择下拉框，用户手动选择 | |
| 混合模式 | 前端默认智能检测 + 手动覆盖下拉框 | |

**User's choice:** LLM 智能检测（推荐）
**Notes:** 与课堂参考代码一致，system prompt 规则 + detect_test_mode 工具辅助

### 组件感知测试范围

| Option | Description | Selected |
|--------|-------------|----------|
| Git 仓库 URL + Graphify | 完整组件感知测试，调用 Graphify MCP 分析源码 | ✓ |
| Phase 5 只做探索性QA | 延迟组件感知到后续阶段 | |
| 上传源码 + 本地分析 | 用户上传源码文件，Agent 本地分析 | |

**User's choice:** Git 仓库 URL + Graphify（完整）
**Notes:** 需要完整实现组件感知测试

---

## Playwright CLI 集成

### CLI 集成方式

| Option | Description | Selected |
|--------|-------------|----------|
| 单一 execute 工具 | Agent 传入命令字符串，后端 subprocess 执行 | ✓ |
| 细粒度工具集 | navigate/click/screenshot 等独立工具 | |
| MCP 模式 | Playwright MCP Server 暴露多个工具 | |

**User's choice:** 单一 execute 工具（推荐）
**Notes:** 与 CLAUDE.md 技术栈决策一致，token 消耗最少

### Playwright 特性支持

| Feature | Selected |
|---------|----------|
| 会话管理 | ✓ |
| 视频录制 | ✓ |
| Trace 追踪 | ✓ |
| 网络控制 | ✓ |

**User's choice:** 全部 4 个特性都支持
**Notes:** 完整的 Playwright 功能覆盖

---

## Skills 与工作流设计

### 工作流结构

| Option | Description | Selected |
|--------|-------------|----------|
| 强制多阶段流程 | 类似 TestCase Agent 的阶段强制执行模式 | ✓ |
| 自由流程 | Agent 自由决定流程 | |
| 核心强制 + 可选扩展 | 核心阶段强制，其他可选 | |

**User's choice:** 强制多阶段流程（推荐）
**Notes:** pw-dogfood Skill 的 6 阶段工作流强制执行

### Skill 组织

| Option | Description | Selected |
|--------|-------------|----------|
| 独立 Skills | 5 个独立 Skill 目录（playwright-cli, agent-browser, pw-dogfood, agent-browser-vs-playwright-cli, component-aware-web-automation） | ✓ |
| 合并 Skills | 合并为 2-3 个核心 Skill | |
| Claude 决定 | 只要覆盖所有 WEB-* 需求 | |

**User's choice:** 独立 Skills（推荐）
**Notes:** 与课堂参考代码的 Skill 结构一致

---

## 7-Agent 导演流水线

### 初始选择

| Option | Description | Selected (initial) |
|--------|-------------|----------|
| 单 Agent 角色切换 | system prompt 角色切换 | |
| LangGraph 多节点图 | StateGraph 7 个节点 | ✓ (initial) |
| 主 Agent + Tool 子任务 | 主 Agent 通过 tool 触发子任务 | |

**User's choice:** LangGraph 多节点图（初始选择）
**Notes:** 用户后续发现 DeepAgents 有原生 SubAgent 支持

### DeepAgents SubAgent 发现

用户指出 DeepAgents 有原生 SubAgent 机制（`SubAgent`, `SubAgentMiddleware`, `AsyncSubAgent`）。
检查后发现 SubAgent 支持：name、description、system_prompt、tools、middleware 独立配置。

**Updated question with SubAgent option:**

| Option | Description | Selected (updated) |
|--------|-------------|----------|
| DeepAgents SubAgent | 原生 SubAgent 机制，7 个子角色独立注册 | ✓ (updated) |
| LangGraph 多节点图 | StateGraph 7 个节点 | |
| 主 Agent + Tool 子任务 | 主 Agent 通过 tool 触发子任务 | |

**User's choice:** DeepAgents SubAgent（更新选择）

### 课堂参考代码发现

检查课堂参考代码后发现：
- 课堂代码**没有**使用 SubAgent 或 LangGraph 多节点图
- 7-Agent 流水线通过 `component-aware-web-automation` Skill 的 `references/` 目录下的 7 个 guide 文件实现
- 主 Agent 按顺序加载 guide 文件，依次扮演不同角色

**Final question:**

| Option | Description | Selected (final) |
|--------|-------------|----------|
| 课堂模式：Skill references | 主 Agent 加载 Skill references 中的角色 guide 文件 | ✓ (final) |
| DeepAgents SubAgent | 每个 SubAgent 角色独立 | |
| 混合模式 | 核心用 Skill references，复杂步骤用 SubAgent | |

**User's choice:** 课堂模式：Skill references（推荐）
**Notes:** 与课堂参考保持一致，降低复杂度，与现有 Skill 模式一致

---

## Claude's Discretion

- SKILL.md 具体内容从课堂参考复制适配
- detect_test_mode 正则规则细节
- ensure_output_dir 目录结构
- check_environment CLI 检查列表
- SYSTEM_PROMPT 具体措辞

## Deferred Ideas

None — discussion stayed within phase scope
