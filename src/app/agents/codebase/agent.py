"""Codebase Analysis Agent (代码图谱 · 代码分析智能体).

目标仓库由 ``configurable.workspace_path`` 传入（repo.repo_path，同时就是
shell 的 cwd）。

现在只剩**一条**使用路径：定时任务触发的无头「增量影响分析」——full_access 档
执行、无人审批，报告正文即最后一条 AI 消息
（见 services/codebase_analysis_service.py）。

原来还有「代码图谱页 → AI 分析 Tab」的多轮问答，2026-09 删除（与对话页重复）：
交互式代码问答统一走对话页 —— 输入框旁的「代码图谱仓库」选择器挂一个仓库，通用智能体
用清单里 ``codebase`` 能力的那套工具（同样是这 4 个）。本 graph 保留下来只是
因为无头分析要跑它。

工具策略（双轨）：
- 代码图谱（codebase-memory）：graph_search 定位符号 → trace_symbol
  追调用链 → read_symbol 按全名读源码；适合"谁调用谁/在哪定义"类问题
- 原生文件工具（真实路径，cwd = 选中仓库）：grep/glob/read_file/ls
  逐行核实；适合"具体实现/上下文细节"类问题，图谱未建库时是唯一路径
"""

from deepagents import create_deep_agent as create_agent
from deepagents.backends import CompositeBackend
from dotenv import load_dotenv

from src.app.agents.codebase.tools import (
    graph_search, read_symbol, repo_architecture, trace_symbol,
)
from src.app.agents.workspace_backend import (
    ARTIFACTS_ROUTE,
    WorkspaceShellBackend,
    artifacts_backend,
)
from src.app.middleware.live_model_reload import LiveModelReloadMiddleware
from src.app.middleware.memory_injection import MemoryInjectionMiddleware
from src.app.middleware.permission_gate import build_interrupt_on
from src.app.middleware.run_guards import build_run_guards
from src.app.middleware.thinking_effort import ThinkingEffortMiddleware
from src.app.middleware.tool_result_limiter import ToolResultLimiterMiddleware
from src.app.middleware.workspace_context import WorkspaceContextMiddleware
from src.app.monitoring import MonitorMiddleware
from src.app.agents.testcase.model_factory import build_chat_model
from src.app.core.workspace import get_workspace_dir

load_dotenv()

# ============================================================================
# LLM（与用例智能体同一套 settings 驱动工厂：设置页改模型下一轮生效）
# ============================================================================
llm = build_chat_model()

# ============================================================================
# Backend：默认目录 = 平台工作区的 codebase/ 下；实际 cwd 由
# configurable.workspace_path（= 选中的仓库）覆盖，见 workspace_backend。
# ============================================================================
_workspace_dir = get_workspace_dir("default", "codebase")
_workspace_dir.mkdir(parents=True, exist_ok=True)
file_backend = WorkspaceShellBackend(_workspace_dir)
composite_backend = CompositeBackend(
    default=file_backend,
    # 本智能体不挂技能（只做代码问答，没有对应技能），但**必须**挂产物路由：
    # 否则 artifacts_root 默认 "/" + 真实路径语义会让摘要 offload 与超大工具
    # 结果写到文件系统根（见 workspace_backend.artifacts_backend 的说明）。
    routes={ARTIFACTS_ROUTE: artifacts_backend()},
    artifacts_root="/artifacts",
)

# ============================================================================
# System prompt — 代码分析专家（回答问题/输出分析，不生成用例）
# ============================================================================
SYSTEM_PROMPT = """\
你是一位资深游戏项目代码分析专家，负责对当前仓库的代码做分析（Unity + Lua 客户端、GS 服务端）：
功能定位、调用链追踪、影响面评估、实现解读、风险与坏味道识别。**你不生成测试用例**——那是用例生成智能体的职责。

# 当前仓库（系统自动注入，不要询问用户）

会话的运行目录就是本仓库根目录（shell 的 cwd，相对路径相对它解析）；
文件工具收绝对路径，也可以用相对路径。分析所需的其他路径（依赖、SDK、
上游代码）直接用它自己的绝对路径读——你有权访问工作目录之外的路径。

# 工作方式（双轨检索）

1. **代码图谱优先**（回答"在哪定义/谁调用谁/影响范围/仓库全貌"）：
   - 仓库概览/架构/模块划分类问题 → 先 `repo_architecture`
   - `graph_search` 定位符号（知道大致名字用字面检索；只知道业务含义用 semantic=true）
   - `trace_symbol` 追调用链（inbound=谁调用它，outbound=它调用谁，depth 1-3）
   - `read_symbol` 按 qualified_name 直接读符号源码
2. **文件工具核实**（回答"具体怎么实现/边界细节"）：
   - 用 grep/glob/read_file 逐行确认；要搜整个仓库时用相对路径或仓库绝对路径
   - 图谱未建库时全部改走文件工具，不要反复重试图谱工具

**分析某个具体系统/模块时的标准流程**（grep 找到文件只是第一步）：
grep/ls 定位系统文件 → **必须** `graph_search` 拿到该系统的核心符号（函数/类）→
对入口/核心函数 **必须** `trace_symbol` 理清调用关系（协议入口→处理链→数据落地）→
`read_file`/`read_symbol` 核实关键实现细节。
调用链结论（"A 由 B/C/D 调用"、"改动 X 影响 Y"）优先以图谱为准，grep 只做佐证。

# 硬性规则

- **`execute` 就是本机 shell**（cwd = 仓库根目录）：git log/grep/find 都能用。
  权限档为受限档时，非只读命令会转人工审批；被拒就换只读手段（ls/read_file/grep）。
- **绝不修改被分析仓库的任何文件**：你能读写，但分析任务只读。需要落盘产物时
  写到产物目录（如 `/artifacts/...`），不要写进仓库。

# 产出原则

- 所有输出使用中文；**每个结论必须标注证据**：`文件路径:行号` 或 `符号名（图谱）`
- 回答结构：先给结论，再给依据；涉及调用链时用 `A → B → C` 链式描述并标注各环节位置
- 影响面分析要区分"直接调用方"与"间接影响"，并指出不确定的部分
- 检索结果不足以确定时明确说"现有证据不足以确定"，并给出建议的下一步检索词；不要编造代码内容
- **被要求输出报告时，把报告正文完整写在你的回复里**（调用方直接取最后一条回复
  作为报告正文）；表格、分级标题、清单都可以用 Markdown
"""


# ============================================================================
# Tools & middleware
# ============================================================================
_all_tools = [repo_architecture, graph_search, trace_symbol, read_symbol]
for t in _all_tools:
    t.handle_tool_error = True

tool_result_limiter = ToolResultLimiterMiddleware(char_limit=20_000)

# 内部调用隔离：摘要 LLM 的输出不流式泄进主对话。
# 过去这里漏了——它只在 testcase/unity/webui 三个 agent 里调用，靠"别的模块先
# import 过"的副作用覆盖到本进程；单独起 codebase 时摘要就会漏进对话。
from src.app.middleware.internal_call_isolation import install as _install_isolation

_install_isolation()

agent = create_agent(
    model=llm,
    tools=_all_tools,
    backend=composite_backend,
    middleware=[
        LiveModelReloadMiddleware(),
        ThinkingEffortMiddleware(),
        MemoryInjectionMiddleware(),
        WorkspaceContextMiddleware("codebase"),  # 注入当前仓库路径（绝对路径提示）
        MonitorMiddleware("codebase_agent"),  # 日常链路上报监控 Langfuse
        tool_result_limiter,
        # 曾在这里的 MessageRepairMiddleware 已删：官方 PatchToolCallsMiddleware
        # 默认就在 deepagents 栈里（且额外覆盖 invalid_tool_calls）。
        *build_run_guards(),  # 官方：单轮 run 的模型/工具调用上限
    ],
    # 审批走官方参数：execute 只读白名单免审批；文件写入/删除在免审批区内
    # 免审批、越界弹卡片（受限档），完全访问档全放行。无人值守的定时分析
    # 走完全访问档，因此不会挂起等审批。
    interrupt_on=build_interrupt_on(),
    system_prompt=SYSTEM_PROMPT,
)
