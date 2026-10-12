"""Voice agent API.

Public (tenant-user) endpoints manage configuration. Internal endpoints are
called by the LiveKit voice worker using a separate service identity.
"""

from __future__ import annotations

from uuid import UUID

from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.errors import HttpError

from apps.common.exceptions import KoraError
from apps.common.permissions import Permission
from apps.contact_centres.models import ContactCentre
from apps.organisations.auth import SessionMembershipAuth
from apps.voice_agents.models import VoiceAgent, VoiceSession
from apps.voice_agents.permissions import VoiceWorkerAuth
from apps.voice_agents.schemas import (
    HandoffInput,
    HandoffOutput,
    KnowledgeSearchInput,
    KnowledgeSearchOutput,
    SessionEndInput,
    SessionEndOutput,
    SessionEventInput,
    SessionInitializeInput,
    SessionInitializeOutput,
    SupportCaseInput,
    SupportCaseOutput,
    TransactionStatusInput,
    TransactionStatusOutput,
    VoiceAgentCreateInput,
    VoiceAgentRead,
    VoiceAgentVersionCreateInput,
    VoiceAgentVersionRead,
)
from apps.voice_agents.services import (
    create_voice_agent,
    create_voice_agent_version,
    end_voice_session,
    initialize_voice_session,
    publish_voice_agent_version,
    record_voice_session_event,
)
from apps.voice_agents.tools import execute_voice_tool

router = Router(tags=["voice-agents"], auth=SessionMembershipAuth())
internal_router = Router(tags=["voice-internal"], auth=VoiceWorkerAuth())


# ---------------------------------------------------------------------------
# Public configuration API
# ---------------------------------------------------------------------------


def _get_owned_agent(request, agent_id: UUID) -> VoiceAgent:
    return get_object_or_404(
        VoiceAgent.objects.select_related("active_version").filter(
            organisation_id=request.auth.organisation_id
        ),
        id=agent_id,
    )


@router.post("", response={201: VoiceAgentRead})
def create_agent(request, payload: VoiceAgentCreateInput):
    request.auth.require(Permission.VOICE_AGENTS_EDIT)
    contact_centre = get_object_or_404(
        ContactCentre.objects.filter(
            organisation_id=request.auth.organisation_id
        ),
        id=payload.contact_centre_id,
    )
    try:
        agent = create_voice_agent(
            organisation=contact_centre.organisation,
            contact_centre=contact_centre,
            name=payload.name,
        )
    except KoraError as exc:
        raise HttpError(exc.http_status, exc.message) from exc
    return 201, agent


@router.get("/{agent_id}", response=VoiceAgentRead)
def get_agent(request, agent_id: UUID):
    request.auth.require(Permission.VOICE_AGENTS_READ)
    return _get_owned_agent(request, agent_id)


@router.post("/{agent_id}/versions", response={201: VoiceAgentVersionRead})
def create_version(request, agent_id: UUID, payload: VoiceAgentVersionCreateInput):
    request.auth.require(Permission.VOICE_AGENTS_EDIT)
    agent = _get_owned_agent(request, agent_id)
    try:
        version = create_voice_agent_version(voice_agent=agent, config=payload.config)
    except KoraError as exc:
        raise HttpError(exc.http_status, exc.message) from exc
    return 201, version


@router.post("/{agent_id}/publish", response=VoiceAgentVersionRead)
def publish_version(request, agent_id: UUID, version_id: UUID | None = None):
    request.auth.require(Permission.VOICE_AGENTS_PUBLISH)
    agent = _get_owned_agent(request, agent_id)

    if version_id is not None:
        version = get_object_or_404(
            agent.versions.filter(id=version_id),
        )
    else:
        version = (
            agent.versions.exclude(status="published")
            .order_by("-version")
            .first()
        )
        if version is None:
            raise HttpError(400, "No draft version to publish.")
    try:
        published = publish_voice_agent_version(version=version, actor=request.auth)
    except KoraError as exc:
        raise HttpError(exc.http_status, exc.message) from exc
    return published


# ---------------------------------------------------------------------------
# Internal worker API
# ---------------------------------------------------------------------------


def _load_session(voice_session_id: UUID) -> VoiceSession:
    session = (
        VoiceSession.objects.select_related("interaction", "voice_agent_version")
        .filter(id=voice_session_id)
        .first()
    )
    if session is None:
        raise HttpError(404, "Unknown voice session.")
    return session


@internal_router.post(
    "/sessions/initialize", response=SessionInitializeOutput
)
def initialize_session(request, payload: SessionInitializeInput):
    try:
        session = initialize_voice_session(
            provider_connection_id=payload.provider_connection_id,
            provider_call_id=payload.provider_call_id,
            room_name=payload.room_name,
            language=payload.language,
        )
    except KoraError as exc:
        raise HttpError(exc.http_status, exc.message) from exc

    config = session.voice_agent_version.config
    return SessionInitializeOutput(
        interaction_id=session.interaction_id,
        voice_session_id=session.id,
        organisation_id=session.organisation_id,
        voice_agent_version_id=session.voice_agent_version_id,
        config=config,
        allowed_tools=list(config.get("tools", [])),
        greeting=config.get("greeting", ""),
        language=session.language,
    )


@internal_router.post("/tools/knowledge", response=KnowledgeSearchOutput)
def tool_knowledge(request, payload: KnowledgeSearchInput):
    session = _load_session(payload.voice_session_id)
    result = execute_voice_tool(
        session=session,
        tool_name="search_approved_knowledge",
        idempotency_key=payload.idempotency_key,
        payload={"query": payload.query},
    )
    if result.status == "denied":
        raise HttpError(403, "Tool not permitted for this session.")
    if result.status == "failed":
        raise HttpError(502, "Knowledge search failed.")
    return KnowledgeSearchOutput(**result.output)


@internal_router.post(
    "/tools/transaction-status", response=TransactionStatusOutput
)
def tool_transaction_status(request, payload: TransactionStatusInput):
    session = _load_session(payload.voice_session_id)
    result = execute_voice_tool(
        session=session,
        tool_name="get_transaction_status",
        idempotency_key=payload.idempotency_key,
        payload={"transaction_reference": payload.transaction_reference},
    )
    if result.status == "denied":
        raise HttpError(403, "Tool not permitted for this session.")
    if result.status == "failed":
        raise HttpError(502, "Transaction lookup failed.")
    return TransactionStatusOutput(**result.output)


@internal_router.post("/tools/support-cases", response=SupportCaseOutput)
def tool_support_cases(request, payload: SupportCaseInput):
    session = _load_session(payload.voice_session_id)
    if payload.subject:
        tool_name = "create_support_case"
        tool_payload = {
            "subject": payload.subject,
            "reference": payload.reference,
        }
    else:
        tool_name = "get_support_case"
        tool_payload = {"reference": payload.reference or ""}

    result = execute_voice_tool(
        session=session,
        tool_name=tool_name,
        idempotency_key=payload.idempotency_key,
        payload=tool_payload,
    )
    if result.status == "denied":
        raise HttpError(403, "Tool not permitted for this session.")
    if result.status == "failed":
        raise HttpError(502, "Support case operation failed.")
    output = result.output
    if tool_name == "get_support_case" and not output.get("found"):
        raise HttpError(404, "Support case not found.")
    return SupportCaseOutput(
        reference=output.get("reference", ""),
        subject=output.get("subject", ""),
        status=output.get("status", ""),
        created_via=output.get("created_via", "voice"),
    )


@internal_router.post("/handoffs", response=HandoffOutput)
def create_handoff(request, payload: HandoffInput):
    session = _load_session(payload.voice_session_id)
    result = execute_voice_tool(
        session=session,
        tool_name="request_human_handoff",
        idempotency_key=f"handoff:{session.id}",
        payload={
            "queue_id": payload.queue_id,
            "reason": payload.reason,
        },
    )
    if result.status == "denied":
        raise HttpError(403, "Tool not permitted for this session.")
    if result.status == "failed":
        raise HttpError(502, "Handoff failed.")
    return HandoffOutput(**result.output)


@internal_router.post("/sessions/{voice_session_id}/events", response={202: dict})
def record_event(request, voice_session_id: UUID, payload: SessionEventInput):
    session = _load_session(voice_session_id)
    record_voice_session_event(
        session=session,
        event_type=payload.event_type,
        source_event_id=payload.source_event_id,
        occurred_at=payload.occurred_at,
        payload=payload.payload,
    )
    return 202, {"status": "recorded"}


@internal_router.post(
    "/sessions/{voice_session_id}/end", response=SessionEndOutput
)
def end_session(request, voice_session_id: UUID, payload: SessionEndInput):
    session = _load_session(voice_session_id)
    ended = end_voice_session(session=session, reason=payload.reason)
    return SessionEndOutput(voice_session_id=ended.id, status=ended.status)
