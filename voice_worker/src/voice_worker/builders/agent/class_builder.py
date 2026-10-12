"""Builds the LiveKit :class:`Agent` for a Kora CX voice session.

The agent reads its instructions and tools from the platform config delivered
during session initialisation. It adds no business logic of its own.
"""

from __future__ import annotations

import logging
from typing import Any

from livekit.agents import Agent

from voice_worker.builders.agent.instructions import InstructionsBuilder
from voice_worker.builders.context import VoiceAgentContext
from voice_worker.builders.tools import FunctionToolsBuilder

logger = logging.getLogger(__name__)


class KoraVoiceAgent(Agent):
    """A config-driven agent whose tools all route through the platform."""

    def __init__(self, ctx: VoiceAgentContext) -> None:
        self._ctx = ctx
        tools = FunctionToolsBuilder(ctx).build()
        super().__init__(
            instructions=InstructionsBuilder(ctx.config).build(),
            tools=tools or None,
        )

    async def on_enter(self) -> None:
        config = self._ctx.config
        if config.read_recording_disclosure and config.recording_disclosure:
            await self.session.say(
                config.recording_disclosure, allow_interruptions=False
            )

        welcome = config.welcome_config
        if welcome and not welcome.user_speak_first:
            if welcome.message:
                await self.session.say(welcome.message)
            else:
                await self.session.generate_reply(
                    instructions="Greet the caller with a warm welcome."
                )


class AgentClassBuilder:
    def __init__(self, ctx: VoiceAgentContext) -> None:
        self._ctx = ctx

    def build(self) -> Agent:
        agent = KoraVoiceAgent(self._ctx)
        logger.info(
            "Built agent for organisation=%s session=%s (tools=%d)",
            self._ctx.organisation_id,
            self._ctx.voice_session_id,
            len(self._ctx.config.tools),
        )
        return agent


def build_agent(ctx: VoiceAgentContext) -> Agent:
    return AgentClassBuilder(ctx).build()


__all__: list[Any] = ["AgentClassBuilder", "KoraVoiceAgent", "build_agent"]
