# smart-test-platform ↔ dsh（DeepSeek Harness）桥接层

把平台的 agent 能力（用例入库 / 飞书导出 / 代码图谱 / 持久记忆 / Unity 自动化 /
视觉核验 / RAG 知识库）零 TS 代码地移植到 [dsh](https://github.com/deepseek-ai/deepseek-harness)：
平台 services 层原样复用，经 MCP (stdio) 暴露给 dsh；技能库直挂 dsh 原生
skills 系统；「测试架构师」人设做成可切换的 agent preset。

```
dsh web（DeepSeek 官方 Agent Harness，端口 3080/自定）
 ├─ mcp-client ──► agent_tools_server.py（29 工具，复用平台 services/DB）
 ├─ mcp-client ──► rag_server.py（LightRAG 知识库 5 工具）
 ├─ skill-filesystem.customSkillDirs ──► src/app/skills/（6 个技能原样复用）
 └─ agent preset「智能测试·全能力」──► 测试架构师人设 + 技能 + 模式内 MCP 工具
```

## 文件清单

| 文件 | 作用 |
|---|---|
| `../src/app/mcp_servers/agent_tools_server.py` | MCP 工具桥（29 工具，薄封装复用现有 `@tool` 实现与 services 层） |
| `cordis.patch.yml` | dsh 宿主补丁：把两个 MCP server 挂到全局工具层（推荐改用 preset，见下） |
| `agent-presets/smart-test/` | agent preset「智能测试」（人设 + 技能库直挂，不带 MCP） |
| `agent-presets/smart-test-suite/` | **「智能测试·全能力」preset：两个 MCP server 挂进模式内**（人设 + 技能 + 34 工具一站式） |
| `mcp_smoke.py` | MCP 冒烟测试（stdio 握手 + 真实工具调用） |

## 快速开始（推荐：「智能测试·全能力」模式，无需 --patch）

MCP 桥直接挂在 preset 组合里，只有选了这个模式的会话才能看到平台工具：

```sh
# 1. 安装 preset（一次性；已安装可跳过）
mkdir -p "$USERPROFILE/.dsh/.agent-presets"
cp -r dsh/agent-presets/smart-test-suite "$USERPROFILE/.dsh/.agent-presets/"

# 2. 正常启动
npx @deepseek-ai/dsh --profile web

# 3. 浏览器打开 http://127.0.0.1:3080
#    设置 → Agent Preset → 选「智能测试·全能力」
#    新建会话 → 选择被测游戏仓库作为工作目录 → 开始对话
```

preset 改动热生效；平台侧 `agent_tools_server.py` 升级后无需改 preset。

备选（全局挂载，所有会话可见平台工具）：

```sh
npx @deepseek-ai/dsh --profile web --patch E:/test_agent/smart-test-platform/dsh/cordis.patch.yml
```

冒烟测试（不依赖 dsh）：

```sh
.venv/Scripts/python.exe dsh/mcp_smoke.py
```

可选环境（缺省时对应工具 fail-open，不影响其他工具）：

- **飞书导出**：本机 `lark-cli` 已登录（`lark-cli auth login`）
- **视觉核验**：`.env` 配置 `VISION_MODEL`（+ 可选 `VISION_BASE_URL` / `VISION_API_KEY`，
  回退 `LLM_*` / `DEEPSEEK_API_KEY`）——dsh 宿主模型无视觉能力，由
  `analyze_image` 工具直连视觉端点补齐
- **RAG**：平台启动器已拉起 LightRAG(:5014)
- **代码图谱**：仓库已在平台「代码图谱」页建索引
- **Unity**：Editor 打开 + LuaTestTool Server(:16666) + Play Mode

## 工具清单（29 + 5）

**用例交付（MD 契约）** `get_beijing_timestamp` `save_case_document`（主交付工具，
整份覆盖写入）`read_case_document` `list_case_documents` `save_requirement_package`
（需求包）`lint_case_document`（确定性质量检查）`review_case_document`（隔离上下文复核）
`get_case_workflow_status`
**飞书** `export_project_mindmap`（按 project_name 读 MD 导出思维导图）`check_feishu_status`
**知识** `search_codebase`（代码图谱，repo_path 为显式参数）`save_memory` `search_memories`
**Unity** `unity_status` `unity_exec_lua` `unity_eval_lua` `unity_screenshot`
`unity_list_windows` `unity_run_skill_script`
**视觉** `analyze_image`（截图核验，modlens 式视觉桥）
**自进化** `evolution_trigger`（手动触发标注反思）`evolution_runs` `evolution_schedule`
**API 自动化** `api_doc_import`（飞书文档→接口清单）`api_script_generate`（生成 pytest）
`api_script_run`（执行+AI 自修复）`api_scripts_list` `api_script_runs` `api_docs_list`
**RAG**（mcp__rag__*）`rag_query` `rag_health` `rag_ingest_text` `rag_ingest_file` `rag_list_documents`

工具在 dsh 里的完整名形如 `mcp__smart-test__save_case_document`。

## 与 deepagents 方案的对照

原来 10 层中间件 + 自研 Backend 的工作，现在由 dsh 原生能力承担：

| 原 deepagents 侧 | dsh 侧 |
|---|---|
| SkillsMiddleware + `/skills/` FilesystemBackend | skill-filesystem `customSkillDirs` 直挂（SKILL.md 格式同源） |
| RepoProxyBackend（/repo/ 只读挂载 + ripgrep 看门狗） | 会话 cwd 即仓库；原生 grep/glob/read（自带 ripgrep） |
| SubAgentMiddleware（task 工具） | 原生 `subagent` / `subagent_fork`（后台可持续对话） |
| SummarizationMiddleware + MessageRepair 修复 | 原生 compaction（append-only 会话日志不变式，不会切散 tool_calls） |
| ToolResultLimiterMiddleware | 原生 tool-result-pruner（8k 阈值裁剪） |
| PermissionGate（三级权限） | 原生 sandbox 三档 + 审批（本来就是参照 dsh 实现的） |
| DynamicModelSelection（切视觉模型） | dsh 暂不支持视觉模型 → `analyze_image` 工具直连视觉端点 |
| LangGraph API + 前端 langgraph-sdk SSE | dsh web 自带会话/流式/子代理 UI |

## 值得装的社区插件（精选）

- **dsh-better-sidebar**（omdsh-dev，3k★）— 侧边工作台：文件树 + 编辑器 + 真终端 +
  Git 面板；自带 `registerTab` 扩展点，适合挂平台管理页
- **@zilliz/memsearch-dsh**（Zilliz，2.5k★）— 跨 agent 持久记忆（本地 bge-m3 混合检索，
  Markdown 为源）；与平台 `save_memory` 互补
- **dsh-market**（2.6k★）— 插件市场（可视化安装/启停，写 cordis.patch.yml 热重载）
- **dsh-qa-skills**（fishzjp）— 9 阶段 QA 技能套件（需求分析→策略→用例→评审→E2E），
  与我们的技能体系可互鉴
- **modlens**（3.7k★）— 视觉桥插件（本方案的 `analyze_image` 即受其启发）
- **dsh-codegraph**（4★但质量高）— 代码图谱工具的提示词引导手法（order 98 抢在官方
  文件工具前注入指引）值得借鉴
- 发现更多：GitHub topic [`dsh-plugin`](https://github.com/topics/dsh-plugin)、
  [awesome-dsh-plugin](https://github.com/awesome-dsh-plugin/awesome-dsh-plugin)

## 已知限制

- dsh 处于 developer preview（本方案验证于 **0.1.1-rc.2**），升级可能破坏兼容——
  全部配置都在本目录，升级后重跑 `dsh/mcp_smoke.py` + `--dump-config` 即可回归
- MCP 桥只走工具（无 Resources/Prompts）；dsh SDK 目前无 cancel 方法
- 未安装 preset 时，MCP 工具对标准 coding 会话也可见（工具注册在全局层）；
  想隔离可把两个 mcp 行挪进 preset 的 composition

## 后续方向

- [ ] 平台管理页（用例/评审/进化）经 dsh-better-sidebar 的 `registerTab` 嵌入
- [ ] 平台 FastAPI(:5012) 经 Python SDK（`deepseek-harness-sdk`）驱动 headless dsh，
  替换 LangGraph(:5011) 进程（前端聊天流改走自建 SSE）
- [ ] 把「验证门」模式（dsh-verification / ouroboros 的证据验收）引入用例交付流程
