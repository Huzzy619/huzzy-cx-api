"""Mapping helpers shared by the pipeline, room, and agent builders."""

from __future__ import annotations

from voice_worker.schemas import AgentConfig


def scale_to_range(value: int, high: float, low: float) -> float:
    """Map a 0-10 UI integer to a float between ``low`` (at 10) and ``high`` (at 0)."""
    clamped = max(0, min(10, value))
    return high + (low - high) * (clamped / 10)


def resolve_language(config: AgentConfig) -> str:
    return config.language or "en-NG"


def resolve_ambient_sound(config: AgentConfig) -> str | None:
    speech = config.speech_config
    if speech and speech.ambient_sound:
        return speech.ambient_sound
    return None


def max_call_seconds(config: AgentConfig) -> int:
    return config.max_call_seconds or 600
