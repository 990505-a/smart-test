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


class ThreadContextMiddleware(AgentMiddleware):
    """Injects thread_id into system prompt so agent knows its upload directory.

    Reads thread_id from LangGraph configurable and tells the agent exactly
    which directory contains the files uploaded in the current conversation.
    This prevents the agent from listing files from other threads.
    """

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        from langgraph.config import get_config

        thread_id = ""
        try:
            config = get_config()
            thread_id = config.get("configurable", {}).get("thread_id", "")
        except RuntimeError:
            pass

        if not thread_id:
            return await handler(request)

        context_block = f"""

---
## 会话上传目录（系统自动注入，不要询问用户）

当前会话上传文件目录: `/uploads/{thread_id}/`

**查找本会话上传的文件时，必须使用以下路径：**
- 查看文件列表: `ls("/uploads/{thread_id}/")`
- 读取文件内容: `read_file("/uploads/{thread_id}/文件名")`

**绝对不要使用 `ls("/uploads/")` 查看其他会话的文件。**
将具体文件路径直接传入子智能体任务描述，不要让子智能体自行搜索。
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
