"""工作区上下文注入：告诉 agent「本次对话的目录在哪」。

为什么需要单独说：文件工具的 schema 要求**绝对路径**，而平台的工作区是
`configurable.workspace_path` 传进来的（每个会话可能不同）。不注入的话，
agent 只能猜——`ls(".")` / `ls("/")` 在真实路径语义下会列出文件系统根目录，
而不是工作区（这不是错误，但它显然不是用户想要的）。

testcase 智能体有更细的版本（还要说会话上传目录，见 agents/testcase/context.py）；
其他智能体挂这个通用的。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse

from src.app.agents.workspace_backend import mounted_workspace_path, resolve_workspace_dir
from src.app.core.config import settings
from src.app.core.workspace import get_space_id


def workspace_context_block(agent_name: str, default_dir: str | None = None) -> str:
    """拼出工作区说明块（未挂载时说明用的是平台默认目录）。"""
    default = default_dir or str(settings.workspace_dir / get_space_id() / agent_name)
    mounted = mounted_workspace_path()
    path = resolve_workspace_dir(default)
    source = "用户挂载的工作区" if mounted else "平台默认工作区（本次对话未挂载目录）"
    return f"""

---
## 工作区（系统自动注入，不要询问用户）

- 当前工作区（{source}，绝对路径，也是 shell 的 cwd）：`{path}`
- **列目录/读文件用绝对路径**：`ls("{path}")`、`read_file("{path}/某个文件")`。
  注意 `ls(".")` 与 `ls("/")` 会去列文件系统根目录，不是工作区。
- `glob` / `grep` 不传路径时默认就在工作区里搜；相对路径按工作区解析。
- 工作区只是你干活的地方，不是必须读的仓库；需要看工作区之外的路径时直接用它的绝对路径。
---
"""


class WorkspaceContextMiddleware(AgentMiddleware):
    """把当前工作区路径注入 system prompt（每个模型调用前刷新）。"""

    def __init__(self, agent_name: str) -> None:
        self.agent_name = agent_name

    def _block(self) -> str:
        return workspace_context_block(self.agent_name)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        block = self._block()
        if isinstance(request.system_message.content, list):
            request.system_message.content = [
                *request.system_message.content,
                {"type": "text", "text": block},
            ]
        else:
            request.system_message.content = request.system_message.content + block
        return await handler(request)
