"""智能体装配器 (harness) —— 从能力清单构建一个 deepagents 智能体.

``build_agent(capabilities)`` 是唯一的装配入口：

- 通用智能体 = ``build_general_agent()`` —— 挂**清单里的全部**能力（含"专属入口"的
  代码分析），可见性由 ``assembly.json`` 的开关在每次模型调用时决定（``assembly=True``）
- 兼容用的单能力 graph = ``build_agent((CAPABILITY_BY_KEY["unity"],))`` —— 旧会话续跑，
  不挂装配开关（老样子）

装配内容（工具/技能/提示词/中间件/审批/后端）都从这里出来，所以"装配了什么"
在代码里只有一个地方可读 —— 与 ``capabilities.inventory()`` 一一对应。

中间件是**整个平台的固定一套**，不按能力切分：一个通用智能体只该有一套洋葱。
之所以原来每个 agent 各挂各的（testcase 有 PDF 上下文与会话上传目录、其他没有），
是因为它们曾是三个独立 agent；合并后这些差异没有意义 —— 任何一类任务都可能
收到上传的 PDF 或图片。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from deepagents import create_deep_agent as create_agent
from deepagents.backends import FilesystemBackend
from deepagents.backends.composite import CompositeBackend
from langchain.agents.middleware import TodoListMiddleware

from src.app.agents.capabilities import (
    Capability,
    CAPABILITIES,
    CHAT_CAPABILITIES,
    build_interrupt_on,
    build_system_prompt,
    build_upload_namespace,
    resolve_tools,
)
from src.app.agents.testcase.context import FeishuReadonlyMiddleware, ThreadContextMiddleware
from src.app.agents.testcase.model_factory import build_chat_model
from src.app.agents.workspace_backend import (
    ARTIFACTS_ROUTE,
    WorkspaceShellBackend,
    artifacts_backend,
)
from src.app.core.workspace import get_workspace_dir
from src.app.middleware.run_model import RunModelMiddleware
from src.app.middleware.internal_call_isolation import install as _install_isolation
from src.app.middleware.live_model_reload import LiveModelReloadMiddleware
from src.app.middleware.memory_injection import MemoryInjectionMiddleware
from src.app.middleware.pdf_context import PDFContextMiddleware
from src.app.middleware.thinking_effort import ThinkingEffortMiddleware
from src.app.middleware.tool_result_limiter import ToolResultLimiterMiddleware
from src.app.middleware.run_guards import build_run_guards
from src.app.monitoring import MonitorMiddleware

#: 通用智能体的 graph 名 / 工作目录名 / 监控名。旧会话仍指向各自的旧 graph。
GENERAL_AGENT_NAME = "smart_test_agent"
GENERAL_AGENT_DIR = "agent"
GENERAL_AGENT_LABEL = "通用测试助手"

#: 技能库根目录（src/app/skills），经 CompositeBackend 只读挂到 /skills/
_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"

#: 工具结果限长：自定义工具（用例文档、导图导出、图谱查询）不经 FilesystemMiddleware
#: 的驱逐，不限长会让 thread state 无限增长。
_TOOL_RESULT_CHAR_LIMIT = 20_000


def build_llm():
    """模型工厂（设置页改模型下一轮生效）。"""
    return build_chat_model()


def build_backend(default_dir_name: str = GENERAL_AGENT_DIR) -> CompositeBackend:
    """真实路径 shell 后端 + 只读技能库 + 产物路由。

    产物路由是**必须**的：否则 artifacts_root 默认 "/" 配真实路径语义会让摘要
    offload 与超大工具结果写到文件系统根（见 workspace_backend.artifacts_backend）。
    """
    default_dir = get_workspace_dir("default", default_dir_name)
    default_dir.mkdir(parents=True, exist_ok=True)
    return CompositeBackend(
        default=WorkspaceShellBackend(default_dir),
        routes={
            "/skills/": FilesystemBackend(root_dir=_SKILLS_DIR, virtual_mode=True),
            ARTIFACTS_ROUTE: artifacts_backend(),
        },
        artifacts_root="/artifacts",
    )


def build_middleware(agent_name: str = GENERAL_AGENT_NAME,
                     default_dir_name: str = GENERAL_AGENT_DIR,
                     *, backend=None, capabilities: tuple[Capability, ...] = (),
                     general: bool = True, assembly: bool = False) -> list[Any]:
    """平台这一套固定的中间件洋葱（顺序有意义）。

    从外到内：装配开关 → 上下文注入 → 模型热更/思考强度/按会话选模型 → 记忆 → 监控 → 限长 → run 守卫。

    ``assembly=True`` 时额外挂两个（只有对话页的通用智能体用）：工具面按开关过滤 +
    提示词能力段每轮重排 + 技能清单过滤。旧单能力 graph 不挂 —— 它们是历史会话的
    "老样子"，不该被用户在装配页上的开关改变行为。
    """
    middleware: list[Any] = []
    if assembly and backend is not None:
        from src.app.middleware.assembly import AssemblyToolsMiddleware, LiveSkillsMiddleware

        # 这两个中间件不带"装配了什么"的快照：每一轮都从装配目录现读（用户能自己
        # 建智能体/能力、改工具与技能，见 services/assembly_service.py）。
        middleware.append(AssemblyToolsMiddleware())
        middleware.append(LiveSkillsMiddleware(backend=backend, sources=["/skills/"]))
    middleware += [
        # 工作区路径 + 本会话上传目录（testcase 那套是超集，合并后所有任务都挂它）。
        ThreadContextMiddleware(default_dir_name,
                                uploads_namespace=build_upload_namespace()),
        FeishuReadonlyMiddleware(),      # ?feishu=on 时注入 lark-cli 只读检索指引
        # 模型可用的任务清单工具（write_todos）：多步任务先列计划、边做边勾，
        # 前端输入框上方那条「任务 N/M」进度条读的就是它写进 state 的 todos。
        # 它是框架工具（不在装配候选池里），所以装配过滤永远保留它。
        TodoListMiddleware(),
        LiveModelReloadMiddleware(),     # 监听 .env：设置页保存的模型下一轮生效
        ThinkingEffortMiddleware(),      # 每轮 reasoning effort
        RunModelMiddleware(),            # 本轮选了模型预设时，按预设换模型与端点（最靠内，最后写
        PDFContextMiddleware(),          # 注入 PDF 文件上下文
        MemoryInjectionMiddleware(),     # 注入工作区记忆（AGENTS.md/MEMORY.md/…）
        MonitorMiddleware(agent_name),   # Langfuse 上报（未配置则空转）
        ToolResultLimiterMiddleware(char_limit=_TOOL_RESULT_CHAR_LIMIT),
        *build_run_guards(),             # 单轮 run 的模型/工具调用上限
    ]
    return middleware


def build_agent(
    capabilities: tuple[Capability, ...],
    *,
    name: str = GENERAL_AGENT_NAME,
    system_prompt: str | None = None,
    default_dir_name: str = GENERAL_AGENT_DIR,
    general: bool | None = None,
    assembly: bool = False,
):
    """从能力清单装配一个 deepagents 智能体。

    ``shell=True`` 由后端提供（WorkspaceShellBackend 实现了 SandboxBackendProtocol）；
    文件系统工具由 deepagents 的 FilesystemMiddleware 自动挂上，不需要在清单里声明。
    """
    # 摘要 LLM 的输出不流式泄进主对话（此前只有部分模块装了，靠 import 副作用覆盖）
    _install_isolation()

    backend = build_backend(default_dir_name)
    return create_agent(
        model=build_llm(),
        tools=resolve_tools(capabilities),
        backend=backend,
        skills=["/skills/"],
        middleware=build_middleware(name, default_dir_name, backend=backend,
                                    capabilities=capabilities, general=general if general is not None else True,
                                    assembly=assembly),
        interrupt_on=build_interrupt_on(capabilities),
        system_prompt=system_prompt or build_system_prompt(
            capabilities, general=general),
        name=name,
    )


def build_general_agent():
    """对话页的 graph —— 服务**任意多个用户定义的智能体**。

    工具面挂清单里**全部**能力的工具（含代码分析的图谱四件套），可见性由装配目录
    （``workspace/<space>/assembly.json``）在每次模型调用时按 ``configurable.agent_id``
    现算：换个智能体、加一项能力、卸一个工具，都不用重启 —— graph 编译期把工具都注册
    好，过滤发生在每次模型调用（见 ``middleware/assembly.py``）。
    """
    return build_agent(CAPABILITIES, name=GENERAL_AGENT_NAME, general=True, assembly=True)
