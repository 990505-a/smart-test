import os
from pathlib import Path
from typing import Any

from pydantic import model_validator
from pydantic_settings import BaseSettings

# 平台自管的 codebase-memory 安装位置（见 services/cbm_install.py）。
# 放 tools/ 与仓库内其它自带 sidecar（tools/playwright-runner）一致。
CBM_MANAGED_DIR = Path(__file__).resolve().parents[3] / "tools" / "codebase-memory"
_DEFAULT_CBM_EXE = str(
    CBM_MANAGED_DIR / ("codebase-memory-mcp.exe" if os.name == "nt" else "codebase-memory-mcp"))


class Settings(BaseSettings):
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    # --- Agent chat model (any OpenAI-compatible endpoint) -------------------
    # provider "deepseek": official API via langchain-deepseek (uses the
    #   DEEPSEEK_* fields above as fallback for key/model).
    # provider "openai_compatible": any OpenAI-compatible endpoint (OpenAI,
    #   SiliconFlow, OneAPI, OpenRouter, vLLM, ...) — requires llm_base_url.
    llm_provider: str = "deepseek"  # 兼容保留；实际由 model_factory 按 base_url 派生
    llm_model: str = ""  # empty -> deepseek_model
    llm_base_url: str = ""  # e.g. https://api.siliconflow.cn/v1
    llm_api_key: str = ""  # empty -> deepseek_api_key
    # Real context window of the model. SummarizationMiddleware triggers at
    # 0.85 × this value; a value larger than the real window means compaction
    # never fires and long conversations grow unbounded (then hard-fail).
    llm_context_window: int = 128_000
    llm_max_retries: int = 3
    llm_request_timeout: int = 300
    # 流式看门狗：两个 chunk 之间的最大间隔秒数。思考型模型长推理段
    # 可能静默 >120s（langchain-openai 默认值），触发 StreamChunkTimeoutError
    # 掐断整个 run。None = 禁用看门狗。
    llm_stream_chunk_timeout: float | None = 300.0
    # Default reasoning effort for thinking-capable models ("" | low | medium |
    # high). Sent as the reasoning_effort kwarg; per-run overrides come through
    # the run's configurable.llm_reasoning_effort. Leave empty if the endpoint
    # rejects the parameter.
    llm_reasoning_effort: str = ""
    langgraph_api_url: str = "http://localhost:5011"
    # 启动器（本机模式的服务管理器，:5010）：后端用它重启 LangGraph —— 改完 agent
    # 代码或往清单里加了工具之后要重启才挂得上（graph 编译期才注册工具）。
    # 容器模式没有启动器，那个接口会如实报错、提示手动重启。
    launcher_url: str = "http://127.0.0.1:5010"
    workspace_dir: Path = Path(__file__).parent.parent.parent.parent / "workspace"

    # 外部依赖的快速失败（见 core/breaker.py）：连续失败 N 次后，冷却 T 秒内直接
    # 返回失败，不再等满超时（LightRAG 检索 120s / 代码图谱 45s）。
    # fail_max <= 0 关闭熔断，退化成"每次都试"。
    # 注意这里**没有**重试/退避参数：平台不做自动重放，工具失败一律交回模型判断，
    # 理由见 middleware/run_guards.py。原 Phase 7 留下的 retry_* 三件套从没实现过，
    # 2026-09-18 删除。
    circuit_breaker_fail_max: int = 5
    circuit_breaker_reset_timeout: int = 30

    # SQLite (local dev — no PostgreSQL required)
    sqlite_db: str = "smart_test_platform.db"

    # --- Transformation modules (2026-08) ------------------------------------

    # Auth (用户模块)
    auth_token_ttl_hours: int = 72
    auth_default_admin_username: str = "admin"
    auth_default_admin_password: str = "admin123"

    # Feishu CLI / lark-cli (飞书集成)
    lark_cli_bin: str = "lark-cli"
    lark_cli_identity: str = "user"  # --as user | bot
    feishu_mindnote_id: str = ""  # 默认思维导图 ID，用例生成结果保存到这里
    feishu_mindnote_parent_node: str = ""  # 可选：挂到某个父节点下
    # 飞书云空间目录 token（URL 中 drive/folder/ 后面那段）。配置后每次导出
    # 在该目录下自动新建一张思维导图（文档名 = root_text），优先于
    # feishu_mindnote_id 的"固定导图追加"模式——适配每个需求一张导图。
    feishu_folder_token: str = ""
    # 导图样式模板（直线连线等）：预先在飞书建一张调好样式的「干净」导图
    # （只留一个根节点），把 mindnotes URL 里的 token 填到这里。导出时复制
    # 该模板为新文档并逐层写入用例树——副本与追加节点都继承模板样式。
    # 连线样式是飞书文档自身设置，开放 API 无法修改，只能走模板复制。
    # 留空则回退 OPML 导入（飞书默认主题 = 曲线）。模板必须是干净的：
    # mindnotes API 没有删节点能力，业务导图当模板会把旧内容带进副本。
    feishu_template_mindnote_id: str = ""

    # LightRAG (RAG 模块) — 一个知识库一个 lightrag-server 进程，由启动器按
    # services/rag_kbs.py 的注册表拉起（默认库 :5014）。lightrag_base_url 是
    # **默认库**的地址：注册表文件还没落盘时的种子，落盘后以注册表为准。
    lightrag_base_url: str = "http://127.0.0.1:5014"
    lightrag_working_dir: str = "workspace/default/rag"  # 相对项目根；各库按 workspace 分子目录
    # LLM 绑定三件套（LightRAG 做实体抽取/生成用）。留空则各自回退到平台主模型：
    # base_url → LLM_BASE_URL，model → LLM_MODEL，api_key → LLM_API_KEY。
    # 为什么必须能配：以前启动器把 binding 写死成 https://api.deepseek.com/v1，
    # 而 DEEPSEEK_API_KEY 早已换成另一个厂商的 key —— 入库/检索一律 401
    # 「Authentication Fails」，只是知识库当时是空的，没人发现。
    lightrag_llm_base_url: str = ""
    lightrag_llm_model: str = ""  # 留空则跟随 LLM_MODEL（原：跟随 deepseek_model）
    lightrag_llm_api_key: str = ""
    # Embedding 走 OpenAI 兼容 API（默认硅基流动 bge-m3，免费额度即可）
    lightrag_embedding_base_url: str = "https://api.siliconflow.cn/v1"
    lightrag_embedding_model: str = "BAAI/bge-m3"
    lightrag_embedding_api_key: str = ""
    lightrag_embedding_dim: int = 1024

    # codebase-memory MCP (代码图谱模块)
    # 官方版一个二进制同时提供三种用法：stdio MCP（agent 工具）、`cli <tool>` 一锤子
    # 模式（平台自身的索引/查询）、`--ui=true` HTTP 图服务（/api/layout 数据源）——
    # 旧的双 exe（GS 定制版索引 + 官方版出图）在官方 v0.11.0 起已无必要。
    # 默认指向平台自管目录 tools/codebase-memory/，由 services/cbm_install.py 按当前
    # 平台下载官方 release（备用路径：装到别处就把这里指过去）。
    codebase_memory_exe: str = _DEFAULT_CBM_EXE
    # 平台自管安装的版本（release tag）；就绪中心据此判断"该升级了"
    codebase_version: str = "v0.11.0"
    # exe 内置 HTTP 图服务端口（graph-data 代理的数据源）
    codebase_graph_port: int = 9749
    # 定时增量索引（间隔制；只增量已建库仓库，见 scheduler.py / codebase_service.run_incremental_round）
    codebase_schedule_enabled: bool = True
    codebase_interval_hours: int = 24
    # 索引后的「增量影响分析」（无头跑 codebase_agent，会消耗 token，故默认关）
    codebase_analyze_enabled: bool = False

    # Unity 自动化（Unity 自动化模块）—— 通用桥：标准 MCP，见 services/unity_bridge.py。
    # 平台**不自带** Unity 侧任何代码：Unity 工程里装一个 MCP 桥包（如 CoplayDev/unity-mcp
    # 的「MCP for Unity」），由它连到下面的 MCP 服务器；平台只经 MCP 说话。
    # 旧的 LuaRemoteServer（:16666，游戏内 Lua 桥）已删除：它把点击/读文本/造数据
    # 建立在对方游戏的 Lua 框架上，换一款游戏整套作废。
    unity_mcp_url: str = "http://127.0.0.1:5016/mcp"
    unity_mcp_transport: str = "http"   # http | stdio
    unity_mcp_command: str = ""         # stdio 模式的命令；留空用默认 uvx 拉起官方服务器
    unity_mcp_server: str = "auto"      # auto | coplay | ivan | generic（工具名方言，认不准才改）

    # Agent 记忆（harness 风格 Markdown 记忆模块，见 services/memory_service.py）
    # 记忆 = workspace/{space}/memory/ 下的一组可开关的 .md（AGENTS.md /
    # MEMORY.md / USER.md / failures.md / PROJECT.md / DECISIONS.md + 用户自建），
    # 启动时自动落盘种子文件，人工可直接编辑。旧的 EverOS 服务已移除。
    memory_enabled: bool = True  # 总开关：关掉后不向 system prompt 注入任何记忆

    # API automation (接口自动化模块)
    api_script_workspace: str = ""  # default: workspace/default/api-auto
    api_script_python: str = "python"  # interpreter for pytest runs
    api_auto_max_repair: int = 3  # 自修复最大尝试次数

    # Web-UI automation (Web-UI 自动化模块) — 浏览器 UI，经 Playwright CLI 执行
    # 执行器是独立 sidecar（tools/playwright-runner）：后端无 Node 运行时，
    # 浏览器依赖重且与 OS 强绑定，故把工具链隔离在容器里，走 HTTP 调用。
    # 容器内用 service 名（http://playwright:5015），宿主机开发用 127.0.0.1。
    playwright_runner_url: str = "http://127.0.0.1:5015"
    playwright_workspace: str = ""  # default: workspace/default/web-ui-auto
    web_ui_max_repair: int = 2  # 用例执行失败后 AI 自修复的最大尝试次数
    web_ui_default_target_url: str = "https://m.douban.com/movie/"
    web_ui_default_device: str = "iPhone 13"  # 不显式指定设备时的默认值（空串=桌面）
    # 单条用例的 playwright test 超时（秒）与整体 HTTP 超时（秒）
    web_ui_case_timeout_s: int = 90
    web_ui_run_timeout_s: int = 300
    # 产物（截图/trace/报告）是给浏览器直接取的，没法带自定义请求头，
    # 走签名 URL：签名密钥留空则每次启动随机生成（重启后旧分享链接失效，
    # 生产应在 .env 里固定）。
    share_link_secret: str = ""
    web_ui_share_ttl_hours: int = 168  # 分享链接默认有效期（7 天）

    # ------------------------------------------------------------------
    # 用例文档质量门禁（确定性规则，见 services/case_docs_service.py）
    #
    # 严格程度由**平台**决定：过去它来自智能体提交的需求包字段 package_strict，
    # 等于让被检文档自己声明"请宽松地检查我"——写 strict:false 就能让需求覆盖率、
    # 风险覆盖率两道门禁整段跳过。这里换成平台配置，文档无法影响自己的判分标准。
    # ------------------------------------------------------------------
    case_lint_strict: bool = True  # 工作流文档一律按严格模式 lint
    case_evidence_required: bool = True  # 需求包每条需求必须带可在原文核对的 source_quote
    case_normative_recall_floor: float = 0.95  # 规范性语句召回率目标（低于即告警）
    case_numeric_check: bool = True  # 断言里的数值必须能在需求文档中找到
    # 单次复核的输入上限（字符）。超出则按用例边界分块复核——
    # 一份 5 万字的用例文档塞进单次调用既慢又贵，且一处超时整轮白跑。
    case_review_chunk_chars: int = 24000
    case_review_max_issues: int = 40  # 单次复核返回的问题上限，避免报告淹没后续处理
    # 复核模型：留空=跟随平台默认模型。可配成**不同模型家族**做异构验证，
    # 避免生成与复核share同一套偏见（同一模型往往看不出自己写错的地方）。
    case_review_model: str = ""

    # ------------------------------------------------------------------
    # 单轮 run 的调用上限（官方 ModelCallLimitMiddleware / ToolCallLimitMiddleware）
    #
    # 起因是一次实测：一个 run 跑了 35 分钟才结束，期间前端收不到任何事件，界面只能
    # 提示"疑似卡死"。根因是多重的（模型请求没有超时、走了系统代理），但**没有任何
    # 上限**这件事本身是共同的放大器：跑飞的 run 会一直占着 4 个 worker 之一，直到
    # 进程重启为止。官方这两个中间件就是干这个的。
    #
    # 阈值取远高于正常用量：正常生成一轮用例大约 30-60 次模型调用，120 是"明显不对劲"
    # 的界线；工具调用同理。触顶时这一轮**优雅结束**（end / continue），不会把会话挂死。
    # 设 0 = 不限制（回到旧行为）。
    # ------------------------------------------------------------------
    agent_run_model_call_limit: int = 120  # 单轮 run 的模型调用上限
    agent_run_tool_call_limit: int = 300  # 单轮 run 的工具调用上限

    # Eval (测评模块) — Langfuse 闭环：观测(Trace) → 沉淀(Dataset) → 实验(Runner) → 回归(Gate)
    # 参考 dsh-eval-automation 的设计：确定性 traceId 让跑在进程外的 runner
    # 不必查 API 就能把分数挂回正确 trace。
    langfuse_enabled: bool = True
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_base_url: str = "http://127.0.0.1:3000"  # 自建 Langfuse（docker）
    langfuse_environment: str = "eval"
    # 执行中的实时进度：批次现场写在 workspace/default/eval-runs/<batchId>/，
    # 心跳是"进程还活着吗"的证据，静默超过 eval_stale_after_s 即判定已中断。
    eval_run_dir: str = ""
    eval_heartbeat_s: int = 15
    eval_stale_after_s: int = 90
    # judge 用独立的模型端点，缺省回退主 LLM；judge 与被测 agent 应尽量可独立配置
    judge_model: str = ""
    judge_base_url: str = ""
    judge_api_key: str = ""

    # Langfuse 监控（日常智能体使用链路）——与上面的 LANGFUSE_*（测评）**分开**：
    # 日常排查看监控组织，跑测评只看测评组织，两边的 trace 不混在一起。
    # 默认关闭：没配 key 就不上报，不会误写进测评的 Langfuse。
    langfuse_monitor_enabled: bool = False
    langfuse_monitor_base_url: str = ""
    langfuse_monitor_public_key: str = ""
    langfuse_monitor_secret_key: str = ""
    langfuse_monitor_environment: str = "monitor"

    @property
    def database_url(self) -> str:
        db_path = Path(__file__).parent.parent.parent.parent / self.sqlite_db
        return f"sqlite+aiosqlite:///{db_path}"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @model_validator(mode="after")
    def _cbm_exe_blank_means_managed(self) -> "Settings":
        """CODEBASE_MEMORY_EXE 留空 = 用平台自管安装的那个二进制。

        设置页没有这个输入框（引擎由平台按需下载安装），但逃生口留着：想指向自己
        装的版本就在 .env 里写路径；写空（=不存在的老配置清掉、或就绪中心点「改用
        平台自管版本」）时回退到 tools/codebase-memory/，而不是变成空路径——
        空路径会让每次调用都报"文件不存在"，比不配还难查。
        """
        if not self.codebase_memory_exe.strip():
            self.codebase_memory_exe = _DEFAULT_CBM_EXE
        return self

    @model_validator(mode="before")
    @classmethod
    def _blank_non_text_values_fall_back_to_default(cls, data: Any) -> Any:
        # 设置页会把空表单项回写成 ENV= 空值行（如 UNITY_MCP_COMMAND=）。
        # 非字符串字段解析空串会抛 ValidationError，而 Settings() 在 import 时
        # 实例化——任何一个空值都会让 FastAPI/LangGraph 全部起不来。空值视为
        # 未设置，回退字段默认值；str 字段不处理（空串本身是合法语义）。
        if not isinstance(data, dict):
            return data
        fields = cls.model_fields
        return {
            key: value
            for key, value in data.items()
            if not (
                isinstance(value, str)
                and value.strip() == ""
                and key in fields
                and fields[key].annotation is not str
            )
        }


settings = Settings()
