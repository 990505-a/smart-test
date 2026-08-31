# 智能测试平台大改造 — 设计文档

日期：2026-08-26
状态：实施中

## 目标

将现有平台（用例生成 / Web 自动化 / API 自动化 三智能体 + FastAPI + Next.js）改造为覆盖
**游戏测试全生命周期** 的平台，面向游戏项目 `E:\m72-publish\m72`（Unity + Lua 客户端，C# 服务端）。

## 模块总览

| 模块 | 技术方案 | 位置 |
|---|---|---|
| 用户模块 | SQLite User/AuthToken 表 + PBKDF2 密码哈希 + Bearer Token | `src/app/db/models/user.py`, `src/app/api/v2/auth.py` |
| 设置模块 | Configuration 表 KV + 用户资料接口（用户名/密码/模型） | `src/app/api/v2/settings.py` |
| 用例生成模块 | 保留 deepagents + skill + mcp 架构；新增「生成完成 → lark-cli 保存飞书思维导图 + DB 留存」 | `src/app/services/feishu_service.py`, testcase agent 新工具 |
| 用例沉淀模块 | ReviewBatch/CaseReview 表；需求外发后回看，好/坏 + 原因标注，二次标注 | `src/app/db/models/review.py`, `src/app/api/v2/reviews.py` |
| 自进化模块 | 参考 openclaw/hermes：聚合标注 → LLM 反思 → 蒸馏经验 → 回写模块 Skill；APScheduler 每日 02:00（可配）自回归 | `src/app/services/evolution_service.py`, `src/app/services/scheduler.py` |
| Skill 模块 | 按游戏模块对「好」用例蒸馏生成 `src/app/skills/modules/<module>/SKILL.md`，用例 Agent 自动加载 | `src/app/services/skill_distiller.py`, `src/app/api/v2/skills.py` |
| MCP 模块 | FastMCP 实现三个 server：rag（RAGFlow HTTP API）、git（本地 git 命令）、codebase-memory（HTTP/CLI 代理） | `src/app/mcp_servers/` |
| RAG 模块 | RAGFlow（外部服务，base_url + api_key 可配） | `src/app/services/ragflow_service.py` |
| 代码分析模块 | git diff → codebase-memory 符号定位 → grep 验证 → LLM 精确分析新增功能 | `src/app/services/code_analysis_service.py` |
| 接口自动化模块 | lark-cli 拉飞书 API 文档 → LLM 生成首版 pytest 脚本 → 执行 → 异常时 AI 对照文档自修复 | `src/app/services/api_auto_service.py` |
| UI 自动化模块 | vendor unity-auto-test skill（HTTP :16666 LuaRemoteServer），unity_agent + 直接工具 | `src/app/skills/unity-ui-test/`, `src/app/agents/unity/`, `src/app/services/unity_service.py` |

## 关键设计决策

1. **认证**：PBKDF2-HMAC-SHA256（hashlib 内置，零新依赖）；token 表存 `secrets.token_hex`；
   首次启动自动创建 `admin/admin123`。新模块路由强制登录，旧路由保持兼容（可选认证）。
2. **飞书 CLI**：本机已装 `lark-cli@1.0.70`。`feishu_service` 以 subprocess 调用：
   - 思维导图：`lark-cli mindnotes nodes create --mindnote-id <id> --data @file --as user`
   - 文档拉取：`lark-cli docs +fetch --doc <url>`
   lark-cli 不可用 / 未配置 mindnote-id 时优雅降级（记录 skipped，不阻断主流程）。
3. **自进化参考 openclaw/hermes** 的三步循环：
   a. 聚合上次进化以来的好/坏标注（含原因）
   b. LLM 反思：提炼「好的模式 / 坏的反模式 / 改进指令」
   c. 将经验回写对应游戏模块的 SKILL.md（追加 Lessons 段），记录 EvolutionRun
4. **模块 Skill 蒸馏产物落到 `src/app/skills/modules/`**：testcase agent 的 SkillsMiddleware
   sources 已指向 `/skills/`（→ `src/app/skills/`），新增子目录即被自动发现，无需改 agent。
5. **MCP servers 用 fastmcp**（依赖已在 pyproject）。每个 server 可独立 `python -m` 启动，
   也注册进 `mcp_client.py` 供 agent 连接。codebase-memory server 做 HTTP 代理
   （`CODEBASE_MEMORY_MCP_URL` 指向正在运行的 codebase-memory 实例）。
6. **RAGFlow**：纯 HTTP 客户端封装（httpx），不做本地 LightRAG。环境变量
   `RAGFLOW_BASE_URL` / `RAGFLOW_API_KEY`。
7. **Unity UI 自动化**：把 `unity-auto-test-skill-master` 整体 vendor 进
   `src/app/skills/unity-ui-test/`（python/ guides/ scripts/ SKILL.md），
   `unity_service` 直接 import 其 python 层；`unity_agent`（deepagents + SkillsMiddleware）
   注册进 graph.json，前端新增「UI自动化」tab。
8. **调度器**：APScheduler AsyncIOScheduler 挂在 FastAPI lifespan；cron 表达式
   由 `EVOLUTION_CRON_HOUR`/`EVOLUTION_CRON_MINUTE` 或 settings 页配置。
9. **前端**：新增 /login、/settings、/reviews、/evolution、/skills、/api-auto、/ui-auto 页；
   ManagementLayout 导航扩展 + 用户菜单；api-client 统一带 Bearer token。

## 数据库新表

- `users`, `auth_tokens`
- `case_review_batches`, `case_reviews`
- `evolution_runs`
- `distilled_skills`
- `api_scripts`, `api_script_runs`
- `ui_scripts`, `ui_script_runs`
- `code_analysis_reports`

全部走 `Base.metadata.create_all`，启动自动建表。

## 服务端口（不变）

- LangGraph server :2026（graph.json 增加 `unity_agent`）
- FastAPI :8000（/api/v2 新增 auth/settings/reviews/evolution/skills/api-auto/ui-auto/code-analysis/mcp 路由）
- Next.js webui :3000
