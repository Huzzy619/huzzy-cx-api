"""AgentSession builder - composes pipeline components and session options."""

from __future__ import annotations

import logging
from typing import Any

from livekit.agents import AgentSession

from voice_worker.builders.context import VoiceAgentContext
from voice_worker.builders.pipeline import (
    LLMBuilder,
    STTBuilder,
    TTSBuilder,
    TurnHandlingBuilder,
)
from voice_worker.builders.utils import resolve_language
from voice_worker.constants import DEFAULT_LLM

logger = logging.getLogger(__name__)


class SessionBuilder:
    def __init__(self, ctx: VoiceAgentContext) -> None:
        self._ctx = ctx

    def build(self) -> AgentSession:
        from livekit.plugins import silero

        config = self._ctx.config
        loaded_vad = silero.VAD.load()
        session_kwargs: dict[str, Any] = {
            "stt": STTBuilder(config, vad_instance=loaded_vad).build(),
            "llm": LLMBuilder(config).build(),
            "tts": TTSBuilder(config).build(),
            "vad": loaded_vad,
            "turn_handling": TurnHandlingBuilder(config).build(),
        }

        self._apply_timing_options(session_kwargs)
        self._apply_call_options(session_kwargs)

        logger.info(
            "Built AgentSession for organisation=%s session=%s "
            "(language=%s, model=%s)",
            self._ctx.organisation_id,
            self._ctx.voice_session_id,
            resolve_language(config),
            config.model or DEFAULT_LLM,
        )
        return AgentSession(**session_kwargs)

    def _apply_timing_options(self, session_kwargs: dict[str, Any]) -> None:
        speech = self._ctx.config.speech_config
        if speech:
            session_kwargs["user_away_timeout"] = float(
                speech.silence_reminder_interval
            )

    def _apply_call_options(self, session_kwargs: dict[str, Any]) -> None:
        call = self._ctx.config.call_config
        if not call:
            return
        if call.end_call_after_silence is not None:
            session_kwargs["user_away_timeout"] = float(call.end_call_after_silence)
        if call.voice_mail_detection:
            session_kwargs["ivr_detection"] = True
