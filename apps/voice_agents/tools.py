"""Voicebot tool execution boundary.

The model never touches the database or external APIs directly. Every tool
call passes through here, where the platform enforces tool allow-lists,
customer-verification gates, tenant scope and idempotency, and records an
invocation and audit trail.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.audit.models import record_audit_event
from apps.common.exceptions import KoraError, ValidationError
from apps.integrations.services import create_support_case, get_support_case
from apps.routing.services import request_human_handoff
from apps.voice_agents.models import VoiceSession, VoiceToolInvocation
from apps.voice_agents.providers import (
    get_knowledge_provider,
    get_transaction_provider,
)
from apps.voice_agents.schemas import (
    VERIFICATION_REQUIRED_TOOLS,
    VoiceAgentConfig,
)
from apps.voice_agents.services import (
    allowed_tools_for_session,
    end_voice_session,
)


@dataclass(frozen=True)
class VoiceToolResult:
    status: str
    output: dict
    invocation_id: uuid.UUID


def _digest(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def execute_voice_tool(
    *,
    session: VoiceSession,
    tool_name: str,
    idempotency_key: str,
    payload: dict,
) -> VoiceToolResult:
    allowed = allowed_tools_for_session(session)
    if tool_name not in allowed:
        invocation = _record_invocation(
            session=session,
            tool_name=tool_name,
            idempotency_key=idempotency_key,
            payload=payload,
        )
        if invocation.status == VoiceToolInvocation.Status.REQUESTED:
            _finish(
                invocation,
                status=VoiceToolInvocation.Status.DENIED,
                error_code="tool_not_enabled",
            )
        return VoiceToolResult(
            status="denied",
            output={"error": "tool_not_enabled"},
            invocation_id=invocation.id,
        )

    if tool_name in VERIFICATION_REQUIRED_TOOLS and not session.is_verified():
        invocation = _record_invocation(
            session=session,
            tool_name=tool_name,
            idempotency_key=idempotency_key,
            payload=payload,
        )
        if invocation.status == VoiceToolInvocation.Status.REQUESTED:
            _finish(
                invocation,
                status=VoiceToolInvocation.Status.DENIED,
                error_code="identity_not_verified",
            )
        return VoiceToolResult(
            status="denied",
            output={"error": "identity_not_verified"},
            invocation_id=invocation.id,
        )

    invocation = _record_invocation(
        session=session,
        tool_name=tool_name,
        idempotency_key=idempotency_key,
        payload=payload,
    )
    if invocation.status == VoiceToolInvocation.Status.SUCCEEDED:
        # Idempotent replay: return the stored result instead of re-executing.
        return VoiceToolResult(
            status="succeeded",
            output=invocation.result,
            invocation_id=invocation.id,
        )
    if invocation.status in {
        VoiceToolInvocation.Status.DENIED,
        VoiceToolInvocation.Status.FAILED,
    }:
        return VoiceToolResult(
            status=invocation.status,
            output=invocation.result or {"error": invocation.error_code},
            invocation_id=invocation.id,
        )

    handler = _HANDLERS[tool_name]
    try:
        output = handler(session=session, payload=payload)
    except KoraError as exc:
        _finish(
            invocation,
            status=VoiceToolInvocation.Status.FAILED,
            error_code=exc.code,
            result={"error": exc.code},
        )
        return VoiceToolResult(
            status="failed",
            output={"error": exc.code},
            invocation_id=invocation.id,
        )

    _finish(
        invocation,
        status=VoiceToolInvocation.Status.SUCCEEDED,
        result=output,
    )
    record_audit_event(
        organisation=session.organisation,
        actor_type="ai",
        action="voice_tool.executed",
        resource_type="voice_tool_invocation",
        resource_id=str(invocation.id),
        metadata={"tool_name": tool_name},
    )
    return VoiceToolResult(
        status="succeeded", output=output, invocation_id=invocation.id
    )


@transaction.atomic
def _record_invocation(
    *,
    session: VoiceSession,
    tool_name: str,
    idempotency_key: str,
    payload: dict,
) -> VoiceToolInvocation:
    existing = VoiceToolInvocation.objects.filter(
        organisation=session.organisation,
        idempotency_key=idempotency_key,
    ).first()
    if existing is not None:
        return existing

    return VoiceToolInvocation.objects.create(
        organisation=session.organisation,
        voice_session=session,
        interaction=session.interaction,
        tool_name=tool_name,
        idempotency_key=idempotency_key,
        status=VoiceToolInvocation.Status.REQUESTED,
        input_digest=_digest(payload),
    )


def _finish(
    invocation: VoiceToolInvocation,
    *,
    status: str,
    result: dict | None = None,
    error_code: str = "",
) -> None:
    invocation.status = status
    invocation.result = result or {}
    invocation.error_code = error_code
    invocation.completed_at = timezone.now()
    invocation.save(
        update_fields=[
            "status",
            "result",
            "error_code",
            "completed_at",
            "updated_at",
        ]
    )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _handle_knowledge(*, session: VoiceSession, payload: dict) -> dict:
    query = str(payload.get("query", ""))
    provider = get_knowledge_provider()
    matches = provider.search(
        organisation=session.organisation, query=query, limit=3
    )
    return {
        "query": query,
        "matches": [
            {
                "document_id": match.document_id,
                "title": match.title,
                "snippet": match.snippet,
            }
            for match in matches
        ],
    }


def _handle_transaction_status(*, session: VoiceSession, payload: dict) -> dict:
    reference = str(payload.get("transaction_reference", ""))
    if not reference:
        raise ValidationError("transaction_reference is required.")
    provider = get_transaction_provider()
    result = provider.get_status(
        organisation=session.organisation,
        customer=session.verified_customer,
        reference=reference,
    )
    return {
        "transaction_reference": result.reference,
        "status": result.status,
        "amount_display": result.amount_display,
        "currency": result.currency,
        "customer_message": result.customer_message,
    }


def _handle_get_support_case(*, session: VoiceSession, payload: dict) -> dict:
    reference = str(payload.get("reference", ""))
    case = get_support_case(
        organisation=session.organisation,
        customer=session.verified_customer,
        reference=reference,
    )
    if case is None:
        return {"found": False}
    return {
        "found": True,
        "reference": case.reference,
        "subject": case.subject,
        "status": case.status,
    }


def _handle_create_support_case(*, session: VoiceSession, payload: dict) -> dict:
    subject = str(payload.get("subject") or "Customer request from voice call")
    case = create_support_case(
        organisation=session.organisation,
        customer=session.verified_customer,
        subject=subject,
        reference=payload.get("reference") or None,
    )
    return {
        "reference": case.reference,
        "subject": case.subject,
        "status": case.status,
        "created_via": case.created_via,
    }


def _handle_handoff(*, session: VoiceSession, payload: dict) -> dict:
    config = VoiceAgentConfig.model_validate(
        session.voice_agent_version.config
    )
    outcome = request_human_handoff(
        interaction=session.interaction,
        queue_id=payload.get("queue_id"),
        default_queue_id=config.default_queue_id,
        reason=str(payload.get("reason", "")),
    )
    return {
        "status": outcome.status,
        "queue_id": str(outcome.queue_id) if outcome.queue_id else None,
        "fallback_message": outcome.fallback_message,
    }


def _handle_end_interaction(*, session: VoiceSession, payload: dict) -> dict:
    end_voice_session(
        session=session, reason=str(payload.get("reason", "voicebot_ended"))
    )
    return {"status": "ended"}


_HANDLERS = {
    "search_approved_knowledge": _handle_knowledge,
    "get_transaction_status": _handle_transaction_status,
    "get_support_case": _handle_get_support_case,
    "create_support_case": _handle_create_support_case,
    "request_human_handoff": _handle_handoff,
    "end_interaction": _handle_end_interaction,
}
