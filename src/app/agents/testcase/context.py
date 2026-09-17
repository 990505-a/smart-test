"""TestCase Agent context schema and context injection middleware."""

from dataclasses import dataclass, field
from typing import Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse


@dataclass
class TestCaseAgentContext:
    """Runtime context for the TestCase Agent.

    Passed from frontend via stream.submit({ messages, context }).
    Injected into system prompt by ContextInjectionMiddleware so tools
    can use these values without asking the user.
    """
    project_identifier: str = ""
    folder_id: str = ""
    current_user_id: str = "00000000-0000-0000-0000-000000000001"


class ContextInjectionMiddleware(AgentMiddleware):
    """Injects runtime context (project, folder, user) into the system prompt.

    Matches the classroom's APIContextInjectionMiddleware pattern:
    reads fields from request.runtime.context and appends them to system_message
    so the agent automatically uses correct project/folder when calling tools.
    """

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        ctx = request.runtime.context
        if not ctx:
            return await handler(request)

        project_id = getattr(ctx, "project_identifier", "") or ""
        folder_id = getattr(ctx, "folder_id", "") or ""

        if not project_id and not folder_id:
            return await handler(request)

        context_block = f"""

---
## 运行时上下文

**当前会话参数（调用工具时必须使用）：**
- `project_identifier`: `{project_id}`
- `folder_id`: `{folder_id}`

**重要提示：** 这些参数由系统自动注入，不要询问用户提供。
---
"""
        if isinstance(request.system_message.content, list):
            request.system_message.content = [
                *request.system_message.content,
                {"type": "text", "text": context_block},
            ]
        else:
            request.system_message.content = request.system_message.content + context_block

        return await handler(request)


class FeishuReadonlyMiddleware(AgentMiddleware):
    """注入只读需求检索指引（默认开启，会话不再有开关）。

    2026-09：前端去掉了「飞书检索」开关——它默认就该是开的（需求经常在飞书
    文档里，agent 主动去查比让用户每次手动开要好）。只要 configurable 里没有
    显式 ``feishu_cli="off"``（旧客户端才会传），就注入这份行为指引。
    「只读」的硬约束不在提示词，而在权限门：lark-cli 写入类命令一律弹审批
    （见 middleware/permission_gate._lark_segment_safe）。
    """

    _CONTEXT_BLOCK = """

---
## 飞书需求检索（默认开启，严格只读）

- 需求澄清/补充阶段，当上传文档信息不足、用户提到需求在飞书，或需要交叉
  验证需求细节时，可按 `/skills/lark-drive`（`drive +search` 搜文档）与
  `/skills/lark-doc`（`docs +fetch` 读正文）的技能指引用 lark-cli 检索
  飞书云文档。
- **严格只读**：只允许搜索、读取类操作；创建、修改、删除、上传、移动、
  权限变更等写操作一律禁止（权限门会把这类命令转人工审批）。
- 从飞书读到的需求证据必须记入需求包 `source_refs` / `source_manifest`
  （附文档链接），并在回复中向用户说明出处。
- lark-cli 未安装或未登录时，告知用户到设置页完成飞书登录即可，不要重试。
---
"""

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        from langgraph.config import get_config

        try:
            configurable = (get_config() or {}).get("configurable") or {}
        except RuntimeError:
            configurable = {}

        if str(configurable.get("feishu_cli", "")).strip().lower() == "off":
            return await handler(request)

        if isinstance(request.system_message.content, list):
            request.system_message.content = [
                *request.system_message.content,
                {"type": "text", "text": self._CONTEXT_BLOCK},
            ]
        else:
            request.system_message.content = (
                request.system_message.content + self._CONTEXT_BLOCK
            )

        return await handler(request)


class ThreadContextMiddleware(AgentMiddleware):
    """注入当前工作区与会话上传目录（绝对路径）。

    路径语义在 2026-09 改为**真实路径**（见 agents/workspace_backend.py）：
    文件和 shell 都按真实路径工作，所以这里给的是磁盘上的绝对路径，而不是
    过去的虚拟路径 ``/uploads/{thread_id}/``。

    工作区说明复用 ``middleware/workspace_context.py``（其他智能体也挂它），
    这里只补"本会话的上传目录"这一条 testcase 特有的信息。
    """

    def __init__(self, agent_name: str = "testcase") -> None:
        self._agent_name = agent_name

    def _uploads_dir(self) -> tuple[str, str]:
        from langgraph.config import get_config

        from src.app.core.config import settings
        from src.app.core.workspace import get_space_id

        try:
            config = get_config()
        except RuntimeError:
            return "", ""
        thread_id = (config.get("configurable") or {}).get("thread_id", "") or ""
        if not thread_id:
            return "", ""
        base = settings.workspace_dir / get_space_id() / self._agent_name
        return str((base / "uploads" / thread_id).resolve()), thread_id

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        from src.app.middleware.workspace_context import workspace_context_block

        uploads, thread_id = self._uploads_dir()
        if not thread_id:
            return await handler(request)

        context_block = workspace_context_block(self._agent_name) + f"""

### 本会话上传文件目录

- 上传文件目录：`{uploads}`
- 读取时用**绝对路径**（用户消息里已给出具体文件的完整路径），例如
  `read_file("{uploads}/文件名")`。
- **不要**去列别的会话的上传目录；把具体文件路径直接写进子智能体任务描述里。
---
"""

        if isinstance(request.system_message.content, list):
            request.system_message.content = [
                *request.system_message.content,
                {"type": "text", "text": context_block},
            ]
        else:
            request.system_message.content = request.system_message.content + context_block

        return await handler(request)
