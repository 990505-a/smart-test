"""服务层共用的 LLM 构建入口（Web-UI spec 生成/修复、接口自动化脚本生成等）。

历史上这里直接 ``init_chat_model("deepseek:...")``，只会打到 DeepSeek 官方端点；
一旦平台走自建/第三方 OpenAI 兼容网关（LLM_BASE_URL），这些路径就会拿网关的
key 去请求官方端点，必然 401。现在统一委托给 agents 的模型工厂，与对话主链、
测评裁判同源——都跟随设置页解析出的 effective 配置（DB → .env → 进程环境）。

保留函数名是为了不动调用点；它返回的已不限于 DeepSeek。
"""

from langchain_core.language_models.chat_models import BaseChatModel

from src.app.agents.testcase.model_factory import build_chat_model


def get_deepseek_model() -> BaseChatModel:
    """返回当前生效配置下的对话模型（跟随 LLM_* 设置）。"""
    return build_chat_model()
