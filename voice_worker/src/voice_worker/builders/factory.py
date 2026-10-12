"""Facade that wires context, session, agent, and room builders."""

from __future__ import annotations

from livekit.agents import Agent, AgentSession, room_io

from voice_worker.builders.agent import AgentClassBuilder
from voice_worker.builders.context import VoiceAgentContext
from voice_worker.builders.room import RoomOptionsBuilder
from voice_worker.builders.session import SessionBuilder


class VoiceAgentFactory:
    """Orchestrates voice agent construction from a resolved context."""

    def __init__(self, ctx: VoiceAgentContext) -> None:
        self._ctx = ctx

    @property
    def context(self) -> VoiceAgentContext:
        return self._ctx

    def build_session(self) -> AgentSession:
        return SessionBuilder(self._ctx).build()

    def build_agent(self) -> Agent:
        return AgentClassBuilder(self._ctx).build()

    def build_room_options(self) -> room_io.RoomOptions:
        return RoomOptionsBuilder(self._ctx.config).build()

    @classmethod
    def from_context(cls, ctx: VoiceAgentContext) -> VoiceAgentFactory:
        return cls(ctx)
