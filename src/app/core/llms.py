from langchain.chat_models import init_chat_model
from src.app.core.config import settings


def get_deepseek_model():
    return init_chat_model(
        f"deepseek:{settings.deepseek_model}",
        api_key=settings.deepseek_api_key,
    )
