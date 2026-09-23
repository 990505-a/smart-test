# 智能测试平台 —— 架构总览

> 本文画的是**当前实际在跑的东西**，不是设计意图。每条都对应代码里的落点，可以逐条核对。
> 历史沿革与事故复盘见 `PLATFORM.md`；本文只讲"现在长什么样"。
> 最后核对：2026-09-23。

---

## 1. 进程与端口（一次 `launcher.py` 拉起全部）

```
                          ┌──────────────────────────────┐
                          │  launcher.py  控制台 :5010    │  ← 只管进程：起停/看日志/一键装依赖
                          │  （autostart 除标注外全为真） │     **不在任何数据链路上**
                          └───────────────┬──────────────┘
        ┌───────────────┬───────────────┼───────────────┬────────────────┐
        ▼               ▼               ▼               ▼                ▼
 ┌─────────────┐ ┌─────────────┐ ┌────────────┐ ┌──────────────┐ ┌────────────────┐
 │ LangGraph   │ │ FastAPI     │ │ WebUI      │ │ Playwright   │ │ Unity MCP 桥   │
 │   :5011     │ │   :5012     │ │  :5013     │ │  执行器:5015 │ │   :5016        │
 │ start_server│ │ src.app.    │ │ next dev   │ │ node server  │ │ uvx mcp-for-   │
 │ .py         │ │ fastapi_app │ │ (Turbopack)│ │ .mjs         │ │ unity 10.2.0   │
 │ inmem 运行时│ │ 平台 API    │ │ 控制台界面 │ │ 真实浏览器   │ │ autostart=false│
 └─────────────┘ └─────────────┘ └────────────┘ └──────────────┘ └───────┬────────┘
                                                                         │ loopback
 ┌──────────────────────────┐                              ┌─────────────▼────────┐
 │ LightRAG :5014           │                              │ Unity 编辑器（外部） │
 │ 一库一实例（autostart=false）│                            │ 装「MCP for Unity」包│
 └──────────────────────────┘                              └──────────────────────┘
 ┌──────────────────────────┐   ┌──────────────────────────┐
 │ codebase-memory 图谱 daemon│  │ Langfuse（外部，:3000）  │
 │   :9749（按需，非必须）    │   │ 测评 + 监控两条链路       │
 └──────────────────────────┘   └──────────────────────────┘
```

**关键点：浏览器聊天是直连 :5011 的**（`@langchain/langgraph-sdk`，SSE 流式），
**FastAPI 不在对话链路上** —— 它是控制面（平台 API、测评执行器、定时任务、无头调用）。

---

## 2. 一次对话的完整链路

```
浏览器 /chat
  │ ① client.runs.stream(threadId, assistantId, {input, configurable})
  │    configurable = {space_id, workspace_path, permission_mode,
  │                    llm_reasoning_effort, agent_id, model…}
  ▼
LangGraph :5011  ── 拉起 graph：smart_test_agent（对话页唯一入口）
  │ ② 组装 system prompt：平台提示词 + 能力领域段 + 技能清单 + 记忆模块 + 工作区说明
  │ ③ 模型调用 ←→ 工具调用（每次模型调用前重算工具面与审批门）
  │ ④ 需要审批的调用 → interrupt → 前端弹卡片 → Command(resume=…) 继续
  ▼
SSE 逐段回浏览器（messages/partial → messages/complete）
  │ ⑤ 流结束后前端 POST /api/v2/threads/{id}/messages/save（消息镜像进 SQLite）
  ▼
历史消息此后走本地 SQLite 分页，不再依赖 LangGraph 线程状态
```

**工具执行时落到哪**（按能力分流）：

```
┌── 进程内（LangGraph 进程自己干）────────────────────────────────────┐
│ 文件/ shell（真实路径，cwd = 本次会话工作区）                       │
│ 用例文档读写、记忆读写、Lint/复核                                    │
└─────────────────────────────────────────────────────────────────────┘
┌── 经 MCP / HTTP 出去 ───────────────────────────────────────────────┐
│ unity_*     → Unity MCP 桥 :5016 → Unity 编辑器    （22 个工具）     │
│ webui_*     → Playwright 执行器 :5015 → 真实浏览器  （8 个）         │
│ rag_*       → LightRAG :5014                       （6 个）         │
│ 图谱 4 个    → codebase-memory.exe（CLI 子进程 + stdio MCP 垫片）     │
│ 飞书 2 个    → lark-cli 子进程                                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. 智能体内部：一个图 + 一层中间件洋葱

```
                    ┌──────────────────────────────────────────────┐
   graph.json 注册  │  smart_test_agent   ← 对话页唯一入口           │
   5 个 graph       │  testcase/unity/webui/codebase_agent          │
                    │  ← 旧会话兼容的薄壳，不再面向新对话            │
                    └───────────────────────┬──────────────────────┘
                                            │ create_deep_agent(...)
                    ┌───────────────────────▼──────────────────────┐
                    │  backend = CompositeBackend                   │
                    │   default → WorkspaceShellBackend（真 shell） │
                    │   /skills/     → 只读技能库 src/app/skills/   │
                    │   /artifacts/  → 超大结果与摘要的落盘区        │
                    └───────────────────────┬──────────────────────┘
                                            │
   ┌────────────────────────────────────────▼─────────────────────────────────┐
   │  中间件洋葱（外层先跑；harness.py:96-152 的实际顺序）                       │
   │                                                                          │
   │  ① AssemblyToolsMiddleware   ← 按 agent_id 现算工具面/提示词段/审批门       │
   │  ② LiveSkillsMiddleware      ← 按装配过滤技能清单                          │
   │  ③ ToolErrorFeedbackMiddleware ← 工具异常 → 错误 ToolMessage（模型可见）   │
   │  ④ ThreadContextMiddleware  ⑤ FeishuReadonlyMiddleware（默认开）          │
   │  ⑥ TodoListMiddleware       ⑦ LiveModelReloadMiddleware（.env 变了换模型）│
   │  ⑧ ThinkingEffortMiddleware ⑨ RunModelMiddleware                        │
   │  ⑩ PDFContextMiddleware     ⑪ MemoryInjectionMiddleware（记忆全量注入）   │
   │  ⑫ MonitorMiddleware        ⑬ ToolResultLimiterMiddleware（20k 字符）     │
   │  ⑭ ExplorationNudgeMiddleware（连续 N 次探测 → 提醒截图）                  │
   │  ⑮ VisionGateMiddleware（读不了图的模型 → 占位符）                         │
   │  ⑯ RunGuards（模型/工具调用上限，**默认关闭 = 0**）                        │
   └──────────────────────────────────────────────────────────────────────────┘

   能力 = 数据（capabilities.py）            装配 = 用户数据（assembly.json）
   ┌────────────────────────────┐           ┌─────────────────────────────┐
   │ testcase  12 工具 + 5 技能  │           │ agents: [general, api, …]   │
   │ unity     22 工具 + 1 技能  │  ──────►  │  每个 agent：勾哪些能力、     │
   │ webui      8 工具 + 1 技能  │   每轮    │  勾哪些工具、勾哪些技能、     │
   │ codebase   4 工具           │   现算    │  哪些工具要人工审批           │
   │ rag        6 工具           │           └─────────────────────────────┘
   └────────────────────────────┘
```

**设计取舍（平台自己的注释）**：**不用子智能体**——deepagents 的 isolated 子智能体只拿到
一句 description、拿不到对话历史，而本平台的流程是多轮的。代价如实标注：技能绑定是
**提示级**而非访问控制级。

---

## 4. 能力 × 外部依赖 × 产物

| 能力 | 依赖（不在线时工具被隐藏） | 产物落点 |
|---|---|---|
| testcase 用例生成 | 飞书 lark-cli | `cases/<项目>.md`（用例文档，**平台平铺，不分子目录**）、`requirements/` |
| unity 自动化 | Unity MCP 桥 :5016 → Unity 编辑器 | `unity-auto/<脚本id>/<时间戳>/`（截图/录像/steps.jsonl/失败现场/case.py）+ 台账 `.passed.json` |
| webui 自动化 | Playwright 执行器 :5015 | `web-ui-auto/runs/<runId>/`（runner 自己的目录 + 清单入库） |
| codebase 代码分析 | codebase-memory.exe（本机二进制，无源码） | `codebase-reports/`、`codebase/.manifests/` |
| rag 知识库 | LightRAG :5014（一库一实例） | `rag/<库的命名空间>/` + `rag_kbs.json` 注册表 |
| （接口自动化，无智能体工具） | 本机 python + pytest | `api-auto/<脚本id>/` |

---

## 5. 数据与状态落点（哪些丢了会疼）

```
┌── 持久（重启不丢）────────────────────────────────────────────────────────┐
│ SQLite  smart_test_platform.db（23 张表，仓库根）                          │
│   ├─ 业务：thread_infos / thread_messages、users / auth_tokens、settings_kv│
│   ├─ 用例：unity_scripts / unity_script_runs、web_ui_*、api_*             │
│   ├─ 图谱：codebase_repos / codebase_index_runs / codebase_impact_reports  │
│   └─ 测评：eval_batches / eval_case_results                                │
│ workspace/<space>/                                                        │
│   ├─ memory/      记忆模块（每轮全量注入 system prompt）                    │
│   ├─ automation/  ★ 自动化工程（代码 + 用例 + 生成物 + 按需读的 docs/）      │
│   ├─ cases/ requirements/ reports/   交付物                                │
│   ├─ unity-auto/ web-ui-auto/ api-auto/ eval-runs/  运行产物（可清理）      │
│   ├─ codebase/ codebase-reports/ rag/  索引数据（可重建）                   │
│   └─ testcase/uploads/ .artifacts/ .feishu_tmp/  上传与临时                  │
│ .env（密钥）+ settings_kv（设置页覆盖）                                     │
│ Langfuse（外部）：测评 trace/score + 监控 trace（两套独立配置）              │
└───────────────────────────────────────────────────────────────────────────┘
┌── 易失（重启即丢）────────────────────────────────────────────────────────┐
│ LangGraph 运行态：inmem runtime + 自研 keeper（.langgraph_api/*.pckl）     │
│   → 实测：今天产生了 4 个 _corrupt_* 隔离目录，store.pckl 长期是 6 字节空文件│
│   → 后果：重启后所有会话的**模型上下文**清零（消息文本仍在 SQLite，可回看）  │
│ 进程内全局状态：GPU 熔断、工程脏标记、录像钩子、工具缓存、装配快照(TTL)      │
└───────────────────────────────────────────────────────────────────────────┘
```

**写入关系**：FastAPI 与 LangGraph 是**两个进程写同一个 SQLite**（无 Alembic、无 WAL，
见 `PLATFORM.md` 与 `ANALYSIS.md` 的风险清单）。

---

## 6. 观测：两条独立链路

```
     日常对话（人工使用）                      测评（跑数据集）
            │                                        ▲
            │ 进程内中间件钩子                        │ FastAPI 驱动
            │ before_agent / wrap_model_call          │ 无头调用 :5011
            │ wrap_tool_call / after_agent            │ + 进程外 runner 打分
            ▼                                        │
   ┌────────────────────┐                  ┌────────┴───────────┐
   │ Langfuse「监控」项目 │                  │ Langfuse「测评」项目 │
   │ 1 trace/轮          │                  │ 1 trace/用例        │
   │ LANGFUSE_MONITOR_*  │                  │ LANGFUSE_*          │
   └────────────────────┘                  └────────┬───────────┘
   └────────── 未配置 = 静默 no-op ──────────┘        ▼
                                            三层打分：确定性 / LLM 裁判 / 人工标注
                                            门禁语法：avg(x)>=0.8 && all(y)
                                            结果另存 SQLite + workspace/…/eval-runs/
```

---

## 7. 部署形态

| 形态 | 组成 | 说明 |
|---|---|---|
| **本机（实际在用）** | launcher 拉起 5010-5013/5015，5014/5016 手动 | Unity 与 Playwright 都需要宿主资源 |
| **Docker（`docker-compose.yml`）** | profile `docker`：langgraph/fastapi/playwright/webui + profile `dsh`/`rag` | 默认关闭（会与宿主进程抢端口）；**无 launcher** → 一键依赖安装与 `/agents/reload` 不可用；Unity 桥与编辑器无法进容器 |

---

## 8. 一眼看出的薄弱点（详细见 `PLATFORM.md` / `ANALYSIS.md`）

1. **无鉴权**：`get_current_user` 无 token 时返回内置本地用户；:5011 完全裸奔，`CORS=*`，
   默认管理员 `admin/admin123`。设计前提是"内网单机"。
2. **无沙箱**：agent 拿真 shell + 真实路径；LLM 生成的代码（api-auto 的 pytest、
   web-ui 的 spec）在本机执行，api-auto 还继承完整环境变量。
3. **运行态易失**：inmem runtime + 自研 keeper，重启即丢上下文（见第 5 节）。
4. **两进程共写 SQLite**：无 WAL、无迁移工具，`ALTER` 失败被静默吞掉。
5. **单实例假设**：Unity 桥、GPU 熔断、脏标记都是"当前编辑器"的全局状态 → 多游戏是分时的。

---

## 9. 目录视角（工作区怎么分区）

```
workspace/<space>/                    空间（现在锁死 default）
├── memory/          平台读：记忆（常驻 = 铁律 + 索引；专题按需读）
├── automation/      ★ 人管：自动化工程，按被测对象分目录
│   └── unity/<游戏>/{lib,cases,docs,tools,archive}
├── cases/ requirements/ reports/        人管：交付物
├── unity-auto/ web-ui-auto/ api-auto/ eval-runs/   平台管：运行产物
├── codebase/ codebase-reports/ rag/                平台管：索引数据
└── testcase/uploads/ .artifacts/ .feishu_tmp/      平台管：临时
```

**边界**：平台只管"机器产的东西"（运行产物/索引/临时）与"配置"（memory、assembly.json）；
`automation/` 与交付物是人的地盘，平台不碰。
