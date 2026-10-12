"""Factories for self-hosted STT/TTS endpoints configured in worker settings.

Endpoints are keyed by model id in ``WorkerSettings.custom_speech_endpoints`` so
tenant configuration only references an approved model id. Two transports:

- ``openai_compatible``: LiveKit OpenAI plugin with a ``base_url`` override.
- ``raw_audio``: custom plugins that POST/return raw audio.
"""

from __future__ import annotations

from typing import Any

from livekit.agents import stt, tts
from livekit.plugins import openai

from voice_worker.builders.pipeline.raw_audio import RawAudioSTT, RawAudioTTS
from voice_worker.config import get_settings


def _endpoint(model_id: str) -> dict[str, Any] | None:
    endpoints = get_settings().speech_endpoints()
    config = endpoints.get(model_id)
    if isinstance(config, dict):
        return config
    return None


def resolve_custom_stt(
    model_id: str | None, *, language: str | None = None
) -> stt.STT | None:
    if not model_id:
        return None
    config = _endpoint(model_id)
    if config is None or not config.get("base_url"):
        return None

    resolved_language = config.get("language") or language or "en"
    if config.get("transport") == "raw_audio":
        return RawAudioSTT(
            endpoint_url=config["base_url"],
            token=config.get("api_key", "") or "",
            model=model_id,
            language=resolved_language,
            response_text_key=config.get("response_text_key", "text"),
            content_type=config.get("content_type", "audio/wav"),
        )
    return openai.STT(
        model=model_id,
        base_url=config["base_url"].rstrip("/"),
        api_key=config.get("api_key", "") or "unused",
        language=resolved_language,
    )


def resolve_custom_tts(
    model_id: str | None, *, voice: str | None = None
) -> tts.TTS | None:
    if not model_id:
        return None
    config = _endpoint(model_id)
    if config is None or not config.get("base_url"):
        return None

    resolved_voice = config.get("voice") or voice
    if config.get("transport") == "raw_audio":
        return RawAudioTTS(
            endpoint_url=config["base_url"],
            token=config.get("api_key", "") or "",
            model=model_id,
            language=config.get("language"),
            voice=resolved_voice,
            request_text_key=config.get("request_text_key", "inputs"),
            request_format=config.get("request_format", "json"),
            response_audio_key=config.get("response_audio_key"),
            response_format=config.get("response_format", "wav"),
        )
    kwargs: dict[str, Any] = {
        "model": model_id,
        "base_url": config["base_url"].rstrip("/"),
        "api_key": config.get("api_key", "") or "unused",
        "voice": resolved_voice or "ash",
    }
    if config.get("language"):
        kwargs["language"] = config["language"]
    return openai.TTS(**kwargs)
