from functools import lru_cache

from langchain.chat_models import init_chat_model

from app.config import settings


@lru_cache(maxsize=1)
def get_chat_model():
    if not settings.llm_api_key:
        raise RuntimeError("LLM_API_KEY is not configured")

    return init_chat_model(
        model=settings.llm_model,
        model_provider=settings.llm_provider,
        api_key=settings.llm_api_key.get_secret_value(),
        temperature=0,
    )