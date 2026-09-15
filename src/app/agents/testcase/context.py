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
    """会话开启「飞书检索」开关时，注入只读需求检索指引。

    前端输入框开关（?feishu=on → configurable.feishu_cli="readonly"）控制
    智能体是否主动去飞书找需求；本中间件只在开启时注入行为指引。
    「只读」的硬约束不在提示词，而在权限门：lark-cli 写入类命令一律
    弹审批（见 middleware/permission_gate._lark_segment_safe）。
    """

    _CONTEXT_BLOCK = """

---
## 飞书需求检索（会话开关已开启，严格只读）

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
            return await handler(request)

        if str(configurable.get("feishu_cli", "")).strip().lower() != "readonly":
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
