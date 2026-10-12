"""Worker-side LangChain chat-model factory.

The voice pipeline talks to LiveKit Inference directly; the LangGraph
supervisor/RAG graphs use LangChain. Model selection is env-driven and never
falls back silently to an unauthorised provider.
"""

from __future__ import annotations

from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from voice_worker.config import get_settings
from voice_worker.constants import DEFAULT_LLM

_DEFAULT_LANGCHAIN_MODEL = "openai:gpt-4o-mini"


def create_chat_model(
    *,
    model_name: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 1000,
    **kwargs: Any,
) -> BaseChatModel:
    settings = get_settings()
    if model_name:
        model = model_name if ":" in model_name else f"openai:{model_name}"
    elif settings.custom_llm_model:
        model = settings.custom_llm_model
    else:
        model = _DEFAULT_LANGCHAIN_MODEL

    if ":" not in model:
        model = f"openai:{model}"

    extra: dict[str, Any] = {}
    provider = model.split(":", 1)[0]
    if provider == "openai" and settings.custom_llm_base_url:
        extra["base_url"] = settings.custom_llm_base_url
        if settings.custom_llm_api_key:
            extra["api_key"] = settings.custom_llm_api_key

    return init_chat_model(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        **extra,
        **kwargs,
    )


DEFAULT_MODEL = DEFAULT_LLM
