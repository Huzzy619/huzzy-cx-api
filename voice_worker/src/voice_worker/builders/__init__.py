"""Voice agent builders - map platform voice config to LiveKit components.

Package layout:
  constants.py  - defaults and shared constants
  context.py    - VoiceAgentContext
  utils.py      - shared mapping helpers
  pipeline/     - STT, LLM, TTS, turn handling, custom providers
  tools/        - platform function tools and knowledge search
  agent/        - instructions and config-driven Agent class
  session.py    - AgentSession assembly
  room.py       - RoomOptions
  factory.py    - VoiceAgentFactory facade
"""

from __future__ import annotations

from typing import Any

from livekit.agents import AgentSession, room_io

from voice_worker.builders.agent import (
    AgentClassBuilder,
    KoraVoiceAgent,
    build_agent,
)
from voice_worker.builders.agent.instructions import InstructionsBuilder
from voice_worker.builders.context import VoiceAgentContext
from voice_worker.builders.factory import VoiceAgentFactory
from voice_worker.builders.pipeline import (
    LLMBuilder,
    STTBuilder,
    TTSBuilder,
    TurnHandlingBuilder,
)
from voice_worker.builders.room import RoomOptionsBuilder
from voice_worker.builders.session import SessionBuilder
from voice_worker.builders.tools import FunctionToolsBuilder
from voice_worker.schemas import AgentConfig, parse_agent_config


def build_agent_session(ctx: VoiceAgentContext) -> AgentSession:
    return SessionBuilder(ctx).build()


def build_room_options(
    config: AgentConfig | dict[str, Any] | None,
) -> room_io.RoomOptions:
    if not isinstance(config, AgentConfig):
        config = parse_agent_config(config)
    return RoomOptionsBuilder(config).build()


__all__ = [
    "AgentClassBuilder",
    "AgentConfig",
    "FunctionToolsBuilder",
    "InstructionsBuilder",
    "KoraVoiceAgent",
    "LLMBuilder",
    "RoomOptionsBuilder",
    "STTBuilder",
    "SessionBuilder",
    "TTSBuilder",
    "TurnHandlingBuilder",
    "VoiceAgentContext",
    "VoiceAgentFactory",
    "build_agent",
    "build_agent_session",
    "build_room_options",
    "parse_agent_config",
]
