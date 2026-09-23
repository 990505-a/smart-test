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
LangGraph (:5011)  ── 5 个 graph，见 graph.json
   │  ├─ smart_test_agent     通用测试助手（对话页唯一入口，能力来自清单）
   │  ├─ testcase_agent       ⚠️ 旧会话兼容（薄壳，同样由清单装配）
   │  ├─ unity_agent          ⚠️ 旧会话兼容
   │  ├─ webui_agent          ⚠️ 旧会话兼容
   │  └─ codebase_agent       代码问答（只被无头影响分析使用，不面向对话）
   │     smart_test_agent 同时也是**用户在 /agents 页定义的所有智能体**的载体
   │
   ├─ 工作目录（真实路径，configurable.workspace_path）：文件读写 + shell
   ├─ 记忆模块（workspace/<space>/memory/*.md 注入 system prompt）
   └─ 监控上报（可选）→ Langfuse「监控」项目

FastAPI (:5012)
   ├─ 平台 API /api/v2/*（认证、设置、用例文档、测评、记忆、技能…）
   ├─ 测评执行器（起批次 → 驱动 agent → 打分 → 上报「测评」Langfuse）
   ├─ 定时任务（代码图谱增量索引）
   └─ 无头智能体调用（services/agent_runner.py：索引后的增量影响分析）
   └─ 定时任务（代码图谱增量索引）

外部依赖（描述的唯一来源：core/integrations.py 注册表 + GET /api/v2/integrations）：
LightRAG(:5014 知识库) / Playwright runner(:5015) / codebase-memory（平台自管安装的
官方二进制，无端口） / Langfuse(:3000) / 飞书 lark-cli / Unity MCP 桥(:5016)
```

---

## 2. 代码地图

| 目录 | 内容 |
|---|---|
| `src/app/agents/` | **能力清单驱动的装配**：`capabilities.py`（能力=数据：工具符号/技能/提示词/审批/依赖）+ `harness.py`（唯一装配器 `build_agent`）+ `general/`（对话页唯一智能体）。各能力只提供自己的 `tools.py` 与技能；`testcase/`、`unity/`、`webui/` 的 `agent.py` 已退化为旧会话兼容薄壳 |
| `src/app/agents/workspace_backend.py` | **工作目录**：`cwd` 按 run 解析（`configurable.workspace_path`），真实路径语义 |
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

### 4.1 通用智能体与能力清单

**对话页只有一个智能体**（`smart_test_agent`），专项能力全部挂在它的一个工具面上，
由它自己判断该用哪一类 —— 用户不再先选模式。装配来自**能力清单**
（`agents/capabilities.py`），加一个能力就是加一条声明：

```python
Capability(key="api-explore", label="接口探索执行",
           description="…",            # ← 这几行字就是路由依据
           skill="api-explore",
           domain_prompt="…",
           tools=("…模块:符号", …))
```

| 能力 | 进对话页 | 工具数 | 技能 | 专属入口 |
|---|---|---|---|---|
| 用例生成 | ✓ | 18（含记忆 6） | `testcase-workflow` | — |
| Unity 自动化 | ✓ | 18 | `unity-ui-test` | — |
| Web-UI 自动化 | ✓ | 8 | `web-ui-test` | — |
| 代码分析 | ✓（需挂仓库） | 4 | — | — |

代码分析需要先挂一个具体仓库（cwd = 该仓库、图谱工具按它解析项目名）：

- **对话页（2026-09）**：输入框旁的「代码图谱仓库」选择器挂一个「代码图谱」里注册的仓库
  （`?repo=<id>`），它随 run 作为 `configurable.workspace_path` 传下去。
  这是唯一的**交互式**入口 —— 原来的「代码图谱 → AI 分析」Tab 已删除（与对话页重复）；
- 另一半是无头的：索引后自动跑的「增量影响分析」（见 4.5），报告在代码图谱页的
  「定时任务」Tab 里看，不产生对话。

它声明了 `requires_repo=True`：**没挂仓库时这 4 个图谱工具不进工具面**。它们靠挂载
路径解析项目名，没挂载时调什么都会立刻返回降级提示（连 exe 都不调）—— 给模型 4 个
必然报错的工具只会让它白试一轮。所以装配开关开着也不会有副作用：工具按上下文出现。
没在「代码图谱」注册过的仓库不需要这套：直接让智能体用 `grep` / `read_file` 读绝对
路径就行（能力段的提示词里写明了这条路，文件工具本来就不限制范围）。

装配可见性：`GET /api/v2/agents` + `/agents` 页（工具符号、来源模块、技能库、
已注册 graph、外部依赖、人工审批项全在里面）。

**装配目录（2026-09 重构）**：层级是 **智能体 → 能力 → 工具 / 技能 / 权限**，
全部是可编辑的用户数据，存在 `workspace/<space>/assembly.json`（v2，
`services/assembly_service.py`）。代码里的 `CAPABILITIES` 退化为**种子 + 工具候选池**
（工具是 Python 函数，界面造不出来，只能从池子里挑）。

| 层 | 有什么 | 谁能建 |
|---|---|---|
| 智能体 | 名字 + 说明 + 装配了哪些能力（对话页可切换） | 用户（页面上建） |
| 能力 | 名字 + 说明 + 领域提示词 + 工具集合 + 技能集合 + 依赖仓库 + 需审批的工具 | 用户 |
| 工具 | 清单里声明过的 36 个（按来源模块分组，带 docstring 首行） | 只能从池子里挑 |
| 技能 | `src/app/skills/` 下的 7 个 SKILL.md | 只能从池子里挑 |

- **一个 graph 服务任意多个智能体**：构建期把所有工具都挂上，每轮按
  `configurable.agent_id` 现算"这个智能体此刻有哪些能力"，然后过滤 `request.tools`、
  把 system prompt 里 `<!--@capabilities-->…<!--/@capabilities-->` 那段换成它的
  能力清单（身份 + 分诊表 + 领域规则 + 依赖）、按能力声明的技能过滤技能清单。
  所以：换智能体、加能力、卸工具、改名改领域提示词，**下一轮就生效，不用重启**。
- **技能不再是独立的库**：模型看得见的技能 = 当前智能体各能力声明的技能之并集。
  卸载是**提示级**（`/skills/` 仍只读挂载，模型猜路径仍读得到）—— 与"技能绑定是
  提示级而非访问控制级"是同一个取舍。
- **审批是现查的**：候选池里每个工具都在 `interrupt_on` 里登记一条 `when` 谓词，
  每轮现查目录（`is_tool_gated`）。在能力编辑器里勾上"需要人工审批"，下一轮就弹卡片。
- 接口：`GET /api/v2/agents`（目录 + 候选池）、`PUT /agents/catalog`（整份保存，
  引用了不存在的东西会丢掉并在 `ignored` 里回报）、`DELETE /agents/catalog`（恢复默认）。
- **工具 vs 技能的新增方式不同**：技能在 `/skills` 页上传（落到 `src/app/skills/`），
  每轮现扫目录，**不用重启**，只需在能力编辑器里勾上；工具是代码里的 `@tool` 函数，
  在 `agents/capabilities.py` 清单里声明，graph 编译期注册进 `ToolNode` ——
  加了新工具要**重启 LangGraph**（`POST /api/v2/agents/reload`，即装配页右下角那个
  「重新加载工具池」，它转发给启动器 :5010）。候选池 `mcp_servers` 字段留给将来的外部
  MCP server（接上后外部工具就是配置即用，不用改代码）。
- 旧单能力 graph **不受目录影响** —— 它们是历史会话的"老样子"。

历史兼容：早期三个能力是三个独立模式，会话里记着自己的 graph 名。`testcase_agent`
/ `unity_agent` / `webui_agent` 作为**薄壳**保留（同样由清单装配），只为让老会话
还能续跑；新会话一律 `smart_test_agent`。确认没有会话再指向它们后，删掉 `graph.json`
里对应条目即可。

> 注意：`skills` 挂载是**整库**（`/skills/`），所以每个 skill 的 name/description 都
> 会进提示词、正文按需读。因此**技能绑定是提示级而非访问控制级** —— 靠清单里的
> 分诊表引导模型读哪一个。要"某能力看不见某技能"需要子智能体，而 deepagents 的
> isolated 子智能体拿不到对话历史，多轮流程会断，所以这里没走那条路。

### 4.2 工作目录

「工作区」这个用户可见概念已删除（原选择器 / 「管理工作区」弹窗 / localStorage /
`workspaces` 表与 CRUD 全部移除）。现在只有一条路径来源：

- **代码图谱里注册的仓库**是唯一"给智能体一个路径"的入口：**对话页输入框旁的
  「代码图谱仓库」选择器**（`?repo=<id>`）。挂上后 `repo.repo_path` 同时是 agent 的 `cwd`、
  相对路径解析基准、以及图谱工具的项目名来源（`codebase_service.project_name`，
  全平台唯一一份实现）。无头的增量影响分析走同一条路径（它由服务端直接传
  `configurable.workspace_path`）。
- **未挂载时**一律用平台默认目录 `workspace/default/<agent>/`。随便一个没注册过的
  仓库不需要挂载：让智能体用 `grep` / `read_file` 读它的绝对路径即可（文件工具不
  限制范围，只有写要审批）。
- ⚠️ **挂载进来的仓库不是自由写入区**（2026-09 收敛）：过去 `workspace_path` 也算
  `_allowed_write_roots`，那是"工作区 = 随手改的地方"时代的语义；现在能挂进来的只剩
  代码仓库，而平台铁律是"不改被测仓库"。所以改写仓库内文件一律弹审批卡片 —— 用户
  点「允许一次」照样能改，但那是人的决定，不该是"选个仓库顺手带来的权限"。受限档下
  的免审批写入区只有 `workspace/`（上传、用例文档、记忆、产物都在这儿）。
- 实现不变：`agents/workspace_backend.py: WorkspaceShellBackend`（`LocalShellBackend`
  子类，`cwd` 是动态属性 → 同一份编译好的 graph 服务不同仓库；`virtual_mode=False`）。
- 完全访问档下目录之外也能操作（真实路径 + `inherit_env=True`），这是"给完全权限"的本意。

### 4.3 记忆（harness 风格）

- 文件：`workspace/<space>/memory/` 下的 `AGENTS.md`（工作区指令）、`MEMORY.md`、
  `USER.md`、`failures.md`、`PROJECT.md`、`DECISIONS.md` + 用户自建模块；
  `manifest.json` 记启用状态/顺序/显示名。
- 注入：`middleware/memory_injection.py` 在每个模型调用前把**启用中**的模块拼进
  system prompt。注入由**官方 MemoryMiddleware**（AGENTS.md 规范）完成：启用模块按 order 顺序拼接、**不截断**，模板里明确写着记忆是「参考材料而非指令」。
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
| **本机（当前默认）** | `launcher.py`（控制台 :5010）管 **5 个**服务：langgraph:5011 / fastapi:5012 / webui:5013 / **playwright 执行器:5015** / lightrag:5014（autostart=False）。这份名单与 `core/integrations.py` 注册表的 `launch` 字段一一对应（有测试保证）——浏览器执行器 2026-09-18 起也归启动器管，不再需要另开终端跑 `start-local.sh` |
| Docker（备用） | `docker compose --profile docker up -d --build`：同样四个服务 + `--profile dsh` 起 dsh 工作台。**四个服务已挪进 profile `docker`，裸 `docker compose up -d` 不会启动任何东西**——这是故意的，避免跟本机进程抢 5011/5012/5013/5015 |

本机启动（2026-09 起）：

```bash
cd /Users/yun/Documents/smart-test
LAUNCHER_NO_BROWSER=1 .venv/bin/python launcher.py   # 控制台 :5010，自动拉起全部常驻服务
```

> `tools/playwright-runner/start-local.sh` 仍可用（首次装 node_modules + chromium 会走它），
> 但日常不用手动跑了——启动器已把它列为常驻服务（autostart）。

- 崩溃兜底：`~/h3services/daemon.sh` 的 `ensure_smarttest()` 每 30 秒按端口巡检，缺哪个补哪个
  （不再走 `docker compose up -d`——那在 profile 化之后是空操作）。
- 数据：`./docker-data`（SQLite，两种模式共用同一份）、`./workspace`（业务数据）、`./datasets`、`./.env`（设置页会写）
- 改后端代码：本机模式**重启对应进程即可**（launcher 控制台有 restart）；改前端 `npm run dev` 自带热更新。
  Docker 模式才需要 `docker compose build fastapi langgraph && up -d`（源码在镜像里，不是挂载）。
- 本机模式下 agent 的 `execute` 就是本机 shell、`read_file` 收真实路径，**能直接读宿主任意路径**
  （如 `/Users/yun/Documents/ruoyi-vue-pro`），不需要挂载；Docker 模式才需要往容器里挂源码。

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

## 9. Unity 自动化真机验证（2026-09-19）

用三个**真实开源 Unity 游戏**验证（不是自造 smoke 工程）。三条用例都跑通"探索界面 →
点交互 → 断言内容 → 截图存证"，经平台 `/unity-auto` 落库并执行，全部 `passed`：

| 游戏 | 工程 / 许可 | Unity | 用例覆盖 | 结果 |
|---|---|---|---|---|
| projectZero | trolit/projectZero · MIT | 2018.3 → 2022.3 | 主菜单 7 个按钮 + 波兰语标签 → 点 MEDALE 进奖牌页 → 返回 | passed 7.8s · 3 图 |
| Trash Dash | Unity 官方 EndlessRunnerSampleGame · Unity Companion | 2021.3 → 2022.3 | 商店外壳 → ITEMS/CHARACTERS/THEMES 三页签内容与价格 → 无新增报错 | passed 0.9s · 3 图 |
| Chop Chop | Unity 官方 open-project-1 · Apache-2.0 | 2020.3 → 2022.3 | 主菜单 5 入口 → 设置页 → 页签互斥 → Anti Aliasing 4x→8x → Save | passed 2.6s · 4 图 |

工程在 `~/Documents/unity-games/{project-zero,trash-dash,chop-chop}`（约 9 GB，MCP 插件已装）。
`_packages/unity-mcp-10.2.0/` 是插件的本地副本：trash-dash 用 `file:` 引它，因为 UPM 直接
从 git 拉这个包在本机会被网络抖动打断（`early EOF`）。

这一轮在真游戏上改掉的桥缺陷（都有回归测试，单测 502 → 514）：

1. 会话过期只对 `_rpc` 自愈，资源读/直接调用不自愈 —— 平台长驻进程会一直显示"未连接"。
2. MCP 会话被绑在它第一次看到的 Unity 实例上，那个编辑器退出后同一条会话永远读不到实例
   → 会话级失败先重建会话再读一次。
3. `find_objects` 只补前 10 个详情，真游戏一次查回几十个时其余是 `name=None` 空壳
   → 默认全补，并回 `count`/`detailed` 让截断可见。
4. 按钮标签在子对象上而 `object_text` 只读自己 —— "按钮上写着什么"这条最常用的断言
   永远失败 → 加 C# 子树兜底（Text / TMP / InputField 都收）。
5. 截图走相机渲染，**拍不到 Screen Space - Overlay 的 UI**（Trash Dash 的商店场景里
   根本没有相机）→ 改用 ScreenCapture 截游戏视图，失败再退回相机工具。
6. `console(types=...)` 传字符串被服务器拒、`exception`/`assert` 属非法取值 → 归一成 list 白名单。
7. `errors()` 只认顶层键，而服务器把条目放在 `data.items` 里 → 明明有报错也返回空，
   "断言控制台无报错"等于没测。
8. 同名对象（每个面板各有一份 SaveButton）取第一个 → 改成优先挑当前可见的那份；
   另外名字两端空白按 Trim 比对（实测 `Button Settings ` 带尾随空格）。

已知遗留：键盘输入合成（新版 Input System 的 `QueueStateEvent`，含放宽 Game View 焦点规则）
在编辑器里没能触发游戏的 Cancel 动作 —— "只能按 Esc 关掉"的界面暂时自动化不了。细节与
规避写法见 `src/app/skills/unity-ui-test/SKILL.md`。

## 10. 大型中文游戏实测：jynew《群侠传，启动！》（2026-09-19）

第四个验证对象，也是"大型 + 中文"那个：`jynew/jynew`（致敬《金庸群侠传》的武侠 RPG，
Steam / TapTap / App Store 已上架，8960 星，仓库 5.3 GB、7.5 GB 工作区、3236 个 C# 脚本）。
工程在 `~/Documents/unity-games/jynew/jyx2`。

用例：**《群侠传，启动！》HUD / 系统菜单 / 背包冒烟**（平台 `/unity-auto` 上 `passed`，
1.5s、4 张截图）：HUD 断言（主角 莫穿林 / 地图 莫桥山庄 / EXP / 三个功能按钮）→ 点「系统」
断言菜单五项 → 「返回游戏」关闭 → 点「背包」断言六个分类 → 「关 闭」关闭 → 无新增报错。

在 Apple Silicon 上把它跑起来，踩了四个坑（都已就地解决）：

1. **工程版本号是中国版 `2020.3.32f1c1`，国际版编辑器直接拒开**（`not a valid Unity version`）
   → 改成 `2020.3.32f1`。
2. **xlua 的原生库只有 x86_64/i386**，arm64 编辑器加载不了（`DllNotFoundException: xlua`）
   → 用 Tencent/xLua v2.1.15 源码（Lua 5.3.5 + luasocket，补 `luaconf.h`、
   `-DLUA_USE_MACOSX -DLUA_COMPAT_5_2`）编出 arm64 bundle，与原来的 x86_64/i386
   `lipo` 成通用二进制，替换 `Assets/Plugins/xlua.bundle/Contents/MacOS/xlua`。
3. **`Assets/XLua/Gen/` 是空的**（生成代码不入库）→ 跑一次编辑器菜单 `XLua/Generate Code`。
4. **生成出来的包装编译不过**（xLua 2.1.15 不支持 `Span<T>`/`ReadOnlySpan<T>` 参数，
   而 2022.3 的 Object/Transform 新增了这类重载）→ 加 `Assets/Editor/XluaGenConfig.cs`，
   用 `[BlackList]` + `Func<MemberInfo,bool>` 把带 ref struct 的成员整体排除。

运行方式：**直接在编辑器里打开 `Assets/Mods/SAMPLE/Maps/GameMaps/01_moqiaoshanzhuang.unity`
再进 Play**。编辑器下打开 `Assets/Mods/` 里的场景会自动选中对应 MOD
（`RuntimeEnvSetup` 的调试分支），不需要走模组管理器。

这一轮又改掉四个桥缺陷（单测 514 → 520）：

9. 服务器的 `by_name` **对运行时克隆出来的对象一个都查不到**（`MainUIPanel(Clone)` 这种），
   `by_path` 却查得到 → 名字查空时自动按路径回退一次。
10. `include_inactive: true` 会让查询**整个返回空**（默认行为本来就含未激活对象）→ 不再传这个参数。
11. 面板/列表的文本要 `subtree_text()`：容器自己身上可能挂着无关的 text/value
    （实测 SystemUIPanel 自己回 `1023799`），`object_text()` 会先取到那个。
12. 界面开关要 `is_visible()` / `expect_hidden()`：关面板是**停用对象**而不是移出场景，
    用 `exists()` / `expect_absent()` 判断会一直等到超时。
另加两项能力：**按可见文本点击**（`u.click("返回游戏")`，文本层会从标签往上找可点对象）
和**非 Button 控件的完整指针序列**（down→up→click，带对象中心坐标 —— UIWidgets 这类
自定义列表项只发 pointerClick 选不中）。

## 11. Unity 存证链对齐（2026-09-19）：截图 / 录像 / 步骤轨迹 / 失败现场

**起因**：用户问「Web-UI 自动化前端能看到截图、失败视频，为什么 Unity 什么都看不到，
是不是有功能没实现」。查下来答案是**对，缺的正是证据链**：

| 能力 | Web-UI（Playwright） | Unity（改造前） |
| --- | --- | --- |
| 截图 | runner 自动（失败必留）+ HTML 报告内嵌 | 只有用例自己 `u.screenshot()` 才有一张，**没有回取接口** |
| 录像 | Playwright `video: retain-on-failure` | 无 |
| 逐帧 trace | `trace.zip` + 官方 HTML 报告（可回放） | 无 |
| 失败上下文 | `error-context.md`（Playwright 生成） | 无 |
| 前端呈现 | `ArtifactGallery`（缩略图/大图/播放器/下载） | 只显示一串**文件名** |
| 产物地址 | 签名 URL（`<img>`/`<video>` 带不上自定义头） | 无（绝对路径写在 DB 里） |

也就是说「前端看不到」不是渲染问题，而是**后端从来没有把产物搬出来**，执行侧也从来不
自动留证据：用例在断言上挂掉、根本没走到自己那行 `screenshot` 时，**证据为零**。

### 这一轮补上的东西

**执行侧（`services/unity_service.py` 的 prelude + `unity_bridge.py`）**

1. **步骤轨迹**：桥给动作方法（click / set_text / wait_for / expect_* / screenshot /
   play…）套了一层"记一笔"装饰器，每个动作写一行 JSONL（序号、相对时间、目标、耗时、
   成败、错误文本）。嵌套调用只记最外层（`expect_exists` 内部走 `wait_for`，两层都记
   会出现成对重复行）。轨迹在 runner 注入 `UNITY_TRACE_FILE` 后自动开，用例一行都不用写。
2. **失败现场**：`atexit` + `sys.excepthook` 收尾 —— 用例挂掉时自动补一张 `failure.png`，
   再写 `failure.txt`：报错原文、最后 25 步、控制台 error/warning 摘录、最后操作对象的
   子树文本（"按钮点了没反应"和"按钮不存在"当场分开）。
3. **录像**：Playwright 有 `video`，Unity 没有等价 API。做法是**编辑器侧逐帧采 + 平台侧
   ffmpeg 合成**：用 `EditorApplication.update` 起一个每拍抓一帧的回调
   （`ScreenCapture.CaptureScreenshotAsTexture` → jpg → Unity 临时缓存目录），跑完平台读盘
   用 ffmpeg 合成 H.264 mp4。**默认开录**（Playwright 的 retain-on-failure 精神，但默认保留，
   因为"想看看到底怎么失败的"是常态）。踩到的两个硬坑：
   - `EditorApplication.update` 是**命名委托类型** `CallbackFunction`，不能用
     `System.Action` 去 `+=`/`-=`（编译期直接失败），局部变量必须声明成那个类型；
   - `record_start` 里定义的委托**没法被之后的 `record_stop` 引用**（MCP 每次
     `execute_code` 都是新编译的一份代码），开关与计数只能放 `UnityEditor.SessionState`，
     回调自己看见 false 就退订。
   合成帧率按**实测速率**算（编辑器节拍 3~10fps，写死请求帧率会快放）。
4. **产物收集**：运行目录里的 png/jpg/mp4/txt/md/json/jsonl/… 全进产物清单（上限 40 个）。

**接口与前端**

5. `GET /unity-auto/runs/{run_id}`：单条执行详情（产物清单 + 步骤轨迹），执行中可轮询。
6. `GET /unity-auto/artifact/{run_id}/{index}?sig=…`：**按序号**取产物 —— 序号→路径的映射
   只有平台知道，既不用把绝对路径塞进 URL，也顺带没有目录穿越；鉴权走 `share_link` 签名
   （`<img>`/`<video>` 是浏览器自己发的请求，带不上 `X-Auth-Token`）。文件被清理时明确回
   410，前端据此不画破图。
7. `POST /scripts/{id}/run` 现在**先建执行记录再入队**并返回 `run_id`：前端点"执行"后直接
   打开详情，看着步骤轨迹一条条冒出来（轨迹是执行中就在写盘的），不用"等 3 秒刷新列表"。
8. 前端：`ArtifactGallery` 抽成两个模块共用（取文件的 URL 由 `urlFor` 注入），新增
   `components/unity-auto/RunDetail.tsx` —— 统计条 + 步骤时间线（失败步骤红底展开错误）
   + 产物存证（缩略图/大图查看器/录像播放器）+ 原始输出；执行历史列表多一列「存证」
   （`16 步 · 4 图 · 录像 · 1 文本`）。顺手修了状态徽章首屏误报"Unity 桥未连接"。

### 验证（真机：jynew《群侠传，启动！》）

- 通过路径：`群侠传启动 …冒烟` 跑出 `steps.jsonl`(16 步) + 4 张截图 + `run.mp4`，退出码 0；
  浏览器实开 `/unity-auto` → 历史 → 看详情：4 张缩略图 `naturalWidth=1386/691`（真的解码了）、
  `<video>` `readyState=4`、步骤时间线 16 行全部渲染。
- 失败路径（故意让 `expect_text` 断言不存在的文本）：自动产出 `failure.png`（正是失败那一刻
  系统菜单打开的界面）+ `failure.txt`（含"第 4 步 expect_text 失败"与控制台摘录）+ 20 帧录像。
- 存证故障不改判结果：ffmpeg 缺失 / 帧目录不在本机只写 `WARN`，退出码仍由断言决定。
- 单测 520 → **535**：桥侧新增轨迹落盘、失败现场、录像合成（有 ffmpeg 时真合成 mp4）、
  录像开关、不带文件名截图落运行目录；接口侧新增产物清单/签名 URL/坏签名 403/清理 410/
  入队返回 run_id 等 7 条（`tests/test_unity_evidence.py`）。

仍缺（跟前一节口径一致）：**没有 trace.zip 那样的逐帧回放控件**，Unity 这边的"逐帧回看"
就是那段 mp4；**录像帧里带 Game View 工具条**（ScreenCapture 抓整个 Game View 窗口，
换成相机渲染会漏掉 Screen Space Overlay 的 UI）。

## 12. 事故与修复：并发工具调用把 Unity 服务器"打死"（2026-09-19）

**现象**（用户报的）：对话里一张 `unity_find_objects` 卡片一直显示「执行中」，整轮对话卡住约
5 分钟后断了；那一轮里模型**一步发了 3 个工具调用**（`write_todos` + 两个 `unity_find_objects`），
状态里只有 1 个 Unity 调用有结果。

**定位**：
- 桥本身是好的 —— 同一时刻手工跑一次查询 0.1~0.3s 返回；
- `faulthandler.dump_traceback_later` 抓栈：两条卡住的线程都停在
  `http/client.py::_read_next_chunk_size`（**读响应体**），调用链是
  `_find_objects_sync → McpClient.call → _HttpTransport.rpc`；
- 复现：同一进程里并发发 3 个 `find_objects` —— 每轮**只有 1 个返回**，其余永远不回。

**根因**：`mcp-for-unity` 服务器**一次只服务一条请求**。并发打过去，它把第一条正常回完，
其余的既不回也不报错，客户端就永远卡在读响应体上（socket 超时后按重试再打，于是整轮拖到
几分钟）。而平台会在模型一步多调用时用 `asyncio.to_thread` 各起一条线程 —— 撞上就卡。

**修复**：`McpClient` 加一把**可重入锁**（`_gate`），`tools()/call()/read_resource()` 串行执行。
代价几乎为零（Unity 主线程本来就是一个一个执行），换来"不会再有点了没反应"。
选择串行化而不是缩短超时：缩短超时只会把"卡 5 分钟"变成"随机失败"，而这类失败重试也会
继续撞服务器。

**验证**：
- 真游戏实测：修复前 3 并发只有 1 个返回；修复后 4 并发全部 0.2~0.3s 返回；
- 回归测试 `test_parallel_calls_are_serialized`：假服务器记录"同时在飞的请求峰值"，
  断言等于 1；把锁换成 no-op 后该测试立刻失败（峰值 3）——测试确实在测东西；
- 真对话复验：重启 agent 服务后，同一会话里模型一步发的
  `unity_screenshot` + `unity_console`、以及后续两个 `unity_find_objects` **全部正常返回**。

**附带修掉**：`unity_screenshot(save_path="00_x.png")` 这类**相对路径**原先落在平台进程的
cwd（仓库根），而智能体是在 workspace 里找文件 → 白跑一轮。现在相对路径统一按**截图目录**
（`_shots_dir()`，即 workspace/default/unity-auto/screenshots）解析，返回绝对路径；
用例脚本那边 `UNITY_SHOT_DIR` 就是它自己的运行目录，语义不变。

**运维提醒**：agent 服务（`start_server.py`，:5011）没有热重载，改完桥的代码要重启它，
新代码才对"对话里的工具调用"生效（用例脚本是子进程，每次重新 import，不受影响）。

## 13. 让智能体"不勉强"：看全貌 + 按文字找（2026-09-19）

**现象**（用户看出来的）：智能体探索一个中文 RPG 界面时，动作序列是这样的 ——
`TalkUI` → `UI` → `UIRoot` → `Talk` 一个个**猜对象名**（每次一轮 MCP 往返、多数落空），
然后干脆自己写 C# 遍历场景（还编译错一次）；后续又在截图落盘路径上 white 跑两轮。
一段本可以两次调用看清楚的探索，烧了十几轮。

**根因不在模型，在工具面**：只有"按名字/路径/组件查"（名字还是**精确匹配**），
没有任何"看全貌"或"按界面上那句话找"的原语 —— 中文游戏里对象名是拼音/英文，
界面上写的是中文，模型只能靠猜。服务器自带的 `manage_scene get_hierarchy` 只给
对象名与组件名、要按页翻、**没有文本**，对"中文界面找入口"帮助有限。

**补的两个原语**（都是 C# 一次成型，一次往返）：

1. `unity_hierarchy(root="", depth=3, max_nodes=80)` —— （子）树的**路径 / 可见性 /
   组件 / 界面上的文本**。广度优先（截断时先保住上层全貌）；`root` 认名字也认路径
   （含半截路径），`depth` 是**相对 root** 的层数。
2. `unity_find_by_text("背包")` —— 按界面上的字反查：写着这句话的对象 + 它的
   **可点祖先**（uGUI 按钮标签挂在子节点上，这个祖先就是要点的东西）。搜不到
   通常意味着那个界面当前没打开。
3. 顺带把 `subtree_text` 也接到工具面（`unity_object_text`）：读整棵子树的文字，
   而不是容器自己身上那个无关的 id。

`capabilities.py` 的 Unity 领域提示与 `SKILL.md` 的探索流程都改成"**先看树 →
按文字找 → 读面板** → 再操作断言"，并明确"别猜对象名"。Unity 工具数 18 → 21。

**真机验证**（jyx2《群侠传，启动！》，同一时刻的场景）：

- `unity_hierarchy()`：整个场景一次摊开（0.5s），BFS 截断时上层结构完整；
- `unity_hierarchy(root="ChatUIPanel(Clone)", depth=2)`：**一次**给出该面板全貌 ——
  `Content/MainContent` 正显示对白「这里四季花开不败…」、`Name/NameTxt` 是「张云贤」、
  `SelectionPanel`（含 `SelectMenu`/`ControllerNotice`）当前【隐藏】。
  这正是智能体此前用十几轮在找的"选项面板"；
- `unity_find_by_text("选择")`：命中
  `MainCanvas/NormalUI/ChatUIPanel(Clone)/SelectionPanel/ControllerNotice/.../Text (TMP)`
  （文本「确认选择 …」）——一条调用定位到"选项走 Selection 模式"；
- `unity_find_by_text("背包")` / `("关 闭")`：直接给出标签对象与可点祖先
  （`UI/.../BagButton`、`UI/.../CloseBtn`），可见性也一并给出。

单测 537 → **540**（树的解析与渲染、文本搜索的"可点祖先"、子树文本；假服务器加了
`tree-only` / `findtext-only` 两个片段分支）。C# 片段的语义（BFS、相对深度、root 认路径）
在真机上验证 —— 假服务器只能验证平台侧的解析与呈现。

## 14. 视觉核验：能看，但没人让它看（2026-09-19）

**用户观察**：智能体"主动视觉识别很少"，不确定有没有按钮时不截图看看。

**先验事实**（别猜）：视觉链路是通的 —— 把真游戏截图（失败现场那张）喂给 `build_chat_model()`，
它把系统菜单 5 项**逐条读对**（保存游戏/载入游戏/游戏设置/回到主菜单/返回游戏，还指出最后一项
是高亮），并把右上角 `FPS=534.91` 读了出来。平台侧 `DynamicModelSelection` 在消息里出现
`image_url` 时会自动切视觉模型（`VISION_MODEL` 空 → 复用文本模型，而 glm-5.3-flash 本身支持视觉）。
**所以不是"看不见"，是没被引导去看，也没让它便宜地看到。**

**三个具体原因**：

1. `unity_screenshot` 只回**文件路径**；要真看到图还得再 `read_file` 一次 —— 两步成本，
   而且**工具说明里没写这一步**（模型自己摸索时还踩了相对路径落仓库根的坑，glob 两轮）。
2. 提示词与技能把探索定义成"查对象 / 读组件"，没有任何"看不清就截图"的指引；SKILL 早期
   版本里那句"界面上的字、按钮能不能点，都从这里读，**不靠截图猜**"更容易被读成"别用图"。
3. 它把"有没有按钮"当成**检索问题**（找一个对象名），而不是**视觉问题**（看一眼界面）——
   名字查不到就被理解成"没有"，而"运行时克隆 / 名字是拼音 / 根本不是独立对象"都会让检索
   落空，图却一眼就有答案。

**改法**（分工写清楚：**图判断"是不是这样"，文本决定"点哪儿"**）：

- `unity_screenshot` 工具说明重写：写明"想看一眼就紧接着 `read_file` 这个路径"，并列出
  四个该看的场合（不确定有没有入口 / 刚打开面板 / 点了没反应 / 断言失败）；返回值里加
  `hint`（模型未必回头读文档，但一定读工具结果）。
- `capabilities.py` 的 Unity 领域提示 + `SKILL.md` 新增「什么时候该看一眼（视觉核验）」
  一节：两步用法 + 四种场合 + 明确分工。**装配文件里存的是提示词副本，必须同步**
  （见 §13：工具清单与领域提示都来自 `workspace/default/assembly.json`，光改代码不生效）。

**顺带修掉一个会丢数据的隐患**：`messages/sync?prune=true` 在"权威源为空"时会
**删掉本地整段消息**（`if not raw_messages: if prune: delete(...)`）。而权威源为空最常见的原因
就是 **agent 服务重启**（inmem 运行时、检查点不落盘）—— 前端重连结束后照例 prune，用户看到的
就是"聊天记录凭空消失"。改成：**空状态一律跳过 prune**（真要清空走删除接口，有 tombstone），
两条测试钉住（空 → 本地不动；非空 → 照旧按权威源覆盖）。单测 540 → **542**。

**教训（写给以后的自己）**：agent 服务（`start_server.py`）的检查点是**内存态**
（`DATABASE_URI=:memory:` + `LANGGRAPH_RUNTIME_EDITION=inmem`），**重启即丢对话上下文**；
线程列表还在（那份元数据是落盘的），所以"能看到会话"容易被误判成"状态也在"。
重启前先想清楚这一点。

## 15. 右侧「智能体看过的图」面板（2026-09-19 上线 → 2026-09-20 移除）

**已移除**。这段保留记录，免得后来人翻 git 历史猜「为什么有个工作区文件回取的路由」——
它是被删掉的，不是没做完。

**原本的做法**：

- 后端 `GET /api/v2/workspace/file?path=…`（`api/v2/workspace.py`）：只读、限工作区内的
  文件回取。`<img src>` 带不上自定义头所以不签名，靠两条硬约束收口 —— resolve 后必须在
  `settings.workspace_dir` 内、单文件 64MB 上限，越界一律 404。
- 前端 `lib/api/workspaceFiles.ts` 从会话消息里统一收集图片路径（工具参数、结果里的
  `path`、结果 JSON 文本中像图片路径的片段）。
- 前端 `components/WorkspaceImagePanel.tsx`：与 `SubAgentPanel` 同一套布局约定，
  默认停在最新一张、缩略图带、"原图"外链、点击放大；图变多时自动弹出，主列右上角有
  `图片 N` 开关。

**移除原因**：用户反馈这个自动弹出的侧栏「太奇怪了」——它既不请自来（图一变多就自己
展开），又把"智能体读过什么文件"这件本该由工具卡片承载的上下文拎出来单列一栏。移除范围
是整条链路：前端面板 + 收集逻辑 + 后端路由（连同它那两个测试）。想看截图仍然可以走工具
卡片里的路径。

## 16. 用例复位：回到"这条用例从哪儿开始"（2026-09-19）

**用户诉求**：Unity 生成的用例有没有复位功能 —— 把**场景和状态还原到用例开始的状态**？
（回答：之前没有；现在有了。）

**先说清楚能做到哪一步**：复位 = **退 Play → 打开起跑场景 → 再进 Play → 等标志物回来**。
它把内存里的一切清干净（场景对象、DontDestroyOnLoad 的常驻单例、静态缓存、网络会话，
Unity 重新进 Play 会重载脚本域）—— 这正是 Playwright 那边"每条 spec 一个新 context"的
等价物。它**不碰游戏自己的存档/服务器数据**：已经写进存档的进度（升级、任务完成、道具
用掉）不会自己回来，那要连存档一起回滚得用游戏自己的机制（系统菜单的「载入游戏」、
GM 命令、或快照存档文件）。任意"战斗第 3 回合中间"的快照式回档做不到 —— 游戏状态
不是可序列化的通用对象。

**做法**（三层，作者负担为零）：

1. **桥层原语** `Unity.reset(scene=, wait_for=, timeout=, mode=, play=)`
   - `hard`（默认）：stop → （需要时）`manage_scene load` 起跑场景 → play → `wait_for(标志物)`。
     同名场景**不重复打开** —— 脏场景的保存对话框是模态的，一弹出来 MCP 线程就再也动不了。
     顺序也是硬要求：Play 中 Unity 会拒绝打开场景（测试用假服务器把这个约束钉住了）。
   - `soft`：Play 内 `SceneManager.LoadScene` 重载当前场景，几秒钟；静态状态与常驻对象不清，
     换场景直接报错（那是 hard 的事）。
   - 复位记进步骤轨迹（第一行 `reset`，target 就是起跑场景），失败按**环境问题**报（退出码 2），
     不是"用例断言失败"。
2. **用例声明起跑线**：脚本里写模块级常量
   `RESET = {"scene": "…/01_moqiaoshanzhuang.unity", "wait_for": "SystemButton"}`；
   平台在执行前解析它（`ast.literal_eval`，不执行用例代码）、经 `UNITY_RESET_JSON` 交给
   prelude，在**用例动作与开录之前**复位。`RESET = False` = 不复位（链式用例），
   `UNITY_RESET=0` 全局关。
3. **跑通一次就记住**：prelude 在复位后、用例动作前写一份候选起跑线
   （`start_state.candidate.json`），**只有跑通（exit 0）才提升**成 `start_state.json`
   （场景 + 轨迹里第一个成功的 `wait_for` 当标志物）。下一轮没写 RESET 的老用例自动用上它 ——
   "先手动打开某场景再进 Play"这类注释里的前置，从此不用人做。

**验证**（jynew《群侠传，启动！》5.3GB 真游戏，场景 `01_moqiaoshanzhuang`，标志物 HUD「系统」按钮）：

- 先把现场弄脏（打开背包面板）→ 用**声明了 RESET** 的用例跑：`复位 -> 起跑线：场景=…标志物=SystemButton 用时=7.5s`，
  背包没了、HUD 文本正确、用例 **PASS**（HUD/系统菜单/背包 全绿）。
- 再跑**没写 RESET** 的同一份用例（用记住的起跑线）：自动复位 7.4s → **PASS**；
  连跑两轮都 PASS，每轮都带 `run.mp4`（16 帧 / 6.8s，h264 1736x1064）。

**顺带修掉的两个"偶发红"**（都在验证过程中现形）：

- **`object_text` 把数字当文本**：`GraphicRaycaster` 的 LayerMask 序列化成 `{"value": 1023799}`，
  被当成"对象自己的文本"收走，于是 jynew 系统菜单的文本读出来是 `1023799 1023799`，
  断言永远不成立。现在只收**字符串**（数字的可见文本本来就在渲染出来的那份里）。
- **录像合不出来**：Game View 被拖成了 1737x1065（宽高都是奇数），h264 的 yuv420p 要求偶数，
  整段录像 `Could not open encoder before EOF`。合成命令加了
  `scale=trunc(iw/2)*2:trunc(ih/2)*2`，并顺手不留 0 字节的 mp4 冒充产物。
- 另外把**平台自己造成的 Console 噪声**（`CaptureScreenshotAsTexture() failed…` —— 进 Play
  头几帧还没有"上一帧"可截，Unity 内部打的日志，调用方 catch 不到）从 Console 读取里滤掉：
  它会让用例里"无新增报错"的断言把平台噪声当成游戏的新报错，表现是偶发红且查不出原因。

单测 544 → **559**；技能 `unity-ui-test` 增「起跑线与复位」一节并在 API 表里加了
`u.reset` / `u.active_scene` / `u.load_scene`；能力目录（`assembly.json`）同步加了
`unity_reset` 工具与相应提示词。

## 17. Unity 用例的删除（2026-09-19）

**用户诉求**：Unity 自动化页面要能删掉旧脚本。

**做法**（与 Web-UI 自动化那套删除同构，但多清一层）：

- `DELETE /api/v2/unity-auto/scripts/{script_id}` → `unity_service.delete_script`：
  执行记录、脚本行、**磁盘上的产物**（每次运行的截图/录像/轨迹 + `start_state.json` 起跑线）
  一起清，并回报"清掉了多少"（`runs` / `files` / `bytes`），前端把它做成 toast。
  只删库不删盘会留下永远没人认领的运行目录 —— 一次执行就是几张截图加一段录像
  （jynew 一次 ~1 MB，大型游戏更多），而点"删除"的人期待的就是它彻底没了。
- **只动 `unity-auto/<script_id>/` 这一层**：共享的 `unity-auto/screenshots/`（探索时截图落的地方，
  不属于任何一条用例）不动，软链不跟（删链接不删目标）——两条都有测试钉住。
- **正在执行的删不掉（409）**：后台任务还在往回写、产物还在生成。判断口径与"运行中卡太久"
  共用（`unity_service.run_stale_after_s()` = 执行预算 + 180s，两面读**同一个函数**），
  所以进程被杀留下的僵死 running 不会让脚本永远删不掉；预算调大后这个阈值跟着动。
- 前端：行内垃圾桶按钮 + `AlertDialog` 二次确认（说明会连执行记录与产物一起删、不可恢复），
  删除中禁用按钮，失败时把后端那句话原样提示（比如"正在执行中"）。
  `apiClient.delete` 顺手改成可指定返回类型（默认仍是 `MessageResponse`）。

**验证**（浏览器实测 + 接口实测）：临时建一条用例跑一次 → 页面点垃圾桶 → 确认框
「删除「【临时】删除功能验证」？」→ 删除 → 该行消失、其他行（含 jynew 那条 v4）不受影响、
toast 显示 `已删除：0 条执行记录 + 6 个产物文件，0.9 MB`；磁盘上该脚本的目录消失、
共享截图目录 18 个文件完好、jynew 的 `start_state.json` 起跑线完好。
单测 559 → **563**；前端 `tsc` 干净、vitest 34 项通过。

## 18. 两个"看起来像界面坏了"的问题（2026-09-19）

用户看着 Unity 自动化页面上一条**从没跑过**的用例问"为什么状态叫运行中"。查下去是两件事：

**1）标签撞词（已修）**：`STATUS_MAP` 是张全局登记表，`active`（用例状态：跑通过一次=可用）
与 `running`（运行态）都写成「运行中」。于是一条刚入库、零执行记录的用例顶着"运行中"，
只会让人以为界面坏了。改成 `active: 可用`（绿色）—— `active` 在平台里只由**脚本/用例**
产生（api-auto / web-ui / unity 三处一致，运行态另用 `running`），所以这条改动全局正确。

**2）智能体跑的用例不进执行历史（待定）**：聊天里的智能体用 `unity_run_script` 跑验证，
走的是同步服务调用，**不写 `UnityScriptRun` 行**（只有页面「执行」/ REST 那个路径会先建记录
再入队）。结果：磁盘上证据齐全（那条新手流程用例 193845 那次有 4 张截图 + `run.mp4` +
`steps.jsonl`，跑通了），页面上却是"0 次执行"。`triggered_by` 字段本来就是为这种区分留的
（现在固定 "manual"）。修法清楚，等一句话就动手。

**3）顺带修掉一个真实缺口：起跑线学不到（已修）**。原来只在 prelude 里、**用例动作之前**
拍一次快照 —— 对"用例自己 `u.play()`"的写法（智能体爱这么写：进 Play、等登录窗、建角…）
拍到的是"还没进 Play"，什么都记不到，于是**跑通之后起跑线仍是空的，下一轮就不会复位**。
现在改成在**"等到起跑线标志物"的那一瞬间**记（`Unity._snapshot_start_line`），并且加两条
护栏：只在**用例第一个动作就是等待**时记（中途的等待是等某个面板，记下来是半路状态，
比不记更糟）、只在真的在 Play Mode 且能读到场景时记。三条都有测试钉住。
单测 563 → **566**。

## 19. 执行详情的弹窗适配（2026-09-19）

用户截图报的：Unity 自动化页打开一次失败的运行详情 →「原始输出」里那些**超长的绝对路径
（`/Users/…/20260919_194433_群侠传…/case.py`）把卡片顶宽了**，正文画到卡片外面、盖住页面背景。

**根因**（两个叠在一起，都是一句话就能说清的老坑）：

1. `DialogContent` 是 `grid`，grid item 默认 `min-width: auto` —— 里面出现不可断行的长内容时，
   子项会撑到自己的 min-content 宽（比卡片还宽），而卡片没有 `overflow: hidden`，于是**画到外面**。
2. 输出用的 `<pre>` 虽然写了 `overflow-auto`，但它的宽度由父链决定（父链已经按 min-content 撑开了），
   滚动条根本没机会出现。

**改法**：执行详情的两条链路（Unity / Web-UI 各一个 RunDetail）加 `min-w-0`（flex 列 + 滚动容器）、
`DialogContent` 加 `overflow-hidden`；「原始输出」的 `<pre>` 改成 `whitespace-pre-wrap break-words`
（日志/堆栈按行折行读起来比横向滚动舒服，也彻底消掉横向溢出）。失败原因、单条用例的 stdout
等几处 `<pre>` 一并统一。

**顺带发现的同级问题**：`DialogContent` 的默认宽度带 `sm:max-w-sm`（384px），而调用方里有一批只写
`max-w-3xl` —— **基础值打不过带 `sm:` 前缀的值**，于是这些弹窗在桌面上被卡成 384px
（实测：Unity 页的「新建脚本」「执行历史」、代码图谱的详情、接口自动化的大弹窗）。按其余 20 处
调用方的写法补成 `sm:max-w-3xl` / `sm:max-w-4xl`。

**验证**（浏览器实测 1280 视口）：修复后运行详情弹窗宽 1024、「原始输出」面板 992 且完全在卡片内
（`pre.right ≤ dialog.right`）、不再需要横向滚动（`scrollWidth == clientWidth`，长路径正常折行）；
「执行历史」弹窗从 384 变成 768。前端 `tsc` 干净、vitest 34 项通过。

## 20. 执行过程要能"看见"（2026-09-19）

用户报："跑完了详情里还显示运行中"，且执行期间什么都看不到（一直 0 步 0 图 耗时 -），
"不能实时给展示信息"。

**两个原因，各自独立**：

1. **执行中的记录在页面上永远是初始态**：产物清单（`screenshots`）要到跑完才写回数据库，
   而详情页的步骤/截图/录像全靠它 —— 于是整个执行期间都是"0 步 / 0 图 / 耗时 -"，那句
   "轨迹实时刷新"是假的。**改法**：运行目录**入队前就定好并落库**（`unity_script_runs`
   新增 `workdir` 列 + `init_db` 轻量迁移），执行期间直接读那个目录里现存的
   `steps.jsonl` 与产物（文件的落盘是即时的）。跑完仍然以 `screenshots` 那份清单为准
   （它才带"文件被清理"的事实）。顺带给在跑的记录一个 `elapsed_ms`，详情页显示
   "已进行 42s"而不是看不出死活的 "-"。
2. **轮询在页面不可见时会暂停**：SWR 的默认行为（`refreshWhenHidden: false`）。而这个页面
   常常在后台 —— 人在聊天页看智能体、或切到别的窗口等结果，回来时看到的就是暂停那一刻的
   "运行中"。**改法**：执行记录与执行历史两个 hook 都加 `refreshWhenHidden: true` +
   `revalidateOnFocus`，历史列表也在有执行在跑时按 3s 轮询（状态自己会变，不用手动刷新）。

**验证**（真机 + 真浏览器）：

- 后端抽样（同一次执行，每 12s 一问）：步骤 `2 → 10 → 14 → 27 → 36`、产物 `2 → 5`、
  `elapsed_ms` `13s → 73s` —— 执行期间就能看到进度在长；
- 前端（浏览器里执行中打开详情）：标题"运行中 / 执行中…（轨迹实时刷新）"、统计
  "步骤 36 / 截图 3 / 已进行 81s"，9 秒后再读变成"已进行 92s"（轮询真的在跑）；
- 跑完自动翻成"通过 / 步骤 37 / 截图 4 / 录像有 / 耗时 97.0s / 退出码 0" ——
  不用手动刷新，也不会再停在"运行中"。

单测 566 → **568**（新增：执行中的记录从运行目录现读步骤与产物；REST 入队把运行目录
落库并把同一条目录传给执行）。

## 21. 知识库：一库一实例、设置页搬进 LightRAG 界面、平台侧只做展示（2026-09-20）

用户提的三件事：① 把 RAG 相关配置挪到 **LightRAG 自带界面**里的设置页；② 两个完全不同的
项目不能挤在一个环境里，"我记得官方支持"；③ 平台知识库页去掉入库、把展示做强。

### 官方到底支持什么（先说结论，因为它决定了做法）

翻的是**装在本机的 lightrag-hku 1.5.7 源码 + 它自己的 OpenAPI**：

- `GET /openapi.json` 的 **0 个请求模型带 workspace 字段** —— `/query`、`/documents/*`、
  `/graph/*` 都没有"按请求切库"这回事；
- `--workspace`（env `WORKSPACE`）的 help 是 "Default workspace for all storage"，
  启动时定死；文件类存储统一按 `working_dir/[<workspace>/]<文件>` 落盘
  （`json_kv_impl` / `json_doc_status_impl` / `networkx_impl` 三个实现都是这个约定），
  上传文件的暂存目录同理（`inputs/<workspace>/`）；
- 源码里那句 "Not user-configurable … See docs/MultiSiteDeployment.md" 说明了官方的多站点
  做法：**一个站点一个实例**。

所以**隔离单位是进程，不是参数**。平台的适配就落在这：一个知识库 = 一个 lightrag-server
实例 + 一个 workspace + 一个端口，清单写在 `workspace/<space>/rag_kbs.json`
（`services/rag_kbs.py`，与 `assembly.json` 同级的"文件即事实源"）。所有实例共用
`LIGHTRAG_WORKING_DIR`，各自的 workspace 天然分家
（`workspace/default/rag/ruoyi/…`）。默认库的 workspace 是**空串**——那是 LightRAG 的全局
命名空间，也是升级前的样子，老数据一个字节没动。

启动器的服务表因此改成**现算**：`_default_services()` 每次按注册表生成
（`lightrag` + `lightrag-<key>`），所以新增一个库不需要重启控制台；
`POST /api/services/{name}/{action}` 对没摸过的新库也能直接操作。

### 设置页为什么"贴"进它的界面（而不是改它的界面）

LightRAG 的 WebUI 是打包好的静态产物（挂载目录写死、`default_headers` 也写死），既没有
设置页、也没有改配置的 API —— LLM / Embedding 全是启动环境变量。所以：

- 页面本体在 `tools/lightrag-ui/`（纯 HTML/CSS/JS，无构建步骤），
  **启动器每次拉起知识库时**把它同步进 `lightrag/api/webui/`，并往 `index.html` 注入一个
  「⚙ RAG 设置」入口按钮（标记包裹、幂等；升级/重装 LightRAG 后自动长回来）；
- 页面数据全走平台后端（`GET/PUT /api/v2/rag/settings`、`PUT /api/v2/rag/kbs`）——
  `.env` 与注册表的事实源在平台这边，改完点「保存并重启」由启动器把实例带新配置拉起来；
- 静态资源带内容指纹（`rag-settings.js?v=<md5>`）：页面文件名固定，否则改完 overlay
  浏览器会用旧 JS（实测踩过，报成"读不到平台配置：Cannot set properties of null"）。

平台设置页里那四项 LightRAG 字段随之删掉，登记进 `test_wiring` 的 `ui_elsewhere`
（"入口在哪儿"这件事必须是显式的）。

### 平台知识库页：去掉入库、把展示做厚

入库/删除/重新解析/图谱编辑都回 LightRAG 界面做（页面直接给地址），平台只留**看**与
**服务控制**：库切换（`?kb=`）、文档状态计数、图谱规模（实体/关系，取样并标注截断）、
管道状态、存储后端、LLM/Embedding 与工作目录、文档表格（状态筛选 + 分页）。
`POST /rag/ingest-{text,file}` 两个路由连卡片一起删掉——智能体的 `rag_*` 工具走的是同一个
service 层，不受影响；工具侧反而多了一个 `kb` 参数和 `rag_list_kbs`（6 个工具）。

### 三条"跑起来才发现"的故障（都已修）

1. **LLM 绑定写死成 `api.deepseek.com` + 别家的 key**：入库必 401
   （`Authentication Fails, Your api key: ****Ryrh`）。知识库当时是空的，所以一直没人发现。
   现在 `LIGHTRAG_LLM_BASE_URL/MODEL/API_KEY` 三项优先、留空回退平台主模型。
2. **上游网关要额外请求头**：平台主模型在 `opencode.ai/zen/go/v1`，缺 `x-opencode-session`
   直接 400（MissingSessionID）。LightRAG 加不了头（`default_headers` 写死），于是控制台
   加了一个**只接受 127.0.0.1** 的代转端点（`/api/llm/...`，流式透传，
   `content-encoding` 必须原样带走——否则客户端拿 gzip 字节去 utf-8 解码）。
3. **本机 MLX embedding 服务（:7997）没起**：`~/Documents/eval-platform/rag/mlx-models`
   的 `./start.sh` 起来后才有可能入库（Mac 重启后需手动启）。它不在本仓库里，属于外部依赖，
   但"RAG 不可用"的第一现场就在这里，记一笔。

### 验证（真服务 + 真浏览器）

- **入库→检索闭环**：文本入库 → `processing` 96 秒后 `processed` → hybrid 检索答出
  "连续输错密码 5 次锁定账号 10 分钟" 并带 `smoke-test-rag.md` 出处；图谱 15 实体 / 24 关系。
- **隔离**：临时建第二个库（:5021，workspace `smoke2`）入库"帮派贡献上限 10000"。
  默认库问群侠传的问题 → "资料中并未包含"；smoke2 问若依的问题 → "I don't have enough
  information"。两边文档列表彼此不可见。验证后已删文档、停实例、清 LLM 缓存、
  注册表恢复成单库（数据目录与日志一并清掉）。
- **界面**（浏览器实测）：LightRAG 的 WebUI 右下角出现「⚙ RAG 设置」，进去能看到知识库
  表格（key/名称/端口/数据目录/在线状态/起停）、LLM 与 Embedding 表单（密钥蒙版、
  "留空跟随主模型"显示生效值）；平台 `/rag` 页无入库卡片，展示与检索测试正常。
- 全量单测 **584 通过**（新增 11 条：注册表 9 条 + 工具/熔断 2 条；`test_wiring` 的
  "注册表服务名 → 启动器"那条改成直接问启动器要服务表，因为服务名现在是现算的）。

## 22. 两件事：录像钩子把 Unity 拖崩了 + 平台不再做复位（2026-09-22）

**用户诉求**（连着两问）："为什么复位后 Unity 直接崩溃了？" → "看一下为什么又崩了，
我这次在线呀" → "我想了想，完全去除复位功能吧，需要复位的时候提醒用户要执行复位操作
然后告诉用户需要复位的场景是什么，保存的 Unity 用例也加一个标注告诉用户复位的场景"。

### 22.1 崩溃：不是复位，是我们自己的录像钩子

两次崩溃的编辑器日志最后一句都是
`Failed to present D3D11 swapchain due to device reset/removed ... unrecoverable error and
the editor will shut down`（GPU 设备丢失，不是脚本/资源/Lua 错误）。第一次（16:30）能对上
系统日志：16:22:15 进「新型待机」（Idle Timeout）→ 16:30:07 鼠标唤醒 → 16:30:18 `dwm.exe`
崩在 `dwmcore.dll` → Unity 设备丢失。第二次（16:59）用户在线、无待机、无 dwm 崩溃，
但那份 28 分钟的会话日志里 **11532 次** `CaptureScreenshotAsTexture() failed` ——
全是我们的逐帧录像钩子（栈是 `MCPDynamicCode/<Execute>…<>m__0 ()` ← `EditorApplication.update`）。

钩子为什么会一直刷：**保险只数成功的帧**（`__n` 只在写盘成功后 +1），截图一直被拒时
帧数永远是 0，`max_frames` 永远不触发；而用例被平台 420s 超时**硬杀**时 runner 的
`atexit` 不执行 → `record_stop()` 没发出 → 钩子留在编辑器里以 6fps 一直截图（那台工程
Screen 报 1080x1920、Game View 只有 1754x1299，逐帧截图次次被拒，实测四轮录像 0 帧）。
一轮超时漏一个钩子，几轮下来同时好几个 —— GPU 就是这么被拖垮的。

**修法**（三处，都在"让钩子不可能无人值守地活着"）：

1. 编辑器侧熔断（`cs_record_start`）：尝试次数上限（4× 帧数）+ **连续失败 20 次自动退订**
   并把原因写进 SessionState；`cs_record_stop` 回传原因，运行输出里能看到"录像提前结束 ——
   逐帧截图连续失败 20 次：…"。
2. 挂钩子前**先试一帧**（`_CS_CAPTURE_PROBE`）：截不到就不挂，直接告诉用例"录像不可用 +
   为什么"，而不是挂上去白刷几万次。
3. 平台兜底收尾（`unity_service._salvage_recording`）：runner 留一个 `.recording` 标记，
   被超时杀掉时父进程补发一次 `record_stop`（顺带把已采到的帧合成录像）。
4. 顺带：跑用例期间用 `SetThreadExecutionState` **禁止系统睡眠** —— 待机唤醒本身就是
   一手"设备丢失"。

## 22bis. 域重载卡死编辑器 + D3D11 设备丢失（2026-09-23 凌晨，整机断电级）

**用户诉求**："平台智能体跑自动化脚本的过程中我把会话中断了，但 Unity 好像还在被驱动，
然后 GPU 崩溃、界面全卡死，只能重启电脑" → "找到根本原因" → "全部修改，不要再出现这么
严重的问题"。

### 22bis.1 现场（全部来自日志，不是推测）

- `Editor-prev.log` 最后一行是 `Begin MonoManager ReloadAssembly`（卡在域重载里），
  它的前两行是 `RefreshV2(ForceUpdate)` 与 `[ScriptCompilation] Requested script
  compilation because: Requested through public api`；`Editor.log`（01:38:15 用户重启的
  那次会话）最后是 44 行 `d3d11: failed to create buffer ... [0x887A0005]`
  （`0x887A0005` = DXGI_ERROR_DEVICE_REMOVED）。
- `logs/unity-mcp.log`：**01:37:50** `refresh_unity: Connection lost during compile
  (expected - domain reload triggered)` → 60s 后 `Timed out after 60s waiting for
  editor to become ready` → 之后 `No Unity plugin reconnected within 20.00s` 刷了 17 次
  （插件再没回来）。当刻有一次 adhoc 用例运行在飞（`unity-auto/adhoc/20260923_013731_adhoc`，
  steps.jsonl 为空）。
- 系统日志：01:43:09 未正常关机 + Kernel-Power 41；**没有** TDR(4101)、**没有** Unity
  crash dump —— 整机卡死后被强制断电，不是驱动报错重启。

### 22bis.2 根因：我们自己注入的 prelude 踩了"会被桥重编译"的工具

链条（每一环都有源码/日志证据）：

1. 平台给每次用例执行注入的 prelude 里，"记起跑线"那段调了 `u.active_scene()`
   → 桥的 `_OP_TOOLS["scene"]` → **`manage_scene`**。
2. `manage_scene` 在桥内部带 `preflight(refresh_if_dirty=True)`：工程被判"有未导入的
   外部改动"（`external_changes_dirty`，一个 **latch**）时，**桥自己**会发
   `refresh_unity(mode="if_dirty", scope="all", compile="request", wait_for_ready=True)`
   （`services/tools/preflight.py`），插件落地就是 `AssetDatabase.Refresh(ForceUpdate|
   ForceSynchronousImport)` + `CompilationPipeline.RequestScriptCompilation()`
   （`MCPForUnity/Editor/Tools/RefreshUnity.cs`）——**注意 `if_dirty` 在插件里等同 force**。
3. 平台的护栏（那 8 个闸内工具、脏就拒发）本身是有的，但脏检查是 **5 秒缓存 + 读失败即
   放行**：缓存里还是"干净"、或被放行的那一刻刚变脏，这一记就漏过去了。
4. 于是一次**强制同步刷新 + 请求重编译**落在 **Play Mode** 里 = 域重载 →
   编辑器卡在 Reloading Domain；插件 WebSocket 1005 掉线后再没重连；GPU 设备随后被移除。
5. "中断了还在被驱动"：平台的停止是**检查点式取消**，已经在飞的工具调用不会被抢占；
   用例跑在独立子进程（`run_unity_script` → `sys.executable case.py`）里、自己连桥，
   命令发出去就照样执行（中断后仍有 01:46/01:49/01:50 三次运行，最后一次真的点了 Unity）。
   另外 runner 被**硬杀**时子进程 atexit 不执行，而收尾只写在 `except TimeoutError` 分支
   （`asyncio.CancelledError` 分支以前漏了）—— 这正是 09-22 那版钩子残留的同一个洞。

### 22bis.3 修法

**A. 让"桥替我们重编译"这件事不可能发生**

1. 闸门改**严格**（`unity_bridge._gate_state` + `_refuse_if_project_dirty`）：代发那 8 个
   工具前**不吃缓存地**读一次状态；读不到 → **拒绝**（fail-closed，以前是放行）；
   脏 + Play → 拒绝并明说"Play 中重载会毁掉这一局、实测卡死编辑器"。
   （问都问不了的方言 —— 平台没有它的状态资源模板 —— 才按"不脏"放行，否则换服务器即不可用。）
2. **读路径不许有写风险**：prelude 的起跑线快照改走新增的 `u.active_scene_path()`
   （execute_code），不再碰 `manage_scene`。
3. 脏标记的清理有了专用安全通道 `unity_sync_assets`
   （`refresh_unity(compile="none", wait_for_ready=False)`：只刷新、不重编译、不 pump
   PlayerLoop）：**仅非 Play 可用**，清完再读一次状态如实回报。agent 工具
   `unity_sync_assets` + REST `POST /unity-auto/sync-assets` + `/unity-auto` 页按钮。
   拒绝文案里写清"Ctrl+R 清不掉这个 latch"，不再让用户白刷。
4. `unity_status` 增加 `editor_stale` / `can_run_gated_tools` / `advice`：编辑器正在重载
   或掉线时如实说出来，而不是只报一句"未连接"让人瞎试。

**B. 中断/异常路径都要能把编辑器拉回干净状态**

5. `run_unity_script` 的 `except asyncio.CancelledError` 分支补 `_salvage_recording`
   （用 `asyncio.shield` 保证收尾跑完）——中断与超时一视同仁。
6. 新增急停：`unity_service.stop_all_runs()`（取消所有在跑的用例 + 卸掉帧录像/手动录制
   两个钩子）+ agent 工具 `unity_emergency_stop` + `POST /unity-auto/stop-all` + 页面按钮。
7. 帧钩子再加两道保险：**墙上时钟上限**（= 执行预算，见第 9 条）与**退出 Play 自动退订**
   （挂钩子时在 Play 才管这条）；fps 从 6 调成 **5**（看清交互，写盘/GPU 回读只有
   10fps 的一半）。
8. 编辑器侧截图不再有"永久改道"（同日按用户口径改回，见 22bis.4）：主路径换成文件版
   `ScreenCapture.CaptureScreenshot(path)`，每次调用都从最好的路开始试，连败只在**当次**
   留一句说明。原先"连败 2 次就永久改道相机截图"的代价是：一次瞬时失败（切场景、
   刚重编译）就把这条路封死到会话结束，而 Play 下截图必须**一直可用**。
9. **执行预算变成一等设置**（同日追加，用户要求"改成 1800s、帧数 5"）：单次执行的墙钟
   预算从"裸 `os.environ` 读一次（默认 420s）"改成 `settings.unity_run_timeout_s`
   （默认 **1800s**，`.env` 的 `UNITY_RUN_TIMEOUT_S`，两条执行路径都读得到 —— 裸 env 只有
   langgraph 进程 load_dotenv 进过 `os.environ`，FastAPI 读不到，这是上个版本埋的坑）。
   **三处常量一起联动**，不再各写一套：僵死判定 `run_stale_after_s()` = 预算 + 180s
   （以前硬编码 600，预算一放到 30 分钟就会把正在跑的记录标成"僵死"还能删）；
   录像上限 `record_budget(fps)` = fps × 预算（以前写死 300s，长流程的录像会莫名少半段）。

回归：`tests/test_unity_reload_guard.py`（闸门三态 + sync_assets 契约）、
`tests/test_unity_recording.py::TestReloadSafetyGuards`（prelude 不许调 `u.active_scene()`、
10fps 默认值、钩子三道保险、中断走 salvage、急停取消 + 卸钩子）。

### 22bis.4 「Play 下截图一直可用」+ 探索打转必须截图 + 显卡设备丢失熔断（同日 11:00）

用户口径两条：「**Play 的情况下截图要一直可用**」「模型遇到问题的纯探索没有结论的情况下，
要**进行截图判断，不要硬找**」。加上当天上午第二次死机（10:26 D3D11 设备丢失 → 10:31 长按
电源；10:38 又一次 → 10:40 BSOD `0x1E`），平台侧又补了三件事。

**A. 截图路径（`unity_bridge._capture_overlay`）**

1. 主路径换**文件版** `ScreenCapture.CaptureScreenshot(path)`：实测（1080x1920 的移动端工程）
   `CaptureScreenshotAsTexture()` 从 `EditorApplication.update` 里调**直接返回 null** ——
   旧文案"录像不可用：ERROR: CaptureScreenshotAsTexture 返回 null"就是这么来的，
   于是"截一张看一眼"这条最该好用的路整个失效。文件版由 Unity 自己排到 end-of-frame 写，
   从哪儿调都能出图，**也不需要场景里有相机**，Overlay UI 照收（实测 1MB PNG，剧情页
   血条/按钮/文字全在）。落盘是"下一帧才写"，所以判据是"文件存在且大小连续两次一样"。
2. **去掉永久熔断**：`_overlay_state` 不再有 `off`；连败只在结果里留一句 `note`，
   下一次照样从文件版开始。截图是低频动作，重试代价只是一次往返；"永久改道"的代价是
   截不到图到会话结束。
3. 编辑模式下失败给**可执行的**报错（`_translate_shot_error`）：Unity 原话
   "No camera found in the scene…" 翻译成"编辑器现在**不在 Play**（没有帧可截），
   而这个场景编辑模式下也没有相机 → 要么让用户点 Play，要么改用
   `unity_hierarchy` / `unity_find_by_text` / `unity_object_text` 读结构"，并明说
   **别反复重试截图**。（顺带纠一个当时的误判：那句报错与 `manage_camera` 是否被闸门拦住无关，
   `manage_camera` 本来就不在那 8 个带 preflight 的工具里。）

**B. 探索打转 → 先截图（新中间件 `exploration_nudge`）**

`ExplorationNudgeMiddleware` 数"连续多少个 Unity 探索类工具调用没有截图"（默认 8，
`AGENT_EXPLORE_NUDGE_AFTER`）：到点就在消息末尾追加一条系统提醒（截图看现场 / 图看不了就
把路径交给用户 / 然后给结论），**每 8 次重复一次**，出现人工消息或截图即复位。
与视觉门（`vision_gate`）配合：读不了图的模型会拿到一段占位符，里面写明"把 path 贴给用户，
别假装看过图"。工具文档（`unity_screenshot`）与技能（`unity-ui-test/SKILL.md`）同步了
"Play 才有画面 / 连续探索 8 次先截图 / 读不了图就交给用户"三条。

**C. 显卡设备丢失熔断（`unity_bridge` GPU alarm）**

第二次死机的现场**不是平台造成的**，但暴露了平台缺一条"停手"通道：

- 时间线：10:25:56 那次会话的 run 正常结束（`run_exec_ms` 1071s，Background run succeeded）
  → 10:26:10 游戏退 Play 时 Unity 报 **85 条**
  `D3D11: Failed to create RenderTexture (828 x 1472 …)，error 0x887a0005` 紧跟
  `Failed to present D3D11 swapchain due to device reset/removed … the editor will shut down`
  → 10:29:23 整个 Python 侧报 `OSError [WinError 10055]`（系统 socket 缓冲区耗尽）
  → 10:31:12 `Kernel-Power 41`（`LongPowerButtonPressDetected=true`，就是长按电源）
  → 10:34 Unity 重新起来 → 10:38 又死 → 10:40:22 `Kernel-Power 41` 带
  **`BugcheckCode=30`（0x1E KMODE_EXCEPTION_NOT_HANDLED，P1=0xC0000005 访问违例）**。
  **后一次 BSOD 时平台进程根本没在运行**（服务全在前一次重启后停着，Unity 还在启动阶段）。
- 硬件侧证据（`Get-WinEvent`，不是推测）：`WHEA-Logger 17`「已更正的硬件错误 / PCI Express
  Advanced Error Reporting」累计 **738 条，最早 2025-01-27**（19 个月前），出错的设备是
  `PCI\VEN_10DE&DEV_2786` = **RTX 4070 及其音频功能**；每次死机前后都有三连条。
  `Display 4101`（TDR）全天历史 **0 条**。机器上还装着三个虚拟显示适配器（ToDesk /
  GameViewer / MuMu）与 Intel 核显，NVIDIA 驱动是 2025-02 的 572.42。
  → 倾向**硬件/驱动级**（GPU 的 PCIe 链路或供电），不是任何一次工具调用能修好的东西。
- 平台侧所以做的是"**停手 + 喊出来**"：`_GPU_LOSS_MARKS`（`0x887a0005` /
  `dxgi_error_device_removed` / `device reset/removed` / `failed to present d3d11 swapchain` /
  `d3d11: failed to create`）扫描所有工具结果与异常文本 → 置熔断 →
  ① `_guard_call` **一律拒绝**后续调用（急停/卸钩子/同步资源三条不收影响，它们不走这条漏斗）；
  ② `record_start` 直接拒（不再往坏显卡上挂每帧截图的钩子）、`run_unity_script` 不开局
  （返回 `environment` 失败，压根不落 `case.py`）；③ `unity_status` 报
  `gpu_device_lost` + `gpu_evidence` + 置顶的 `advice`，`/unity-auto` 页出红色卡片 +
  急停/解除按钮（`POST /unity-auto/clear-gpu-alarm`）。
  熔断**会在检测到新的 Unity 实例时自动解除**（判据是实例指纹变化，不是"过了多久"；
  读不到实例时保持熔断），另有手动解除兜底。

回归：`tests/test_unity_gpu_alarm.py`（16 条：签名识别 / base64 大块里也能找到 /
熔断后底层函数一次都不被调用 / 结果与异常两条置位路径 / 换实例自动解除 / 读不到实例保持熔断 /
录像与开局被拦 / 状态页与手动解除 / 截图主路径不含被插件安检拦下的 API）、
`tests/test_exploration_nudge.py`（6 条）。

**D. 顺带挖出来的真 bug：录像链路从探针到钩子全是坏的（同日 11:35 实测）**

用户看到的那句 `录像不可用：ERROR: CaptureScreenshotAsTexture 返回 null` 不是偶发 ——
**逐帧录像在这台工程上从来没成功过**，因为探针和帧钩子都用了
`ScreenCapture.CaptureScreenshotAsTexture()`：

- 实测（Unity 2022.3.23f1c1 + 该工程，Play 中）：从 `execute_code` 调 → `NULL`；
  从 `EditorApplication.update` 钩子调 → **也是 `NULL`**（第 3 帧再试仍是）。那个 API
  只能在 end-of-frame 调，而插件的命令队列与帧回调都不是。
- 对照实测：同一钩子里 `ScreenCapture.CaptureScreenshot(path)` **成功落盘 1 157 745 字节**。
- 所以：`record_start` 的试拍永远失败 → 用例每次都收到"录像不可用"（被 prelude 吞成
  一行 WARN，用例照样判过，于是没人发现）；就算绕过探针，钩子也会每帧抛异常、
  连续失败到自熔断。

改法（全部走文件版，且顺手把"请求/落盘隔一拍"当成正式契约）：

1. 探针改成**两步**：`_CS_CAPTURE_PROBE_ARM` 挂一次性钩子试拍 → `_CS_CAPTURE_PROBE_READ`
   读 `SessionState` 里的结果；`probe_capture_ok()` 每 0.4s 问一次、最多 12 次。
   钩子**给足 ~180 帧（约 3 秒）的耐心**再判死 —— `CaptureScreenshot` 是异步的，
   只给一两帧的耐心会让录像是"有时能开始、有时报不可用"（第一版实测踩到）。
2. 帧钩子改成：**每一拍先验收上一拍请求的那一帧**（文件存在且非空 → 帧数 +1、失败清零），
   同时用文件版请求下一帧。帧率不降（验收与请求在同一拍），且不再有"每帧抛异常"。
3. 帧文件从 `f_%05d.jpg` 变 `f_%05d.png`：`_frames_in` 两代都认，`stitch_video` 的
   `-i f_%05d<扩展名>` 跟着实际帧走（老录像重合成不会读一半就断）。
4. `cs_record_stop` 只在**钩子自己退订**过时才回 `reason`：平台主动停的那次，钩子最后
   发出的一帧还没来得及验收，残留的"连续失败 1 次"会盖在一段正常录像上报成
   `WARN: 录像提前结束`（实测 44 帧 / 10.8s 的正常录像被这么播过）。
5. 截图主路径里那句"先删同名文件"（`System.IO.File.Delete`）撞上插件安检的
   `Blocked pattern`：整段代码被原样拒绝，于是每次都静默退到**相机截图**（看不见
   Overlay UI），而 note 里只看得到 texture 版那句 null —— 现在改成"毫秒 + Guid 命名、
   不做任何删除"，并且**两条路的错误都报出来**（`_capture_overlay` 的 `errors` 列表）。

端到端实测（Play 中，平台自检用例）：`录像已开始 -> …/rec_20260923_113649`、
`录像 -> …/run.mp4 (18 帧 / 3.4s)`，连跑两次稳定；截图 3/3 走编辑器侧文件版
（1080x1920、约 0.4s、含 Overlay UI 的游戏界面）。

### 22.2 复位：从"平台自动做"改成"人做、平台只检查"

复位是**改被测对象状态**的动作：做了之后没人分得清"游戏本来就这样"还是"平台点成这样"，
而且自动复位会让失败多出一类说不清的理由。现在：

- **平台侧**：`Unity.reset` / `_reset_lua` / `_CS_LUA_INJECT` / `_CS_RELOAD_SCENE` /
  `unity_service.reset` 全部删除；`unity_reset` 工具换成只读的 `unity_start_line`
  （看当前在不在起跑线，不在就把 `instruction` 给用户）；设置页的「Lua 复位入口 / 复位代码」
  两个字段一并删除（它们只服务于复位）。
- **执行时**：prelude 只在输出里打**一行提示**（"这条用例要求从哪个场景/界面开始；平台
  不复位、不检查，请自行确认"），然后照常往下跑 —— 第一版是"不在起跑线就 exit 3 /
  `needs_reset` 拦下来"，用户当天就要求去掉："不要强制验证，全靠用户自觉"。拦下来的
  那一下代价是每次都要有人点确认，而起点对不对本来就是用户自己的事。
- **用例侧**：`RESET = {"scene": …, "wait_for": …}` 语义变成"起跑线的**声明/标注**"；
  入库时自动在文件头写一行 `# 起跑线（人工复位）：场景=…；标志物=…`（幂等，起跑线改了会更新），
  用例列表新增「起跑线（需人工复位）」一列，接口也带 `start_line` / `start_line_note`。
  没写 RESET 的用例仍用"上次跑通时记下的现场"兜一份说明。

单测：删除 6 条复位行为用例，新增 6 条（"必须没有复位入口" / 起跑线检查只读 /
不在起跑线也照跑（只提示不拦） / 标注幂等 …）；`tests/` 全量 **646 通过**（另有 4 条与本改动
无关的环境性失败：3 条 Windows 符号链接、`test_stdio_transport` 在改动前就是红的）。
### 22.3 跑不通 = 改用例再跑，不是"执行不了"（同日追加）

**用户诉求**："平台智能体执行自动化脚本的时候，判断如果走不通，不是直接不执行，
而是优化用例，然后再执行保存。"

落到三处（都是让这句话变成**事实**，而不只是提示词里的一句话）：

1. **失败摘要 + 分类**（`unity_service.failure_digest`）：`unity_run_script` 的返回值
   多了 `failure`：`kind`（`case` / `environment` / `timeout`）、挂在哪一步（轨迹里
   最后一个 `ok:false` 的步骤）、证据文件路径（`failure.txt` / `failure.png` /
   `steps.jsonl` / `case.py`）、环境类失败时附 `ERROR:`/`WARN:` 原文。exit 1 但报错里
   带环境指纹（掉线/未连接/工程脏被门禁/不在 Play）会被改判成 `environment` ——
   这类失败**改用例是白改**，得先修环境。智能体照 `kind` 决定下一步，不用啃 30k 输出。
2. **"已验证才入库"变成真的**：跑通一次就把这份内容的指纹记进台账
   （`workspace/default/unity-auto/.passed.json`，忽略平台自己写的起跑线标注行）；
   `save_script` 请求 `active` 但指纹不在台账里 → 落 `draft`，`unity_save_script`
   返回 `verified=false` + hint。于是"改用例 → 跑通 → 保存"是顺序上的硬约束，
   而不是工具 docstring 里的一句自述。
3. **提示词/技能同步**：`skills/unity-ui-test/SKILL.md` 增「跑不通怎么办：改用例，
   不是放弃」一节（三种 kind 怎么办 + 三条纪律：改法必须来自证据 / **不许为了变绿
   放宽或删掉断言** / 同一份改 3 轮不过就停下报结论）；能力提示词、`assembly.json`、
   记忆种子与**已落盘的** `workspace/default/memory/MEMORY.md`（含 .snapshot）一并更新
   —— 记忆里原来还写着"复位走 Lua、hard 已禁用"，留着会让智能体读到自相矛盾的规则。

单测：`tests/test_unity_bridge.py` 91 通过（新增失败分类、"已验证"指纹忽略标注、
未验证落 draft 三条）。
