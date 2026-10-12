"""Text-to-speech pipeline builder with fallback."""

from __future__ import annotations

from livekit.agents import inference, tts

from voice_worker.builders.pipeline.custom_providers import resolve_custom_tts
from voice_worker.constants import DEFAULT_TTS_MODEL, DEFAULT_TTS_VOICE
from voice_worker.schemas import AgentConfig


class TTSBuilder:
    def __init__(self, config: AgentConfig) -> None:
        self._config = config

    def build(self) -> tts.TTS | tts.FallbackAdapter:
        transcription = self._config.transcription_config
        voice = self._config.voice or DEFAULT_TTS_VOICE
        language = self._config.language or None
        instances: list[tts.TTS] = []

        custom_model = transcription.tts_model if transcription else None
        custom = resolve_custom_tts(custom_model, voice=voice)
        if custom is not None:
            instances.append(custom)
        else:
            kwargs: dict = {"model": custom_model or DEFAULT_TTS_MODEL}
            if language:
                kwargs["language"] = language
            if voice:
                kwargs["voice"] = voice
            instances.append(inference.TTS(**kwargs))

        instances.append(
            inference.TTS.from_model_string(DEFAULT_TTS_MODEL)
        )
        return tts.FallbackAdapter(instances)
