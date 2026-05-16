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
