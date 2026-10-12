"""Phased voice-agent job runtime: prepare -> media/session."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from livekit.agents import (
    Agent,
    AgentSession,
    AudioConfig,
    BackgroundAudioPlayer,
    BuiltinAudioClip,
    JobContext,
)

from voice_worker.builders import VoiceAgentContext, VoiceAgentFactory
from voice_worker.builders.utils import max_call_seconds, resolve_ambient_sound
from voice_worker.config import get_settings
from voice_worker.kora_client import KoraClient
from voice_worker.observability import attach_session_observability
from voice_worker.schemas import AgentConfig, parse_agent_config
from voice_worker.session_flags import SessionFlags, get_session_flags

logger = logging.getLogger(__name__)


@dataclass
class CallRuntimeState:
    voice_session_id: str
    interaction_id: str
    organisation_id: str
    agent_config: AgentConfig
    session: AgentSession
    agent: Agent
    room_options: Any
    max_call_duration: int
    ambient_sound: str | None
    flags: SessionFlags


def _as_str(value: Any) -> str | None:
    return None if value is None else str(value)


async def prepare_context(
    ctx: JobContext, metadata: dict[str, Any]
) -> CallRuntimeState:
    settings = get_settings()
    client = KoraClient(settings)
    ctx.proc.userdata["kora_client"] = client

    room_name = _as_str(metadata.get("room_name")) or ctx.room.name
    initialised = await client.initialize_session(
        provider_connection_id=_as_str(metadata.get("provider_connection_id"))
        or room_name,
        provider_call_id=_as_str(metadata.get("provider_call_id")) or room_name,
        room_name=room_name,
        language=metadata.get("language"),
    )

    config = parse_agent_config(initialised.get("config"))
    # The platform allow-list is authoritative over the config's own list.
    allowed = initialised.get("allowed_tools")
    if isinstance(allowed, list):
        config.tools = [str(tool) for tool in allowed]
    if initialised.get("greeting"):
        config.greeting = str(initialised["greeting"])
    if initialised.get("language"):
        config.language = str(initialised["language"])

    voice_session_id = str(initialised["voice_session_id"])
    interaction_id = str(initialised["interaction_id"])
    organisation_id = str(initialised["organisation_id"])

    agent_ctx = VoiceAgentContext(
        organisation_id=organisation_id,
        voice_session_id=voice_session_id,
        interaction_id=interaction_id,
        config=config,
        client=client,
    )
    factory = VoiceAgentFactory.from_context(agent_ctx)
    session = factory.build_session()
    agent = factory.build_agent()
    room_options = factory.build_room_options()
    attach_session_observability(session, ctx)

    flags = get_session_flags(ctx)
    flags["organisation_id"] = organisation_id
    flags["voice_session_id"] = voice_session_id
    flags["interaction_id"] = interaction_id
    flags["agent_config"] = config.model_dump(mode="json")

    return CallRuntimeState(
        voice_session_id=voice_session_id,
        interaction_id=interaction_id,
        organisation_id=organisation_id,
        agent_config=config,
        session=session,
        agent=agent,
        room_options=room_options,
        max_call_duration=max_call_seconds(config),
        ambient_sound=resolve_ambient_sound(config),
        flags=flags,
    )


async def _enforce_max_call_duration(ctx: JobContext, seconds: int) -> None:
    async def _timer() -> None:
        await asyncio.sleep(seconds)
        logger.info("Max call duration of %ss reached; shutting down", seconds)
        ctx.shutdown()

    ctx.proc.userdata["max_call_task"] = asyncio.create_task(_timer())


async def start_media_and_session(ctx: JobContext, state: CallRuntimeState) -> None:
    logger.info(
        "Starting session (organisation=%s session=%s)",
        state.organisation_id,
        state.voice_session_id,
    )

    await state.session.start(
        agent=state.agent,
        room=ctx.room,
        room_options=state.room_options,
    )

    await _enforce_max_call_duration(ctx, state.max_call_duration)

    if state.ambient_sound:
        background_audio = BackgroundAudioPlayer(
            ambient_sound=AudioConfig(state.ambient_sound, volume=0.8),
            thinking_sound=[
                AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING, volume=0.7),
                AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING2, volume=0.7),
            ],
        )
        await background_audio.start(room=ctx.room, agent_session=state.session)

    await state.session.generate_reply(
        instructions="Greet the caller and offer your assistance."
    )


async def run_voice_job(ctx: JobContext, metadata: dict[str, Any]) -> None:
    state = await prepare_context(ctx, metadata)
    await start_media_and_session(ctx, state)
