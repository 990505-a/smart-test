# smart-test 全面分析（2026-09-17 · 第二轮）

> 本文是对 `/Users/yun/Documents/smart-test` 的一次完整代码级复核，基线 commit `8c7a1b6`。
> 与仓库既有 `PLATFORM.md`（同日早些时候写的架构说明）互补：`PLATFORM.md` 讲"是什么、
> 怎么跑"，本文讲"代码实际长什么样、哪里有坑"，且**每条结论都经过实读源码/查库核实**，
> 复核过的高危项标 ✅。
>
> 面向读者：接手这个平台的人。所有结论都给出 `文件:行号`，可逐条核对。

> **2026-09-18 后记**：本文是一份**时点快照**，其中一批问题已经修掉了。当天做的
> 一轮清理（删除死配置/死端点/死代码、修四处界面缺陷、把聊天页任务清单接上、
> 新增 `tests/test_wiring.py` 接线断言）覆盖了本文 §5 的第 6、15 条以及 §7 的
> 第 8 条等；具体以 `git log` 与 `tests/test_wiring.py` 的白名单注释为准。
> 读本文时请把"问题清单"当历史记录，而不是当前状态。
>
> **同一天第二轮（外部依赖收敛）又让两条失效**：
> §5 第 18 条"硬编码 Windows 路径"——默认值已改为平台自管安装位置
> （`tools/codebase-memory/`，`services/cbm_install.py` 按当前系统下载官方 release
> 并校验 sha256），GS 定制版 exe 与 `C:/codebase/...` 已全部移除；
> §5 第 20 条"`Capability.requires` 是纯文本、没有程序读"——已改为
> `core/integrations.py` 注册表里的 key，装配层据此在依赖不在线时收起该能力的工具，
> 提示词的依赖段也由同一份注册表渲染。

---

## 0. 结论摘要

**这是一个完成度相当高的单机智能测试平台**：4 个 DeepAgents/LangGraph 智能体、19 个 REST
路由、一套能进 CI 的测评门禁、Docker 编排、175 个单测。架构选型（MD 为单一事实源、
harness 风格工作区、确定性 traceId 接入 Langfuse）比多数同类项目想得更清楚，代码注释
密度高且解释了"为什么"，不是随手写的 demo。

主要风险不在架构，而在**边界**：

| 优先级 | 问题 | 影响 |
|---|---|---|
| P1 ✅ | 默认权限档 `workspace_write` 对文件写入**没有任何限制**（只有 `execute` 走审批） | 与命名/文档承诺不符，agent 可无审批写任意绝对路径 |
| P1 ✅ | 三处用户可控路径未过滤：`upload-to-workspace`、`/memories?space=`、附件下载 | 任意目录写文件 / 覆盖 `*/memory/*.md` |
| P1 ✅ | 全站无鉴权（有意设计）+ CORS `*` 带 credentials + launcher `0.0.0.0:5010` 可杀任意进程 | 单机内网可接受；一旦多人/公网共用即失守 |
| P1 ✅ | `saveMessagesToLocalStore` 闭包捕获旧 `assistantId` | 历史会话记错模式，"点开恢复模式"失效 |
| P1 ✅ | 前端 Markdown 渲染开了 `rehype-raw` 但没装 `rehype-sanitize` | LLM/技能文件内容可注入任意 HTML（iframe/form/style） |
| P1 ✅ | deepagents 摘要 offload 固定写到 `/conversation_history/`（`artifacts_root` 默认 `/`），而 backend 是真实路径语义 | 容器里写到容器根目录（不进卷、重建即丢）；本机跑直接权限失败 |
| P1 ✅ | 两个 Settings 单例：`app.*` 与 `src.app.*` 双模块身份（6 vs 89 个文件，甚至同文件混用） | 运行时改配置的代码可能改到"另一份" settings |
| P2 ✅ | `identifier_seq` 表无 model、无 DDL，从未被创建 | `POST /api/v2/projects` 必然 500（前端已不调用，属潜伏） |
| P2 ✅ | Langfuse 同步 `httpx.Client` 在 async 端点里裸调（`settings.py:112,195`、`eval.py:128`） | 探活时阻塞事件循环最长 30s |
| P2 ✅ | `.env.example` 端口仍是旧值（2026 / 9621 / 9000），与现行 5011/5014/5010 不符 | 照模板部署连不上 |
| P2 ✅ | Unity 工作区路径两套：service 写 `default/unity-auto/`，agent 与注入提示用 `default/unity/` | 产物目录分裂 |

**如果只修三件事**：① 收紧文件写路径与 `workspace_write` 语义；② 修 `useChat` 闭包 +
装 `rehype-sanitize`；③ 统一模块身份（全部改 `src.app.*` 或全部 `app.*`）。

---

## 1. 项目定位与规模

**智能测试平台（Smart Test Platform）**：基于 Agent + RAG + MCP + Skills 技术栈，覆盖
用例生成 / Web-UI 自动化 / Unity 自动化 / 接口自动化 / 代码分析。

| 维度 | 实测 |
|---|---|
| 后端 | Python 3.12（容器）/ 3.13（本机 `.python-version`），149 个 `.py`，**24.7k 行** |
| 前端 | Next.js 15.4.4 + React 19 + Tailwind 4 + SWR + LangGraph SDK，88 个 `.ts/.tsx`，**18.8k 行** |
| 智能体 | 5 个 graph：`smart_test_agent`（通用，对话页唯一入口）+ 3 个旧会话兼容薄壳 + `codebase_agent`（`graph.json`）。装配由 `agents/capabilities.py` 的能力清单驱动 |
| API | `/api/v2` 下 19 个 router（`src/app/api/__init__.py:30-51`） |
| 存储 | SQLite（业务）+ 工作区 Markdown（用例/记忆/产物）+ Langfuse（观测）+ LightRAG |
| 依赖 | 23 个运行时依赖（`pyproject.toml`），DeepAgents ≥0.7.9 / LangGraph ≥1.0 |
| 测试 | `tests/` 20 个文件，**175 个 test 函数**，全程离线（LLM/HTTP 均 mock） |
| 文档 | CLAUDE.md(27k) / PLATFORM.md(14k) / EVAL.md(17k) / DOCKER.md(22k) / GUIDE.md / MISSION / NOTES / RESOURCES |
| 前端体积 | `webui/` 1.2 GB（含 `node_modules` + `.next`） |

---

## 2. 运行时拓扑

```
浏览器 webui :5013
  │ SSE（@langchain/langgraph-sdk）
  ▼
LangGraph :5011  ── 5 个 graph（graph.json 注册，start_server.py 拉起，内存态 checkpointer；通用智能体 + 3 个兼容薄壳 + 代码图谱）
  │  ├─ 工作区 = 真实目录（WorkspaceShellBackend，virtual_mode=False）
  │  ├─ 记忆 = workspace/<space>/memory/*.md，每轮注入 system prompt
  │  └─ 监控 = 可选，折叠成 Langfuse trace（LANGFUSE_MONITOR_*）
 FastAPI :5012
  ├─ /api/v2/*（19 router）
  ├─ 测评执行器（BackgroundTasks 起批次 → 驱动 agent → 打分 → 上报）
  └─ APScheduler（代码图谱增量索引）
外部：LightRAG :5014(profile rag) / Playwright runner :5015 / 代码图谱 exe / Langfuse :3000
      / lark-cli / Unity Editor :16666 / dsh :3081(profile dsh) / launcher 控制台 :5010
```

**两套启动方式（互斥，DOCKER.md 已声明）**：`docker compose`（4~6 容器）或 `launcher.py`（本机
进程）。launcher 只管 langgraph/fastapi/webui/lightrag；Playwright 执行器与 dsh 不在其内。

**数据面**：`./docker-data/smart_test_platform.db`（SQLite，被 langgraph + fastapi + dsh
三个容器共写）、`./workspace`、`./datasets`、`./.env`（设置页会回写）。

---

## 3. 四个智能体

| 模式 | graph | 工具面 | 中间件链（洋葱序） |
|---|---|---|---|
| 用例生成 | `testcase_agent` | 用例 MD 全生命周期、需求包、lint/复核、飞书导图、代码图谱、记忆（6）、时间戳 | Skills → ThreadContext → FeishuReadonly → LiveModelReload → ThinkingEffort → DynamicModelSkill → PDFContext → MemoryInjection → Monitor → ToolResultLimiter → MessageRepair → **PermissionGate** |
| Unity 自动化 | `unity_agent` | `unity_status/exec_lua/eval_lua/screenshot/list_windows/run_skill_script` | Skills → MemoryInjection → WorkspaceContext → Monitor → PermissionGate |
| Web-UI 自动化 | `webui_agent` | `webui_runner_status/generate_spec/run_spec/screenshot/cli/save_script/list_scripts` | 同 Unity |
| 代码分析 | `codebase_agent` | `trace_symbol/read_symbol/repo_architecture/graph_search` | LiveModelReload → ThinkingEffort → MemoryInjection → WorkspaceContext → Monitor → ToolResultLimiter → PermissionGate（2026-09 起只被无头影响分析使用；交互式代码问答走对话页的「仓库」选择器） |

共同点：都用 `build_chat_model()`（`agents/testcase/model_factory.py:208-275`，按 `LLM_BASE_URL`
派生 provider，可热更）、都用 `WorkspaceShellBackend`（真实路径 + `inherit_env=True`）、
都把 `/skills/` 以只读 `FilesystemBackend(virtual_mode=True)` 挂在 `CompositeBackend` 上。

**值得注意**：
- Skills 是**全量注入**的——`SkillsMiddleware(sources=["/skills/"])` 不做按 agent 过滤，
  四个 agent 看到同一份技能目录（testcase 能看到 `unity-ui-test`，反之亦然）。靠提示词自律。
- **MCP 没有接进任何 agent**：`mcp_servers/rag_server.py` 与 `mcp/mcp_client.py` 只被
  `/api/v2/mcp` 的连通性检查使用。代码图谱走的是 `codebase_service.cbm_call` 直连。
  即"平台宣称 MCP"，但实际只有诊断页用到了 MCP。
- `internal_call_isolation.install()` 现在四个 agent 都调用（`codebase/agent.py` 早期漏过——
  当时靠"别的模块先 import 过"的副作用，单独起 code_analyst 时摘要会漏进对话）。

---

## 4. 单一事实源（这是设计上最值得肯定的部分）

平台刻意**不用关系库存业务内容**，四类事实源清晰：

| 事实源 | 位置 | 谁读 |
|---|---|---|
| 用例 | `workspace/default/cases/{项目}.md`（标题层级 = 导图节点，`[P0-P3]`、`前置：`、`- 操作 ⇒ 预期`） | `case_docs_service` 解析 → agent 工具 / `/case-docs` API / 飞书导图 |
| 记忆 | `workspace/<space>/memory/*.md` + `manifest.json` | `memory_service` → `MemoryInjectionMiddleware` 每轮注入 |
| 评测集 | `datasets/*.yaml`（与 dsh-eval-automation 同格式） | `eval/dataset.py` → runner / `/eval` 页 |
| 设置 | SQLite `settings_kv` + `.env`（DB → .env → 进程 env 三层优先级） | `settings_service` |

标注（✅/❌/⚠️ + `>` 批注）直接写在 MD 源文件里，导出/解析时自动剥离——"下游全是 LLM 读原文，
所以不需要打分表"。这个取舍很果断，也让 `/cases` 的编辑体验变得简单。

**评测子系统**是另一个亮点：`trace_id` 由 `thread_id` 确定性派生（FNV-1a，注释强调必须与
dsh 逐字节一致），所以进程外的 runner 能把分挂到正确的 trace 上；打分器三层（确定性 →
LLM-judge → 门禁表达式），门禁 **fail-closed**（分数未产出即失败）；CLI 退出码可做 CI 门禁。

---

## 5. 问题清单

### P1-1 ✅ 默认权限档不限制文件写入，且白名单可逃逸

`build_permission_middleware()` 的文档串写着"只门控 execute；文件写由 workspace 路由兜底"
（`src/app/middleware/permission_gate.py:224`），但兜底并不存在：

- `WorkspaceShellBackend` 用 `virtual_mode=False`（`src/app/agents/workspace_backend.py:77`），
  deepagents 该模式下语义是"绝对路径原样使用，相对路径按 cwd 解析"
  （`.venv/.../deepagents/backends/filesystem.py:189-190`）——**没有任何 root 约束**。
- 于是默认档 `workspace_write` 下，`write_file("/etc/...")`、`edit_file` 一路畅通无审批，
  与档位名字、以及 PLATFORM.md §4.6 的表述（"文件面的工作区限制来自后端 root（软限制）"）不符。
- 白名单本身也有口子（`permission_gate.py:60-79`）：`"sort"` / `"uniq"` / `"echo"` 少了尾随
  空格（会匹配 `sortx` 之类），`sort -o out`、`uniq in out`、`sed -n 'w file'` 都能写文件，
  `awk 'BEGIN{system("rm -rf X")}'` 既无 `>` 也无 `$(`/反引号，能绕过副作用检测直接执行命令。

**建议**：要么把默认档 backend 换成 `virtual_mode=True`（真正锁在工作区内），要么在
`_needs_execute_approval` 之外给文件写工具也挂 HITL；白名单改成 `shlex` 分词后按
`cmd + 子命令 + 危险 flag` 判定，别用字符串前缀。

### P1-2 ✅ 三处用户可控路径未过滤

| 位置 | 问题 |
|---|---|
| `src/app/api/v2/extract_pdf.py:119-124` | `space_id` / `agent_name` / `thread_id` 直接拼路径并 `mkdir(parents=True)`，`space_id="../../.."` 即可任意建目录写文件。**这条是活的**：聊天页上传 PDF/Markdown 就走它（前端 `webui/src/app/utils/multimodal.ts:135` → Next route → `/api/v2/upload-to-workspace`），且接口无鉴权 |
| `src/app/services/memory_service.py:129-131` + `src/app/api/v2/memories.py:73-171` | `memory_root(space)` = `workspace_dir / space / "memory"`，`space` 是未校验的 query 参数 → 可读写/删除任意 `*/memory/*.md`（文件名被 `_safe_file` 限制为 `*.md`，缩小了范围但没消除） |
| `src/app/api/v2/attachments.py:78` + 上传存 `file.filename` 原样（`attachments.py:49`） | 下载时把 DB 里的文件名直接拼 `/tmp/smart_test_platform/`，`../` 形态可越出临时目录；且临时文件**永不清理**（磁盘泄漏） |

对照做得对的地方：`skills.py:34-39`、`eval.py:244-252`、`case_docs_service.doc_path:60-67`、
`web_ui_auto.py:144-155` 都做了路径归一化校验——说明团队知道该怎么做，只是漏了几处。

### P1-3 ✅ 鉴权：有意为之，但边界要写清楚

`get_current_user` 无 token 时返回内置本地用户，永不 401（`src/app/api/v2/auth.py:43-63`，
注释明确说明这是 2026-09 去登录的有意取舍）。配套的事实：

- 6 个模块**连 `CurrentUserDep` 都没挂**：projects / attachments / workspaces / configurations /
  threads(messages) / extract-pdf。其中 attachments、workspaces、configurations 前端已
  零调用（属遗留 API 面），但 **`upload-to-workspace` 与 `/threads/*` 是活路径**。
- CORS `allow_origins=["*"]` + `allow_credentials=True`（`src/app/fastapi_app.py:74-80`）：
  任意网页都能对 5012 发起带凭据的写操作。
- `launcher.py` 以 `0.0.0.0:5010` 暴露且 `/api/services/{name}/{action}` 无鉴权，
  Windows 分支还会用 `taskkill` 杀掉占用端口的外部进程（`launcher.py:203-211`）。
- 默认口令 `admin123`（`config.py:60`），`.env.example:34` 直接写出来。

**结论**：说成"单机内网工具"就要真的保证它只在单机内网——目前 CORS 与 launcher 监听
地址与这个前提冲突。改 CORS 白名单 + launcher 绑 `127.0.0.1` 是低成本高收益。

### P1-4 ✅ 前端 `useChat` 闭包捕获旧 `assistantId`

`saveMessagesToLocalStore` 的 `useCallback` 依赖数组是 `[]`（`webui/src/app/hooks/useChat.ts:452`），
但函数体里写 `agent: assistantId`（同文件 `:406`）。`assistantId` 是该 hook 的参数（`:119,123`），
空依赖意味着**首次渲染后就固定**。切换模式后落库的 `thread_infos.agent` 一直是旧值，
而"点开历史会话恢复模式"正是靠这一列（`webui/src/app/chat/page.tsx:49-64`）。

**修法**：把 `assistantId` 放进依赖数组，或用 ref 兜住（该文件已有多处 `*Ref` 模式可循）。

### P1-5 ✅ Markdown 渲染开 `rehype-raw` 但没装 `rehype-sanitize`

`webui/package.json:39` 有 `rehype-raw`，**没有** `rehype-sanitize`（`node_modules` 里也不存在），
`MarkdownContent.tsx:530` 直接 `rehypePlugins={[rehypeRaw]}`。渲染内容是 LLM 输出、技能文件、
子智能体输出——即模型从网页/文档里读到的任何 HTML 都会被真实解析成 DOM 节点
（`<iframe>`、`<form>`、`<style>` 可注入；`javascript:` URL 由 react-markdown 的
`urlTransform` 挡住，但标签本身挡不住）。react-markdown 官方 README 的 Security 一节点名
要求搭配 `rehype-sanitize`。

### P1-6 ✅ 上下文摘要的落盘位置是错的（deepagents 默认值 vs 真实路径后端）

deepagents 的 `SummarizationMiddleware` 把被挤出的历史写到
`<artifacts_root>/conversation_history/{session_id}.md`（`.venv/.../middleware/summarization.py:603`），
而 `CompositeBackend.artifacts_root` 默认 `"/"`（`.venv/.../backends/composite.py:212`），
平台构造时没有覆盖（`src/app/agents/testcase/agent.py:93-98` 等四处）。偏偏 backend 是
`virtual_mode=False` 的真实路径语义，于是目标是**文件系统根目录**：

- 容器里（backend 镜像无 `USER`，跑 root）能写进去——但写在容器根目录，
  **不进任何卷**，重建即丢；
- 本机跑（macOS/Linux 普通用户）直接 PermissionError。

**修法**：构造 `CompositeBackend` 时传 `artifacts_root=str(workspace_dir)`，或改用
子目录路由（如 `"/conversation_history/": skills_backend 同款的 workspace backend`）。

### P1-7 ✅ 双模块身份造成两个 Settings 单例

`src/` 没有 `__init__.py`（namespace package），于是 `app.*` 和 `src.app.*` 都 import 得动：

- **89 个文件**用 `from src.app.*`，**6 个文件**用 `from app.*`——而且 `src/app/agents/unity/agent.py`
  在 29-36 行**同一个文件里混用**两种写法。
- 两条启动路径的模块名不同：`Dockerfile.backend` 的 CMD 是
  `uvicorn src.app.fastapi_app:app`；而 `start_server.py:25-26` 把 `src/` 插到 `sys.path[0]`，
  LangGraph 以 `app.agents.*` 载入 graph，graph 内部再 `from src.app.*` 就得到**第二份**
  `app.core.config.settings`。
- 而运行期确实会改 settings：`agents/testcase/model_factory.py:182,186` 用
  `setattr(settings, field, ...)` 做设置页热更，`codebase_service.py:962-963` 写调度配置。
  改到"哪一份"取决于 import 路径。

**建议**：统一成一种写法（推荐全 `src.app.*`，与 Docker CMD 一致），或给 `src/` 加
`__init__.py` 并全仓统一。这是一次机械替换，但能消掉一类"改了不生效"的幽灵 bug。

### P2 级问题

| # | 问题 | 证据 |
|---|---|---|
| 1 ✅ | `identifier_seq` 表**从未被创建**（无 model、无 DDL；实际库 16 张表里也没有），而 `generate_identifier` 裸 SQL 依赖它 → `POST /api/v2/projects` 必然 500。前端已不调用该接口，属潜伏 bug | `db/utils/identifier.py:29,37`、`db/services/project_service.py:69` |
| 2 ✅ | Langfuse 用同步 `httpx.Client`（`eval/langfuse_client.py:96`），却在 async 端点里裸调：`api/v2/settings.py:112,195`、`api/v2/eval.py:128,132` → 探活时阻塞整个事件循环（默认超时 30s） | 同上 |
| 3 ✅ | `.env.example` 端口漂移：`LANGGRAPH_API_URL=http://localhost:2026`、`LIGHTRAG_BASE_URL=...:9621`、注释"启动器(:9000)"，现行分别是 5011 / 5014 / 5010 | `.env.example:29,48-49` |
| 4 ✅ | Unity 工作区两套路径：`unity_service.py:93,140` 用 `default/unity-auto/`，而 `unity/agent.py:50` 的默认工作区与提示词注入是 `default/unity/`（仓库里两个目录并存） | 同上 |
| 5 ✅ | 代码图谱子图查询用 f-string 拼 Cypher，`_cy()` 是自实现的转义（只处理 `\` 和 `'`），入口是 `GET /codebase/graph-subgraph?value=` | `services/codebase_service.py:433-435,459-470` |
| 6 | `eval_max_repair` / `dataset.max_repair` 已解析、已在 `/eval/status` 暴露，但 `runner.run_dataset(repair_rounds=None)` 从未被传值——**测评的自修复能力实际未接线** | `core/config.py:146`、`api/v2/eval.py:145`、`eval/runner.py:89` |
| 7 | `start_index` 用 `asyncio.create_task` fire-and-forget 且不持有引用，异常也无人 await；索引锁 `_index_lock`/`_index_progress` 是进程内状态，多 worker 下失效 | `services/codebase_service.py:856,700,757` |
| 8 | TOCTOU：用例文档保存先 `_check_expected` 再写文件，sidecar 元数据也是 read→save，两个窗口并发保存会漏掉乐观锁冲突 | `services/case_docs_service.py:684-701`、`case_workflow_service.py:170-202` |
| 9 | `seq_index` 用 `max()+1` 分配再 upsert，非原子（代码注释自认 "concurrent requests may share a slot"），并发写会撞号，破坏分页排序 | `api/v2/messages.py:540-552` |
| 10 | `_backfill_local_store` 逐条 `SELECT`+`flush`（N+1）+ 全表 `seq_index+1_000_000` 平移 | `api/v2/messages.py:997-1063` |
| 11 | `attachments.py:39` 一次性 `await file.read()` 无大小上限，大文件全量进内存 | 同上 |
| 12 | `GET /codebase/repos` 对未登记仓库逐个 spawn exe 子进程探测（`_probe_project`），延迟随仓库数线性增长 | `services/codebase_service.py:591,612-624` |
| 13 | `main()` 里 `graph.json` 的 `dependencies: ["."]` 与 `start_server.py` 的 `sys.path.insert` 组合，是上面 P1-7 的根因 | `graph.json`、`start_server.py:25-26` |
| 14 | 死配置：`circuit_breaker_*`、`retry_*`、`doubao_api_key`、`openai_api_key`、`enable_pdf_multimodal`、`llm_provider`、`lightrag_llm_model` 全仓 0 引用 | `core/config.py:16,39-41,46-50,82` |
| 15 | 死代码：`agents/testcase/file_preprocess.py`（整文件）、`context.py:9-65`（`TestCaseAgentContext`+`ContextInjectionMiddleware`，零引用）、`processors/{image,excel}.py`、前端 `useConfigurations.ts`、`DataTable.tsx`、4 个零引用 ui 组件 | 各文件 |
| 16 | 三份重复实现：上传文件处理（`pdf_context.py` / 死掉的 `file_preprocess.py` / `extract_pdf.py`）、工具调用断链修复（`message_repair.py` vs deepagents 内置 `PatchToolCallsMiddleware`）、视觉模型配置（`model_factory.py:290-337` vs `agent_tools_server.py:281-362`） | 各文件 |
| 17 | `pdf_context.py:28` 把上传落到**包内** `src/app/workspace/uploads`，而 `ThreadContextMiddleware` 与 `extract_pdf.py:121` 告诉 agent 的是 `workspace/<space>/<agent>/uploads/<thread>/`——三处不一致 | 同上 |
| 18 | 硬编码 Windows 路径作默认值：`C:/codebase/cbm-gs.exe`、`E:/m72-publish/m72`；`codebase_memory_shim.py:24` 同一份路径 | `core/config.py:92,94,102-103` |
| 19 | Docker：4 个镜像全部 root 运行、无 `USER`；compose 无资源限制与日志轮转；`Dockerfile.playwright` 不用 lockfile（`npm install`）导致构建不可复现；dsh 健康检查探的是 socat 端口而非 dsh 端口（dsh 挂了仍报 healthy） | `Dockerfile.*`、`docker-compose.yml` |
| 20 | `skills/testcase-workflow/SKILL.md:19-20` 仍写 `/uploads/{thread_id}/` 与已删除的 `/repo/`，`:94` 说"最多复核 2 轮"而代码是 3（`case_workflow_service.py:33`）——技能文档与实现脱节会直接误导 agent | 同上 |
| 21 | `skills/unity-ui-test/SKILL.md:2` 的 `name: unity-auto-test` 与目录名不符；`skills/L849.txt` 是误入技能库的用例片段 | 同上 |

---

## 6. 工程质量

**做得好的**：

- 注释解释"为什么"而非"做什么"（例如 `auth.py` 为什么允许无 token、`start_server.py`
  为什么是 4 个并发槽、`case_docs_service` 的原子写为什么要 fsync）。
- 服务层契约统一：外部依赖失败一律降级成 `{"success": False, "error": ...}` 而不是抛异常，
  可测可控（`lightrag_service`、`feishu_service`、`codebase_service`、`unity_service` 一致）。
- 前端细节专业：流式渲染 50ms 合并、每 30 事件/≥5s 增量落库、Virtuoso + `firstItemIndex`
  锚定翻页、断线 `joinStream` 重连 + 取消墓碑、Sigma.js 懒加载 + 客户端 ForceAtlas2、
  索引进度 2s/8s 自适应轮询。
- 迁移策略务实：`init_db()` 就地 `RENAME`/`ALTER` + `CREATE TABLE new` 全表搬运
  （`db/database.py:73-162`），旧库无需重建；`identifier_seq` 之类漏网是这套方案的固有代价。
- 近两天（`f2f07a8`、`8c7a1b6`）的改造（去登录、工作区模型、记忆 MD 化、Docker 化 +
  测评增强）已经落地且有验证记录（PLATFORM.md §8）。

**工程上的短板**：

- **巨型文件**：前端 7 个文件 >600 行（`useChat.ts` 1259、`ChatInterface.tsx` 963、
  `useNewModules.ts` 911 塞了 8 个模块的类型和 hooks）；后端 `codebase_service.py` 967、
  `case_docs_service.py` 742、`feishu_service.py` 679。
- **重复的辅助函数**：`formatElapsed` 三份、状态色映射四套、`toLocaleString("zh-CN")` 12 处。
- **测试结构不对称**：中间件/服务层测得不错（175 个用例，覆盖 permission_gate、
  memory_injection、workspace_backend、model_factory 等），但

| 覆盖空洞 | 说明 |
|---|---|
| 4 个 agent graph | 无任何编排测试 |
| HTTP 层 | 全仓无 `TestClient`/`ASGITransport`，路由行为只能靠 `tools/playwright-runner/acceptance`（需真起 5012/5013 + 账号，非 CI 可跑） |
| `src/app/eval/` | 只测了 `generator.py` 纯函数；`runner` / `gate` / `scorers` / `langfuse_client` / `tracing` / `live` 全裸——而这几个是 EVAL.md 宣称的门禁核心 |
| `launcher.py` / `server.mjs` | 无测试 |
| CI | 无 `.github/workflows`；`.dockerignore` 排除 `tests/`，容器内也跑不了 |

- 现存 1 条红灯：`tests/test_lightrag_service.py::test_health_degrades_when_server_down`
  在带代理的本机失败（断言"不可达"，代理返回 502）——环境问题，PLATFORM.md §6.6 已记录。

---

## 7. 建议的修复顺序

**第一批（安全与正确性，改动小）**
1. `upload-to-workspace` / `memories?space=` / 附件下载三处加路径归一化校验（对齐
   `skills.py:34-39` 的写法）。
2. `useChat.ts` 的 `saveMessagesToLocalStore` 依赖数组补 `assistantId`。
3. 装 `rehype-sanitize` 并接到 `MarkdownContent` 的 `rehypePlugins`。
4. `CompositeBackend(..., artifacts_root=str(workspace_dir))`。
5. CORS 收敛为白名单；launcher 绑 `127.0.0.1`；`.env.example` 端口改 5011/5014/5010。

**第二批（语义一致性）**
6. 决定权限档语义：要么默认档用 `virtual_mode=True`，要么给文件写工具也挂 HITL；
   同时把白名单换成 `shlex` 分词判定。
7. 全仓统一 `src.app.*` 模块身份，消掉双 Settings 单例。
8. 补齐 `eval_max_repair` 的接线（或删掉配置项，别留误导）。
9. 修 `CREATE TABLE identifier_seq`（加 model 或改成 `create_all` 能覆盖的表），
   顺手删掉 `repositories/base.py` 里的 PG advisory lock 死代码。

**第三批（可维护性）**
10. 清理死代码/死配置（`file_preprocess.py`、`context.py:9-65`、`processors/*`、
    `useConfigurations.ts`、`DataTable.tsx`、`circuit_breaker_*` 等）。
11. 拆分 7 个前端巨型文件；抽出 `formatElapsed` 等重复 helper。
12. 给 HTTP 层补 `TestClient` 冒烟测试（先覆盖 `/health`、`/case-docs`、`/eval/status`），
    给 `eval` 的 gate/scorer 补纯函数单测——这两块是"宣称有门禁但没测门禁"的缺口。
13. Unity 工作区路径统一（`unity-auto` → `unity` 或反之），并修 SKILL.md 的过时描述。

---

## 8. 复核方法说明

- 本文所有 ✅ 标注项均通过直接阅读源码、`.venv` 内依赖源码、以及对本仓库 SQLite
  `smart_test_platform.db` 的只读查询核实，非"疑似"推断。
- 未逐条复核的低优先级项（如 N+1 的具体往返次数、Docker 镜像体积）沿用静态阅读结论，
  修之前建议再确认一次。
- 本轮分析未修改任何代码文件，仅新增本文。
