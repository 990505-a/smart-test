"""Web Automation Agent stub - Phase 1 skeleton."""
from pathlib import Path
from deepagents import create_deep_agent as create_agent
from deepagents.backends import FilesystemBackend
from langchain.chat_models import init_chat_model
from dotenv import load_dotenv

load_dotenv()

llm = init_chat_model("deepseek:deepseek-chat")
workspace_dir = Path(__file__).parent.parent.parent.parent.parent / "workspace"
file_backend = FilesystemBackend(root_dir=workspace_dir, virtual_mode=True)

agent = create_agent(
    model=llm,
    tools=[],
    backend=file_backend,
    middleware=[],
    system_prompt=(
        "你是智能测试平台的Web自动化测试助手。"
        "在当前初始阶段，请友好地回应用户的查询。"
        "完整的Web自动化测试功能将在后续阶段添加。"
    ),
)
