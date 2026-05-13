# Phase 5: Web Automation Agent - Context

**Gathered:** 2026-05-13
**Status:** Ready for planning

<domain>
## Phase Boundary

构建 Web 自动化测试 Agent，支持双模式测试：
- **模式 A（探索性 QA）**：用户提供目标 URL，Agent 执行 6 阶段专业 QA 流程，生成 Playwright TypeScript 测试脚本 + 证据（trace/screenshots/video）
- **模式 B（组件感知测试）**：用户提供源码仓库 URL，Agent 通过 Graphify MCP 分析源码，执行 7-Agent 导演流水线生成 POM + 组件级测试脚本

技术基础：DeepAgents + Skills + CompositeBackend（LocalShell + Filesystem）+ Playwright CLI

本阶段不实现 API 自动化 Agent（Phase 6）、不实现多工作空间隔离（Phase 7）。

**关键参考：** 课堂代码（2026-05-07）已实现完整的 Web Agent，本阶段基于课堂代码适配到现有项目架构。
</domain>

<decisions>
## Implementation Decisions

### 双模式检测与入口 (WEB-01)
- **D-01:** 模式检测采用 LLM 智能判断 — system prompt 包含规则：URL（http/https）→ 探索性QA；源码仓库/git URL/路径关键词 → 组件感知测试。与课堂参考一致
- **D-02:** 额外提供 `detect_test_mode` 工具作为辅助 — 用正则匹配用户消息中的 URL vs 路径/仓库关键词，返回 MODE_A_QA / MODE_B_COMPONENT / ASK_CLARIFICATION
- **D-03:** 组件感知测试需要完整实现 — Git 仓库 URL + Graphify MCP 分析源码（非仅上传文件）

### Playwright CLI 集成 (WEB-02, WEB-08)
- **D-04:** 采用单一 `execute` 工具 — Agent 传入 Playwright 命令字符串，后端用 subprocess 执行并返回结果。LLM token 消耗最少，与 CLAUDE.md 技术栈决策一致
- **D-05:** Phase 5 支持全部 4 个 Playwright 特性 — 会话管理（--storage-state）、视频录制（--video）、Trace 追踪（--trace on）、网络控制（脚本中 route.fulfill()）
- **D-06:** 使用 CompositeBackend = LocalShellBackend（执行命令）+ FilesystemBackend（读写文件），与课堂参考一致

### Skills 与工作流设计 (WEB-03, WEB-04, WEB-05, WEB-07)
- **D-07:** 探索性QA 采用强制多阶段流程 — 类似 TestCase Agent 的 5 阶段模式，通过 pw-dogfood Skill 的 6 阶段工作流强制执行
- **D-08:** 独立 Skills 设计 — 5 个独立 Skill 目录，每个有完整 SKILL.md：
  1. `playwright-cli` — Playwright CLI 使用指南（含 references：元素属性、测试生成、请求mock、运行代码、会话管理、存储状态、trace、视频录制）
  2. `agent-browser` — Agent-Browser 模式浏览器控制
  3. `pw-dogfood` — 专业 QA 技能（6 个子领域：系统探索/证据收集/性能/安全/无障碍/响应式）+ 报告模板
  4. `agent-browser-vs-playwright-cli` — 框架选择决策 Skill
  5. `component-aware-web-automation` — 组件感知测试 + 7-Agent 导演流水线（含 references：7 个角色 guide 文件）
- **D-09:** Skills 目录在 workspace/web/skills/ 下，与课堂参考的目录结构一致

### 7-Agent 导演流水线 (WEB-06)
- **D-10:** 采用课堂模式的 Skill references 实现 — 主 Agent 按顺序加载 `component-aware-web-automation` Skill 的 references 目录下的 7 个角色 guide 文件（script-analyst-guide.md → stage-manager-guide.md → ... → continuity-lead-guide.md），依次扮演不同角色
- **D-11:** 不使用 DeepAgents SubAgent 或 LangGraph 多节点图 — 保持与课堂参考一致，降低复杂度
- **D-12:** 7 个角色顺序固定：Script Analyst → Stage Manager → Blocking Coach → Set Designer → Choreographer → Assistant Director → Continuity Lead

### Claude's Discretion
- 具体的 5 个 SKILL.md 内容从课堂参考代码复制适配
- detect_test_mode 工具的正则匹配规则细节
- ensure_output_dir 的目录结构和命名规范
- check_environment 的 CLI 依赖检查列表
- SYSTEM_PROMPT 的具体措辞和指令细节
- CompositeBackend 的路由配置细节

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 课堂参考代码（主要参考）
- `D:/test_agent/2026-05-07-ai-test-agent-system/2026-05-07-ai-test-agent-system/ai-test-agent-system/src/app/agents/web/agent.py` — Web Agent 主文件，双模式 system prompt、SkillsMiddleware 配置、工具注册
- `D:/test_agent/2026-05-07-ai-test-agent-system/2026-05-07-ai-test-agent-system/ai-test-agent-system/src/app/agents/web/tools.py` — 3 个自定义工具 + CompositeBackend 配置
- `D:/test_agent/2026-05-07-ai-test-agent-system/2026-05-07-ai-test-agent-system/ai-test-agent-system/src/app/agents/web/validate_agent.py` — Agent 验证脚本
- `D:/test_agent/2026-05-07-ai-test-agent-system/2026-05-07-ai-test-agent-system/ai-test-agent-system/src/workspace/web/skills/` — 全部 5 个 Web Skills 目录（含 SKILL.md 和 references/）
- `D:/test_agent/2026-05-07-ai-test-agent-system/2026-05-07-ai-test-agent-system/ai-test-agent-system/src/workspace/web/ARTIFACT_CONTRACT.md` — Web Agent 产物契约

### 现有项目代码（集成点）
- `src/app/agents/web/agent.py` — 当前 Web Agent stub（需替换）
- `src/app/core/config.py` — 项目配置（需添加 Playwright/Graphify 相关配置）
- `webui/src/app/components/AgentTabs.tsx` — 前端 Agent 切换（已有 Web 自动化 tab）
- `graph.json` — Agent 路由配置（已有 web_agent 路由）

### 技术文档
- CLAUDE.md — 技术栈决策（Playwright CLI > MCP mode，单一 execute 工具）
- `D:/test_agent/2026-05-07-ai-test-agent-system/2026-05-07-ai-test-agent-system/multi-agent system for restful api tests.pdf` — 课程资料 PDF

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Web Agent stub** (`src/app/agents/web/agent.py`): 已有基本骨架，可直接扩展
- **graph.json**: 已配置 `web_agent` 路由，无需修改
- **AgentTabs.tsx**: 前端已有 "Web自动化" tab 和 Globe 图标
- **SkillsMiddleware + FilesystemBackend**: 已在 TestCase Agent 中验证的 Skill 加载模式
- **TestCase Agent 架构**: 可参考 3-layer middleware 和 system prompt 设计模式

### Established Patterns
- **create_deep_agent + middleware + tools**: 标准的 Agent 创建模式
- **SkillsMiddleware with sources=[]**: Skill 加载模式，Web Agent 使用 `/web/skills/`
- **FilesystemBackend for skills**: 技能文件通过 FilesystemBackend 管理
- **system prompt 中文**: 所有 Agent 的 system prompt 使用中文

### Integration Points
- **graph.json**: `web_agent` 路由 → `src/app/agents/web/agent.py:agent`
- **workspace 目录**: Web 产物输出到 workspace/web-output/
- **前端 AgentTabs**: 用户切换到 "Web自动化" tab 时自动路由到 web_agent
- **Graphify MCP**: 组件感知模式需要调用 Graphify MCP 分析源码（需确认 MCP 配置）

</code_context>

<specifics>
## Specific Ideas

- 课堂参考代码是主要实现来源，直接适配到现有项目架构
- 5 个 Skills 的 SKILL.md 和 references 目录结构从课堂参考复制
- detect_test_mode 工具的正则匹配规则从课堂参考代码直接使用
- CompositeBackend = LocalShellBackend + FilesystemBackend 从课堂参考适配
- 7-Agent 流水线的角色 guide 文件从课堂参考的 `references/` 目录复制

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 05-web-automation-agent*
*Context gathered: 2026-05-13*
