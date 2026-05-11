from langchain.chat_models import init_chat_model


def get_deepseek_model():
    return init_chat_model("deepseek:deepseek-chat")
