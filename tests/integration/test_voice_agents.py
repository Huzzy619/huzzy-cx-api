"""Integration tests for the voice agent layer.

These exercise real PostgreSQL constraints (idempotency, unique config
versions) plus the tenant and verification boundaries the voice worker cannot
bypass.
"""

from __future__ import annotations

import pytest

from apps.common.exceptions import ValidationError
from apps.customers.models import Customer
from apps.routing.services import request_human_handoff
from apps.voice_agents.models import (
    VoiceAgent,
    VoiceSession,
    VoiceToolInvocation,
)
from apps.voice_agents.services import (
    allowed_tools_for_session,
    end_voice_session,
    initialize_voice_session,
    mark_authentication_verified,
    publish_voice_agent_version,
)
from apps.voice_agents.tools import execute_voice_tool
from tests import factories

pytestmark = pytest.mark.integration


@pytest.fixture
def published_agent(db, organisation, contact_centre):
    agent = factories.VoiceAgentFactory(
        organisation=organisation, contact_centre=contact_centre
    )
    version = factories.VoiceAgentVersionFactory(voice_agent=agent, version=1)
    publish_voice_agent_version(version=version)
    agent.refresh_from_db()
    return agent


@pytest.fixture
def voice_session(db, published_agent, channel_connection):
    return initialize_voice_session(
        provider_connection_id=channel_connection.provider_account_id,
        provider_call_id="provider-call-voice-1",
        room_name="room-voice-1",
    )


# ---------------------------------------------------------------------------
# Configuration lifecycle
# ---------------------------------------------------------------------------


def test_publish_sets_active_version_and_emits_outbox(db, published_agent):
    from apps.common.outbox import OutboxEvent

    assert published_agent.active_version is not None
    assert published_agent.status == VoiceAgent.Status.ACTIVE
    assert OutboxEvent.objects.filter(
        event_type="voice_agent.published",
        aggregate_id=published_agent.id,
    ).exists()


def test_publish_is_idempotent(db, published_agent):
    version = published_agent.active_version
    again = publish_voice_agent_version(version=version)
    assert again.id == version.id
    assert again.published_at == version.published_at


# ---------------------------------------------------------------------------
# Session initialisation
# ---------------------------------------------------------------------------


def test_initialize_creates_session_and_interaction(
    db, published_agent, channel_connection
):
    session = initialize_voice_session(
        provider_connection_id=channel_connection.provider_account_id,
        provider_call_id="provider-call-voice-init",
        room_name="room-init",
    )

    assert session.status == VoiceSession.Status.INITIALIZING
    assert session.interaction.provider_call_id == "provider-call-voice-init"
    assert session.voice_agent_version == published_agent.active_version
    # Config includes a verification-required tool.
    assert session.authentication_status == VoiceSession.AuthenticationStatus.PENDING
    assert "get_transaction_status" in allowed_tools_for_session(session)


def test_initialize_is_idempotent_per_call(voice_session, channel_connection):
    again = initialize_voice_session(
        provider_connection_id=channel_connection.provider_account_id,
        provider_call_id="provider-call-voice-1",
        room_name="room-voice-1",
    )
    assert again.id == voice_session.id


def test_initialize_without_active_agent_is_rejected(db, channel_connection):
    with pytest.raises(ValidationError):
        initialize_voice_session(
            provider_connection_id=channel_connection.provider_account_id,
            provider_call_id="provider-call-no-agent",
            room_name="room-no-agent",
        )


# ---------------------------------------------------------------------------
# Tool boundary
# ---------------------------------------------------------------------------


def test_unverified_session_cannot_call_verified_tool(voice_session):
    result = execute_voice_tool(
        session=voice_session,
        tool_name="get_transaction_status",
        idempotency_key="idem-1",
        payload={"transaction_reference": "TX-1"},
    )

    assert result.status == "denied"
    invocation = VoiceToolInvocation.objects.get(pk=result.invocation_id)
    assert invocation.status == VoiceToolInvocation.Status.DENIED
    assert invocation.error_code == "identity_not_verified"


def test_verified_session_can_call_tool(voice_session, organisation):
    customer = Customer.objects.create(
        organisation=organisation, display_name="Ada"
    )
    mark_authentication_verified(session=voice_session, customer=customer)
    voice_session.refresh_from_db()

    result = execute_voice_tool(
        session=voice_session,
        tool_name="get_transaction_status",
        idempotency_key="idem-verified",
        payload={"transaction_reference": "TX-2"},
    )

    assert result.status == "succeeded"
    assert result.output["status"] == "unknown"
    assert result.output["transaction_reference"] == "TX-2"


def test_knowledge_tool_allowed_without_verification(voice_session):
    result = execute_voice_tool(
        session=voice_session,
        tool_name="search_approved_knowledge",
        idempotency_key="idem-knowledge",
        payload={"query": "card blocked"},
    )
    assert result.status == "succeeded"
    assert result.output["matches"] == []


def test_tool_not_in_config_is_denied(voice_session, organisation):
    customer = Customer.objects.create(
        organisation=organisation, display_name="Ada"
    )
    mark_authentication_verified(session=voice_session, customer=customer)

    result = execute_voice_tool(
        session=voice_session,
        tool_name="end_interaction",
        idempotency_key="idem-end",
        payload={},
    )
    assert result.status == "denied"
    assert result.output["error"] == "tool_not_enabled"


def test_tool_execution_is_idempotent(voice_session, organisation):
    customer = Customer.objects.create(
        organisation=organisation, display_name="Ada"
    )
    mark_authentication_verified(session=voice_session, customer=customer)

    first = execute_voice_tool(
        session=voice_session,
        tool_name="get_transaction_status",
        idempotency_key="idem-replay",
        payload={"transaction_reference": "TX-3"},
    )
    second = execute_voice_tool(
        session=voice_session,
        tool_name="get_transaction_status",
        idempotency_key="idem-replay",
        payload={"transaction_reference": "TX-3"},
    )

    assert first.invocation_id == second.invocation_id
    assert (
        VoiceToolInvocation.objects.filter(
            idempotency_key="idem-replay"
        ).count()
        == 1
    )


def test_tool_missing_reference_fails(voice_session, organisation):
    customer = Customer.objects.create(
        organisation=organisation, display_name="Ada"
    )
    mark_authentication_verified(session=voice_session, customer=customer)
    voice_session.refresh_from_db()

    result = execute_voice_tool(
        session=voice_session,
        tool_name="get_transaction_status",
        idempotency_key="idem-empty",
        payload={"transaction_reference": ""},
    )
    assert result.status == "failed"
    assert result.output["error"] == "validation_error"


# ---------------------------------------------------------------------------
# Handoff
# ---------------------------------------------------------------------------


def test_handoff_without_agents_returns_fallback(voice_session):
    outcome = request_human_handoff(interaction=voice_session.interaction)
    assert outcome.status in {"no_agent_available", "rejected"}
    assert outcome.fallback_message


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


def test_end_session_marks_ended_and_emits_outbox(voice_session):
    from apps.common.outbox import OutboxEvent

    ended = end_voice_session(session=voice_session, reason="completed")
    assert ended.status == VoiceSession.Status.ENDED
    assert ended.ended_at is not None
    assert ended.termination_reason == "completed"
    assert OutboxEvent.objects.filter(
        event_type="voice_session.ended",
        aggregate_id=voice_session.id,
    ).exists()

    # Ending is idempotent and does not move ended_at on a second call.
    again = end_voice_session(session=voice_session, reason="again")
    assert again.ended_at == ended.ended_at
