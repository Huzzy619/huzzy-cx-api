"""LLM pipeline builder: LiveKit Inference with an optional self-hosted model."""

from __future__ import annotations

from livekit.agents import inference, llm
from livekit.plugins import openai

from voice_worker.config import get_settings
from voice_worker.constants import DEFAULT_LLM, DEFAULT_LLM_FALLBACK
from voice_worker.schemas import AgentConfig


class LLMBuilder:
    def __init__(self, config: AgentConfig) -> None:
        self._config = config

    def build(self) -> llm.LLM | llm.FallbackAdapter:
        primary_model = self._config.model or DEFAULT_LLM
        settings = get_settings()

        if settings.custom_llm_model and primary_model == settings.custom_llm_model:
            primary: llm.LLM = openai.LLM(
                model=primary_model,
                base_url=settings.custom_llm_base_url or None,
                api_key=settings.custom_llm_api_key or None,
                temperature=self._config.temperature,
            )
        else:
            primary = inference.LLM(model=primary_model)

        return llm.FallbackAdapter(
            [primary, inference.LLM(model=DEFAULT_LLM_FALLBACK)]
        )
