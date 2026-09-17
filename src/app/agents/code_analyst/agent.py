"""Code Analysis Agent (代码分析智能体).

与用例生成智能体（testcase）的差异：不产出测试用例，专注代码分析——
功能定位、调用链追踪、影响面评估、实现解读、风险点识别。

工具策略（双轨）：
- 代码图谱（codebase-memory）：graph_search 定位符号 → trace_symbol
  追调用链 → read_symbol 按全名读源码；适合"谁调用谁/在哪定义"类问题
- 原生文件工具（真实路径，cwd = 本次对话挂载的工作区）：grep/glob/read_file/ls
  逐行核实；适合"具体实现/上下文细节"类问题，图谱未建库时是唯一路径

架构（精简自 testcase，去掉了用例/记忆/飞书等无关层）：
    |-- ThinkingEffort / LiveModelReload
    |   |-- ToolResultLimiter(20k) / MessageRepair / PermissionGate
    |   |-- LLM (settings 驱动，model_factory)
Backend: CompositeBackend
    default -> WorkspaceShellBackend：本次对话挂载的工作区（真实路径，见
               agents/workspace_backend.py），未挂载时退回
               workspace/default/code_analyst/
    /skills/ -> 平台技能库（本智能体暂未挂载技能，路由留空）
"""

from pathlib import Path

from deepagents import create_deep_agent as create_agent
from deepagents.backends import CompositeBackend, FilesystemBackend
from dotenv import load_dotenv

from app.agents.workspace_backend import WorkspaceShellBackend
from app.agents.code_analyst.tools import (
    graph_search, read_symbol, repo_architecture, trace_symbol,
)
from app.middleware.live_model_reload import LiveModelReloadMiddleware
from app.middleware.memory_injection import MemoryInjectionMiddleware
from app.monitoring import MonitorMiddleware
from app.middleware.workspace_context import WorkspaceContextMiddleware
from app.middleware.message_repair import MessageRepairMiddleware
from app.middleware.permission_gate import build_permission_middleware
from app.middleware.thinking_effort import ThinkingEffortMiddleware
from app.middleware.tool_result_limiter import ToolResultLimiterMiddleware
from app.agents.testcase.model_factory import build_chat_model
from app.core.workspace import get_workspace_dir

load_dotenv()

# ============================================================================
# LLM（与用例智能体同一套 settings 驱动工厂：设置页改模型下一轮生效）
# ============================================================================
llm = build_chat_model()

# ============================================================================
# Backend：本次对话挂载的工作区（真实路径语义，见 agents/workspace_backend.py）
# ============================================================================
_workspace_dir = get_workspace_dir("default", "code_analyst")
_workspace_dir.mkdir(parents=True, exist_ok=True)
file_backend = WorkspaceShellBackend(_workspace_dir)
composite_backend = CompositeBackend(
    default=file_backend,
    routes={},
)

# ============================================================================
# System prompt — 代码分析专家（区别于用例生成：回答问题/输出分析，不生成用例）
# ============================================================================
SYSTEM_PROMPT = """\
你是一位资深游戏项目代码分析专家，负责对用户指定的代码做分析（Unity + Lua 客户端、GS 服务端）：
功能定位、调用链追踪、影响面评估、实现解读、风险与坏味道识别。**你不生成测试用例**——那是用例生成智能体的职责。

# 工作方式（双轨检索）

1. **代码图谱优先**（回答"在哪定义/谁调用谁/影响范围/仓库全貌"）：
   - 仓库概览/架构/模块划分类问题 → 先 `repo_architecture`
   - `graph_search` 定位符号（知道大致名字用字面检索；只知道业务含义用 semantic=true）
   - `trace_symbol` 追调用链（inbound=谁调用它，outbound=它调用谁，depth 1-3）
   - `read_symbol` 按 qualified_name 直接读符号源码
2. **文件工具核实**（回答"具体怎么实现/边界细节"）：
   - 本会话的工作区是 shell 的 cwd，相对路径相对它解析；要分析代码时用绝对路径
     或先 `ls` 找到目标目录，再用 grep/glob/read_file 逐行确认
   - 图谱未建库时全部改走文件工具，不要反复重试图谱工具

**分析某个具体系统/模块时的标准流程**（grep 找到文件只是第一步）：
grep/ls 定位系统文件 → **必须** `graph_search` 拿到该系统的核心符号（函数/类）→
对入口/核心函数 **必须** `trace_symbol` 理清调用关系（协议入口→处理链→数据落地）→
`read_file`/`read_symbol` 核实关键实现细节。
调用链结论（"A 由 B/C/D 调用"、"改动 X 影响 Y"）优先以图谱为准，grep 只做佐证。

# 硬性规则

- **用真实路径**：文件工具收绝对路径（如 `/Users/you/proj/src/a.lua`），相对路径按工作区解析。
  代码不在工作区里时直接用它的绝对路径读——你有权访问工作区之外的目录。
- **`execute` 就是本机 shell**（cwd = 工作区）：git log/grep/find 都能用，命令里也用真实路径。
  权限档为 workspace_write 时，非只读命令会转人工审批；被拒就换只读手段（ls/read_file/grep）。

# 产出原则

- 所有输出使用中文；**每个结论必须标注证据**：`文件路径:行号` 或 `符号名（图谱）`
- 回答结构：先给结论，再给依据；涉及调用链时用 `A → B → C` 链式描述并标注各环节位置
- 影响面分析要区分"直接调用方"与"间接影响"，并指出不确定的部分
- 检索结果不足以确定时明确说"现有证据不足以确定"，并给出建议的下一步检索词；不要编造代码内容
- 用户要求输出分析报告时，把报告保存为 Markdown 到当前工作区（相对路径即可），并在回复中给出文件名
- 分析文档写入工作区；不要修改被测项目的源码文件
"""


# ============================================================================
# Tools & middleware
# ============================================================================
_all_tools = [repo_architecture, graph_search, trace_symbol, read_symbol]
for t in _all_tools:
    t.handle_tool_error = True

tool_result_limiter = ToolResultLimiterMiddleware(char_limit=20_000)

agent = create_agent(
    model=llm,
    tools=_all_tools,
    backend=composite_backend,
    middleware=[
        LiveModelReloadMiddleware(),
        ThinkingEffortMiddleware(),
        MemoryInjectionMiddleware(),
        WorkspaceContextMiddleware("code_analyst"),  # 注入工作区路径（绝对路径提示）  # 注入工作区记忆（AGENTS.md/MEMORY.md/…）
        MonitorMiddleware("code_analyst_agent"),  # 日常链路上报监控 Langfuse
        tool_result_limiter,
        MessageRepairMiddleware(),
        build_permission_middleware(),
    ],
    system_prompt=SYSTEM_PROMPT,
)
