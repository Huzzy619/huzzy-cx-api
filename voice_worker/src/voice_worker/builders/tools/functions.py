"""LiveKit function tools backed by the Kora CX platform.

Only tools present in the platform allow-list (``config.tools``) are exposed,
so the model can never call a capability the platform did not authorise. Every
handler is a thin wrapper over :class:`KoraClient`; policy, identity
verification and idempotency are enforced server-side.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from livekit.agents import RunContext, function_tool, get_job_context
from livekit.agents.beta.tools import EndCallTool

from voice_worker.builders.context import VoiceAgentContext
from voice_worker.builders.tools.knowledge_base import build_knowledge_tool
from voice_worker.constants import (
    TOOL_CREATE_SUPPORT_CASE,
    TOOL_END_INTERACTION,
    TOOL_GET_SUPPORT_CASE,
    TOOL_HANDOFF,
    TOOL_KNOWLEDGE,
    TOOL_TRANSACTION_STATUS,
)

logger = logging.getLogger(__name__)


def _key(prefix: str) -> str:
    return f"{prefix}:{uuid.uuid4().hex}"


class FunctionToolsBuilder:
    def __init__(self, ctx: VoiceAgentContext) -> None:
        self._ctx = ctx
        self._allowed = set(ctx.config.tools)

    def build(self) -> list[Any]:
        tools: list[Any] = []
        if TOOL_KNOWLEDGE in self._allowed:
            tools.append(build_knowledge_tool())
        if TOOL_TRANSACTION_STATUS in self._allowed:
            tools.append(self._build_transaction_status_tool())
        if TOOL_GET_SUPPORT_CASE in self._allowed:
            tools.append(self._build_get_support_case_tool())
        if TOOL_CREATE_SUPPORT_CASE in self._allowed:
            tools.append(self._build_create_support_case_tool())
        if TOOL_HANDOFF in self._allowed:
            tools.append(self._build_handoff_tool())
        if TOOL_END_INTERACTION in self._allowed:
            tools.extend(EndCallTool(delete_room=False).tools)
        return tools

    def _build_transaction_status_tool(self) -> Any:
        ctx = self._ctx

        @function_tool(name="get_transaction_status")
        async def get_transaction_status(
            run_context: RunContext, transaction_reference: str
        ) -> dict[str, Any]:
            """Look up the status of a customer payment or transfer.

            Requires the caller to be identity-verified first.

            Args:
                transaction_reference: The reference the caller provided.
            """
            return await ctx.client.transaction_status(
                voice_session_id=ctx.voice_session_id,
                transaction_reference=transaction_reference,
                idempotency_key=_key("txn"),
            )

        return get_transaction_status

    def _build_get_support_case_tool(self) -> Any:
        ctx = self._ctx

        @function_tool(name="get_support_case")
        async def get_support_case(
            run_context: RunContext, reference: str
        ) -> dict[str, Any]:
            """Retrieve an existing support case by its reference.

            Args:
                reference: The support case reference to look up.
            """
            return await ctx.client.support_case(
                voice_session_id=ctx.voice_session_id,
                reference=reference,
                idempotency_key=_key("case-get"),
            )

        return get_support_case

    def _build_create_support_case_tool(self) -> Any:
        ctx = self._ctx

        @function_tool(name="create_support_case")
        async def create_support_case(
            run_context: RunContext, subject: str
        ) -> dict[str, Any]:
            """Create a support case for the caller to follow up.

            Args:
                subject: A short summary of the caller's issue.
            """
            return await ctx.client.support_case(
                voice_session_id=ctx.voice_session_id,
                subject=subject,
                idempotency_key=_key("case-create"),
            )

        return create_support_case

    def _build_handoff_tool(self) -> Any:
        ctx = self._ctx
        escalation = ctx.config.escalation_config
        handoff_message = (
            escalation.handoff_message
            if escalation and escalation.handoff_message
            else "Please hold while I connect you with a teammate."
        )
        transfer_number = escalation.call_transfer_number if escalation else None

        @function_tool(name="request_human_handoff")
        async def request_human_handoff(
            run_context: RunContext, reason: str = ""
        ) -> str:
            """Transfer the caller to a human colleague.

            Args:
                reason: A short summary of why the caller needs a human.
            """
            await ctx.client.request_handoff(
                voice_session_id=ctx.voice_session_id, reason=reason
            )
            await run_context.session.say(handoff_message, allow_interruptions=False)

            if transfer_number:
                transferred = await _sip_transfer(run_context, transfer_number)
                if transferred:
                    return f"Transferred the caller to {transfer_number}."
            return "Handoff requested. The caller is queued for a human colleague."

        return request_human_handoff


async def _sip_transfer(run_context: RunContext, transfer_number: str) -> bool:
    try:
        from livekit import api

        job_ctx = get_job_context()
        room_name = job_ctx.room.name

        sip_identity = _find_sip_participant(job_ctx)
        if sip_identity is None:
            logger.warning("No SIP participant found to transfer in room %s", room_name)
            return False

        transfer_to = transfer_number
        if not transfer_to.startswith(("tel:", "sip:")):
            transfer_to = f"tel:{transfer_to}"

        await job_ctx.api.sip.transfer_sip_participant(
            api.TransferSIPParticipantRequest(
                room_name=room_name,
                participant_identity=sip_identity,
                transfer_to=transfer_to,
                play_dialtone=True,
            )
        )
        return True
    except Exception:
        logger.exception("SIP transfer to %s failed", transfer_number)
        return False


def _find_sip_participant(job_ctx: Any) -> str | None:
    fallback: str | None = None
    for participant in job_ctx.room.remote_participants.values():
        identity = participant.identity or ""
        is_sip_like = (
            identity.startswith("sip_")
            or identity.startswith("+")
            or identity.isdigit()
        )
        if is_sip_like:
            return identity
        if identity and fallback is None:
            fallback = identity
    return fallback


def extract_job_metadata(job_ctx: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(job_ctx.job.metadata or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}
