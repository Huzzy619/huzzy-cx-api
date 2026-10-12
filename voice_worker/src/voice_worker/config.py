"""Runtime configuration for the Kora CX voice worker.

Secrets are read from the environment (or a local ``.env``) and are never sent
to the model. Only the internal voice API base URL and the worker token are
required to reach the control plane.

Self-hosted speech endpoints are configured here, by model id, so tenant
configuration only ever references an approved model id.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CustomSpeechEndpoint(BaseSettings):
    """A self-hosted STT/TTS endpoint keyed by an approved model id."""

    model_config = SettingsConfigDict(extra="ignore")

    model: str
    base_url: str
    transport: str = "openai_compatible"
    api_key: str | None = None
    language: str | None = None
    voice: str | None = None


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    kora_api_base_url: str = "http://localhost:8000/api/v1"
    voice_worker_token: str = ""
    voice_engine: str = "livekit"
    default_language: str = "en-NG"

    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    voice_agent_name: str = "kora-voice-agent"

    tool_timeout_seconds: float = 8.0

    # Optional OpenAI-compatible LLM endpoint for a single model id
    # (for example a self-hosted model). When unset, LiveKit Inference is used.
    custom_llm_model: str = ""
    custom_llm_base_url: str = ""
    custom_llm_api_key: str = ""

    # JSON object mapping model id -> endpoint config, used for self-hosted
    # STT/TTS. Example:
    #   {"ncair1/yoruba-asr": {"base_url": "...", "transport": "raw_audio"}}
    custom_speech_endpoints: str = Field(default="{}")

    def speech_endpoints(self) -> dict[str, dict[str, Any]]:
        try:
            parsed = json.loads(self.custom_speech_endpoints or "{}")
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}


_settings: WorkerSettings | None = None


def get_settings() -> WorkerSettings:
    global _settings
    if _settings is None:
        _settings = WorkerSettings()
    return _settings
