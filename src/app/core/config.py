from pathlib import Path
from typing import Any

from pydantic import model_validator
from pydantic_settings import BaseSettings


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
    # --- Vision model (图片内容时切换；全留空则复用上面的文本模型) ------------
    vision_model: str = ""  # e.g. gpt-4o / glm-4.5v; empty -> reuse text model
    vision_base_url: str = ""  # empty -> llm_base_url（都不填则视为 OpenAI 官方端点）
    vision_api_key: str = ""  # empty -> llm_api_key
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
    doubao_api_key: str = ""
    openai_api_key: str = ""  # GPT-4o multimodal model (Phase 4)
    enable_pdf_multimodal: bool = True  # Multimodal mode toggle (Phase 4)
    langgraph_api_url: str = "http://localhost:5011"
    workspace_dir: Path = Path(__file__).parent.parent.parent.parent / "workspace"

    # Resilience settings (Phase 7)
    circuit_breaker_fail_max: int = 5
    circuit_breaker_reset_timeout: int = 30
    retry_max_attempts: int = 3
    retry_initial_delay: float = 1.0
    retry_max_delay: float = 30.0

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

    # LightRAG (RAG 模块) — 独立 lightrag-server 进程，由启动器管理 (:5014)
    lightrag_base_url: str = "http://127.0.0.1:5014"
    lightrag_working_dir: str = "workspace/default/rag"  # 相对项目根目录
    lightrag_llm_model: str = ""  # 留空则跟随 deepseek_model
    # Embedding 走 OpenAI 兼容 API（默认硅基流动 bge-m3，免费额度即可）
    lightrag_embedding_base_url: str = "https://api.siliconflow.cn/v1"
    lightrag_embedding_model: str = "BAAI/bge-m3"
    lightrag_embedding_api_key: str = ""
    lightrag_embedding_dim: int = 1024

    # codebase-memory MCP (代码图谱模块)
    # stdio 直连 exe（按需拉起）：GS/Lua 定制版（项目名按仓库路径推导，见 codebase_service.project_name）。
    # 注意：GS 版构建时未内嵌 UI 资源，HTTP 图服务起不来；图守护用下面 graph_exe 指向的官方版（两者共享索引存储）
    codebase_memory_exe: str = "C:/codebase/cbm-gs.exe"
    # 图守护进程用的 exe（--ui=true HTTP 服务，/api/layout 数据源）
    codebase_graph_exe: str = "C:/codebase/codebase-memory-mcp/build/c/codebase-memory-mcp.exe"
    # exe 内置 HTTP 图服务端口（graph-data 代理的数据源）
    codebase_graph_port: int = 9749
    # 定时增量索引（间隔制；只增量已建库仓库，见 scheduler.py / codebase_service.run_incremental_round）
    codebase_schedule_enabled: bool = True
    codebase_interval_hours: int = 24

    # Game project (代码分析 / UI 自动化)
    game_repo_path: str = "E:/m72-publish/m72"
    game_client_repo: str = "E:/m72-publish/m72/client"

    # Unity UI automation (UI 自动化模块)
    unity_host: str = "127.0.0.1"
    unity_port: int = 16666

    # EverOS memory (记忆模块) — 本地 EverOS server，按需拉起（见 everos_service）
    # Windows 说明：EverOS 官方不支持 Windows（fcntl），启动时通过
    # src/app/everos_compat/fcntl.py 垫片 + tools/patch_everos.py 补丁拉起。
    everos_enabled: bool = True
    everos_host: str = "127.0.0.1"
    everos_port: int = 9631
    everos_root: str = "workspace/default/memory"  # 相对项目根目录（MD 单一事实源，进 git）
    # 记忆隔离维度（平台单机单用户，固定三个维度即可）
    everos_app_id: str = "smart-test"
    everos_project_id: str = "default"
    everos_user_id: str = "platform"
    # LLM 三项留空则复用 llm_*（再回退 deepseek_*）
    everos_llm_model: str = ""
    everos_llm_base_url: str = ""
    everos_llm_api_key: str = ""
    # Embedding 三项：key 留空 = keyword-only 模式（向量/混合检索与反思、
    # 技能蒸馏禁用）；base/model 留空则回退 lightrag_embedding_*（硅基流动）。
    # 填 OpenAI 官方 key 时用 https://api.openai.com/v1 + text-embedding-3-small
    everos_embedding_api_key: str = ""
    everos_embedding_base_url: str = ""
    everos_embedding_model: str = ""

    # API automation (接口自动化模块)
    api_script_workspace: str = ""  # default: workspace/default/api-auto
    api_script_python: str = "python"  # interpreter for pytest runs
    api_auto_max_repair: int = 3  # 自修复最大尝试次数

    @property
    def database_url(self) -> str:
        db_path = Path(__file__).parent.parent.parent.parent / self.sqlite_db
        return f"sqlite+aiosqlite:///{db_path}"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @model_validator(mode="before")
    @classmethod
    def _blank_non_text_values_fall_back_to_default(cls, data: Any) -> Any:
        # 设置页会把空表单项回写成 ENV= 空值行（如 UNITY_PORT=）。
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
