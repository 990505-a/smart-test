# 智能测试平台 —— 全面分析（2026-09-17）

本文是对 `smart-test` 平台的一次完整梳理：它由什么组成、数据怎么流、每个模块的
事实源在哪、哪些地方是"看起来能用其实有坑"。最后两节是本轮 9 项改造的落地说明与
遗留清单。

面向读者：接手这个平台的人（包括三个月后的自己）。所有结论都给出文件路径，
可以逐条核对。

---

## 1. 一句话概括

**基于 DeepAgents（LangGraph）+ RAG + MCP + Skills 的企业级测试平台**：四个智能体
（用例生成 / Unity 自动化 / Web-UI 自动化 / 代码分析）跑在 LangGraph 上，
Next.js 提供控制台，SQLite 存业务数据，工作区里的 Markdown 存用例/记忆/产物，
Langfuse 收两条独立的观测链路（日常监控 + 测评）。

```
浏览器 (webui :5013)
   │  SSE 流式对话（@langchain/langgraph-sdk）
   ▼
LangGraph (:5011)  ── 四个 graph，见 graph.json
   │  ├─ testcase_agent       用例生成（飞书导图/代码图谱/记忆）
   │  ├─ unity_agent          Unity 客户端 UI 用例（LuaTestTool :16666）
   │  ├─ webui_agent          浏览器 UI 用例（Playwright runner :5015）
   │  └─ code_analyst_agent   只读代码问答（代码图谱）
   │
   ├─ 工作区（真实路径，configurable.workspace_path）：文件读写 + shell
   ├─ 记忆模块（workspace/<space>/memory/*.md 注入 system prompt）
   └─ 监控上报（可选）→ Langfuse「监控」项目

FastAPI (:5012)
   ├─ 平台 API /api/v2/*（认证、设置、用例文档、测评、记忆、技能…）
   ├─ 测评执行器（起批次 → 驱动 agent → 打分 → 上报「测评」Langfuse）
   └─ 定时任务（代码图谱增量索引）

外部服务：LightRAG(:5014 知识库) / Playwright runner(:5015) / 代码图谱 exe /
Langfuse(:3000) / 飞书 lark-cli / Unity Editor(:16666)
```

---

## 2. 代码地图

| 目录 | 内容 |
|---|---|
| `src/app/agents/` | 四个智能体：`testcase/`（工具最多）、`unity/`、`webui/`、`code_analyst/`。每个 `agent.py` 里是 LLM + backend + 工具 + 中间件 + 系统提示词 |
| `src/app/agents/workspace_backend.py` | **工作区挂载**：`cwd` 按 run 解析（`configurable.workspace_path`），真实路径语义 |
| `src/app/middleware/` | 中间件洋葱：权限门、记忆注入、工作区上下文、思考强度、模型热更、消息修复、工具结果限长、内部调用隔离 |
| `src/app/services/` | 业务服务：用例文档（MD 解析）、飞书、记忆模块、代码图谱、Playwright、Unity、LightRAG、API 自动化、调度器、设置 |
| `src/app/eval/` | 测评：数据集 YAML、runner、三层打分器、门禁、Langfuse 传输层、AI 生成器（`generator.py`）、实时进度（`live.py`） |
| `src/app/monitoring/` | 监控：日常对话的 trace 采集与上报（与测评分开的 Langfuse 配置） |
| `src/app/api/v2/` | 平台 REST API（每个模块一个 router） |
| `src/app/skills/` | 平台技能库（SKILL.md，SkillsMiddleware 渐进披露给 agent） |
| `webui/src/app/` | 控制台页面（`/chat` `/cases` `/eval` `/memories` `/settings` …） |
| `workspace/` | 业务数据：`cases/`（用例 MD）、`memory/`（记忆 MD）、`<agent>/uploads/`（上传）、`eval-runs/`（测评现场） |
| `datasets/` | 评测集 YAML（页面可编辑，容器里挂载为唯一事实源） |

**单一事实源的约定**（重要）：用例 = `workspace/default/cases/<项目>.md`；
记忆 = `workspace/default/memory/*.md`；评测集 = `datasets/*.yaml`；
设置 = SQLite `settings_kv` + `.env`。数据库里没有用例表、没有记忆表。

---

## 3. 一次对话的完整链路

1. 前端 `ChatInterface` 收集输入 + 附件 + 本次对话的配置（模式 / 工作区 / 思考强度 / 权限档），
   经 `useChat.sendMessage` 组成 `configurable`：
   `{space_id, workspace_path, permission_mode, llm_reasoning_effort}`。
2. `client.runs.stream(threadId, assistantId, {input, config})` 打到 LangGraph：
   `assistantId` 就是模式（`testcase_agent` 等），线程懒创建（首条消息时才建）。
3. LangGraph 拉起对应 graph：agent 进程里 backend 的 `cwd` 由 `workspace_path` 决定，
   system prompt 由 系统提示词 + 技能 + 记忆 + 工作区/上传目录 拼成。
4. 模型调用 / 工具调用逐段流回浏览器（`messages` + `tasks` 两个 stream mode）。
   需要审批的 shell 命令会中断，前端弹审批卡片，用户在卡片上决定后 `Command(resume=...)`。
5. 流结束后前端把消息 POST 到 `/api/v2/threads/{id}/messages/save`（顺带写 `thread_infos`，
   含本次的 `agent`），历史消息从此走本地 SQLite 分页，不再依赖 LangGraph 线程状态。
6. 若开了监控：agent 进程把这一轮折叠成一条 Langfuse trace（generation + tool span）上报。

---

## 4. 模块要点

### 4.1 智能体与"模式"

四个 graph 都在 `graph.json` 里注册，区别只是**挂载的工具 / 技能 / 提示词**：

| 模式 | graph | 工具面 | 技能 |
|---|---|---|---|
| 用例生成 | `testcase_agent` | 用例 MD 全生命周期、需求包、Lint/复核、飞书导图、代码图谱、记忆 | `testcase-workflow`、`large-system-testing`、`lark-*` |
| Unity 自动化 | `unity_agent` | Unity HTTP 工具（Lua 执行 / 截图 / 窗口） | `unity-ui-test` |
| Web-UI 自动化 | `webui_agent` | Playwright runner 工具（生成/执行/自修复/截图） | `web-ui-test` |
| 代码分析 | `code_analyst_agent` | 代码图谱四个工具（架构/搜索/调用链/读符号） | — |

> 2026-09 起，模式选择从"顶部 Tab 栏"移入输入框旁（dsh 风格），并且会话会记住
> 自己的模式（`thread_infos.agent`）：点开历史会话会把模式切回去。

### 4.2 工作区（原"挂载仓库"）

- 语义：本次对话挂一个目录作为 agent 的 `cwd`；`ls/glob/grep` 不带路径就在里面找，
  相对路径按它解析，`read_file` 用绝对路径；`execute` 是真实 shell。
- 实现：`agents/workspace_backend.py: WorkspaceShellBackend`（`LocalShellBackend` 子类，
  `cwd` 是动态属性 → 同一份编译好的 graph 服务不同工作区；`virtual_mode=False`）。
- 未挂载时用平台默认目录 `workspace/default/<agent>/`，行为与过去一致。
- 完全权限档下工作区之外也能操作（真实路径 + `inherit_env=True`），这是"给完全权限"的本意。
- 旧的 `/repo/` 只读虚拟挂载（`RepoProxyBackend`）与"必须选仓库"已删除。

### 4.3 记忆（harness 风格）

- 文件：`workspace/<space>/memory/` 下的 `AGENTS.md`（工作区指令）、`MEMORY.md`、
  `USER.md`、`failures.md`、`PROJECT.md`、`DECISIONS.md` + 用户自建模块；
  `manifest.json` 记启用状态/顺序/显示名。
- 注入：`middleware/memory_injection.py` 在每个模型调用前把**启用中**的模块拼进
  system prompt（AGENTS.md 标注为"必须遵守"，其余按预算裁剪；块字节稳定以利 prefix 缓存）。
- 工具：`save_memory` / `record_failure` / `search_memories` / `read_memory_module` /
  `list_memory_modules` / `update_memory_module`（AGENTS.md 只允许用户改）。
- 页面：`/memories` 开关 + 直接编辑 + 关键词检索 + 手动沉淀。
- 旧 EverOS 服务（本地 server + SQLite + LanceDB + Windows 垫片）已整体移除；
  迁移：旧 `user.md` → `USER.md`、旧 episodes 主题 → `MEMORY.md`（各只搬一次）。

### 4.4 测评（Langfuse 闭环）

`观测 → 沉淀 → 实验 → 回归`，详见 `EVAL.md`。本轮变化：
- **裁判模型解析**：设置页优先（DB → .env → 进程环境），不再读进程环境里那份可能过期的
  `LLM_MODEL`（这正是"judge 显示 glm-4.7、agent 却在跑 glm-5.3-flash"的成因）。
- **启动批次**：可多选评测集（每个集子一个批次）+ 数据集内勾选用例（先冒烟两条再全量）。
- **AI 生成测评集**：从历史对话的完整记录（含工具调用）提炼 `input/expected/judge` 草稿，
  人工微调后保存（`eval/generator.py` + `/eval/datasets/generate` + 页面弹窗）。

### 4.5 监控（与测评分开的第二条链路）

- 设置页「Langfuse（监控 · 日常对话）」配 `LANGFUSE_MONITOR_*`，与测评的 `LANGFUSE_*` 独立。
- agent 进程的 `MonitorMiddleware` 采集每个 run：模型调用（模型名/token/耗时/错误）+
  工具调用（参数/结果大小/耗时），折叠成一条 trace，`sessionId` = 会话 id。
- 采集是旁路：未配置就空转，上报失败只写日志——监控挂了不能影响对话。
- 配置热生效：agent 每 15 秒重读 `.env`，改完下一轮对话就上报，不用重启容器。

### 4.6 权限与安全边界

- 两档：`workspace_write`（只读命令白名单自动放行，其余 `execute` 弹审批）/ `full_access`。
- 文件面的"工作区限制"来自后端 root（软限制），不是 OS 沙箱——完全权限档下
  agent 可以操作工作区外路径（by design）。
- 飞书写操作（lark-cli 建/改/删/上传）一律走审批；只读检索默认开启。

---

## 5. 部署与运行

| 方式 | 说明 |
|---|---|
| Docker（本机默认） | `docker compose up -d --build`：langgraph / fastapi / webui / playwright 四容器；`--profile rag` 起 LightRAG，`--profile dsh` 起 dsh 工作台 |
| 本机启动器 | `launcher.py`（控制台 :9000）管理同样几个服务，Windows 上用 `启动控制台.bat` |

- 数据：`./docker-data`（SQLite）、`./workspace`（业务数据）、`./datasets`、`./.env`（设置页会写）
- 改后端代码要 `docker compose build fastapi langgraph && up -d`；改前端要 build webui
  （前端源码在镜像里，不是挂载）

---

## 6. 已知问题与风险（本轮未改）

1. **单进程 SQLite**：LangGraph 与 FastAPI 共用一个 SQLite 文件，写入靠 WAL 串行化。
   并发高时（多人同时跑测评）会成为瓶颈；上 PostgreSQL 是迟早的事。
2. **平台默认工作区是"软边界"**：完全权限档没有 OS 级沙箱，agent 的 `execute`
   能碰整台机器。内网单机工具可以接受，多人共用需要重新评估。
3. **`jupyter`-级长任务无持久队列**：测评批次跑在 FastAPI 的 BackgroundTasks 里，
   容器重启会中断（页面会显示"疑似中断"，已跑完的结果保留）。要跨重启需要真队列。
4. **Legacy 目录仍在**：`workspace/default/memory/smart-test/`（旧 EverOS 数据）、
   `.index/`、`workspace/m72/` 等历史残留可以人工清理，代码已不再读它们。
5. **`tools/rg.exe` 只对 Windows 有意义**：容器里 grep 走 Python 回退，性能一般。
6. **测试环境依赖**：`tests/test_lightrag_service.py::test_health_degrades_when_server_down`
   在本机（有代理）会失败——它断言"不可达"，而本机代理对探测端口返回 502。与代码无关。

---

## 7. 本轮 9 项改造对照

| # | 需求 | 落地 |
|---|---|---|
| 1 | 全面分析平台 | 本文 + `CLAUDE.md` 更新 |
| 2 | 对话页按 dsh 方式切换智能体 | 顶部 Tab 栏删除；输入框旁 `AgentPicker`（含说明与 graph id）；会话记录自己的模式并在点开历史时恢复（`thread_infos.agent`） |
| 3 | 去掉挂载仓库，改为挂载工作区 | `WorkspaceShellBackend`（cwd = 挂载目录、真实路径）；输入框旁工作区选择器 + 管理弹窗；`/repo/` 与仓库选择逻辑删除；提示词改为绝对路径指引；上传文件路径改为绝对路径 |
| 4 | 去掉飞书检索开关，默认开启 | `FeishuReadonlyMiddleware` 改为默认注入（显式 `off` 才关闭）；前端开关与 `?feishu=` 参数删除 |
| 5 | 修复 judge 模型读取 | 裁判回退改走设置页解析路径（`SettingsService.model_values`）；`judge_endpoint_from_settings` 刷新 .env；CLI 同步 |
| 6 | 设置页新增 Langfuse 监控配置 | `LANGFUSE_MONITOR_*` + 设置页卡片 + 连通自检；`monitoring/` 采集日常对话 trace（sessionId=会话） |
| 7 | 启动测评可自定义选择数据集 | `/eval/run` 支持 `datasets[]`（多批次）+ `item_ids[]`（勾选用例）；弹窗支持多选与全选/全不选 |
| 8 | AI 生成测评集 | `eval/generator.py` + `/eval/datasets/generate` + `/eval/sources` + 「AI 生成测评集」弹窗；生成草稿进编辑器微调后保存 |
| 9 | 记忆模块 harness 化 | `memory_service` + 6 个内置模块 + 可开关 + `/memories` 页重写 + 记忆工具重写；EverOS 整体移除并迁移旧数据 |

---

## 8. 验证记录（2026-09-17 凌晨）

- 单测：`229 passed`（新增 `test_memory_injection`(15) / `test_workspace_backend`(10) /
  `test_monitoring`(9) / `test_eval_generator`(12)）；1 项与代码无关的环境失败（见 §6.6）。
- 测评：`smoke-testcase@verify-item-select` 勾选 1 条跑通（judge 1.0，门禁通过）；
  AI 生成：真实对话 → 3 条用例草稿 → 保存成 YAML → 校验通过（验证后已删除）。
- 智能体：真跑一轮 testcase_agent，确认 `ls` 列出的是挂载工作区（`/app/...`）、
  `read_memory_module` 读到 AGENTS.md；监控 trace 落在 Langfuse（env `monitor-verify`，
  4 个 observation，sessionId=会话 id）。
- 前端：`next build` 通过；浏览器实测 `/chat`（模式选择器 + 工作区选择器 + 无飞书开关）、
  `/memories`（6 模块开关 + 编辑）、`/eval`（judge 显示 glm-5.3-flash、AI 生成按钮、
  启动弹窗多选与用例勾选）、`/settings`（两张 Langfuse 卡片）。
