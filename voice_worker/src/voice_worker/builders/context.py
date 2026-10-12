"""Session-scoped context passed through the voice builder tree."""

from __future__ import annotations

from dataclasses import dataclass

from voice_worker.kora_client import KoraClient
from voice_worker.schemas import AgentConfig


@dataclass(frozen=True)
class VoiceAgentContext:
    organisation_id: str
    voice_session_id: str
    interaction_id: str
    config: AgentConfig
    client: KoraClient
