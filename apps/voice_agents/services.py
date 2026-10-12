"""Voice agent configuration lifecycle and session services."""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.models import record_audit_event
from apps.common.exceptions import NotFoundError, ValidationError
from apps.common.outbox import write_outbox_event
from apps.common.tenancy import assert_same_organisation
from apps.interactions.models import InteractionEvent
from apps.telephony.services import (
    get_or_create_interaction,
    resolve_active_voice_connection,
)
from apps.voice_agents.models import (
    VoiceAgent,
    VoiceAgentVersion,
    VoiceSession,
)
from apps.voice_agents.schemas import (
    VERIFICATION_REQUIRED_TOOLS,
    VoiceAgentConfig,
)

# ---------------------------------------------------------------------------
# Configuration lifecycle
# ---------------------------------------------------------------------------


@transaction.atomic
def create_voice_agent(*, organisation, contact_centre, name: str) -> VoiceAgent:
    assert_same_organisation(
        organisation=organisation,
        objects=[("contact_centre", contact_centre)],
    )
    return VoiceAgent.objects.create(
        organisation=organisation,
        contact_centre=contact_centre,
        name=name,
    )


def _parse_config(config: dict) -> VoiceAgentConfig:
    try:
        parsed = VoiceAgentConfig.model_validate(config)
        parsed.validate_tools()
    except ValueError as exc:
        raise ValidationError(f"Invalid voice agent config: {exc}") from exc
    return parsed


@transaction.atomic
def create_voice_agent_version(
    *, voice_agent: VoiceAgent, config: dict
) -> VoiceAgentVersion:
    _parse_config(config)
    agent = VoiceAgent.objects.select_for_update().get(pk=voice_agent.pk)
    next_version = (
        agent.versions.order_by("-version")
        .values_list("version", flat=True)
        .first()
        or 0
    ) + 1
    return VoiceAgentVersion.objects.create(
        voice_agent=agent,
        version=next_version,
        config=config,
        status=VoiceAgentVersion.Status.DRAFT,
    )


def validate_voice_agent_version(version: VoiceAgentVersion) -> VoiceAgentConfig:
    return _parse_config(version.config)


@transaction.atomic
def publish_voice_agent_version(
    *, version: VoiceAgentVersion, actor=None
) -> VoiceAgentVersion:
    locked = VoiceAgentVersion.objects.select_for_update().get(pk=version.pk)
    agent = VoiceAgent.objects.select_for_update().get(pk=locked.voice_agent_id)

    if locked.status == VoiceAgentVersion.Status.PUBLISHED:
        # Publishing is idempotent; do not create a second active version.
        return locked

    _parse_config(locked.config)

    locked.status = VoiceAgentVersion.Status.PUBLISHED
    locked.published_at = timezone.now()
    if actor is not None:
        locked.published_by_id = getattr(actor, "user_id", None) or getattr(
            actor, "id", None
        )
    locked.save(
        update_fields=["status", "published_at", "published_by", "updated_at"]
    )

    agent.active_version = locked
    agent.status = VoiceAgent.Status.ACTIVE
    agent.save(update_fields=["active_version", "status", "updated_at"])

    write_outbox_event(
        organisation=agent.organisation,
        aggregate_type="voice_agent",
        aggregate_id=agent.id,
        event_type="voice_agent.published",
        payload={"version": locked.version},
    )
    return locked


@transaction.atomic
def archive_voice_agent(*, voice_agent: VoiceAgent) -> VoiceAgent:
    agent = VoiceAgent.objects.select_for_update().get(pk=voice_agent.pk)
    agent.status = VoiceAgent.Status.ARCHIVED
    agent.save(update_fields=["status", "updated_at"])
    return agent


def get_active_voice_agent(*, organisation, contact_centre) -> VoiceAgent | None:
    return (
        VoiceAgent.objects.select_related("active_version")
        .filter(
            organisation=organisation,
            contact_centre=contact_centre,
            status=VoiceAgent.Status.ACTIVE,
            active_version__isnull=False,
        )
        .first()
    )


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


@transaction.atomic
def initialize_voice_session(
    *,
    provider_connection_id: str,
    provider_call_id: str,
    room_name: str,
    language: str | None = None,
) -> VoiceSession:
    """Create or reconcile the session for a provider call.

    Tenant context is resolved server-side from the provider connection; the
    caller cannot select an organisation.
    """

    connection = resolve_active_voice_connection(
        provider_connection_id=provider_connection_id
    )
    if connection is None:
        raise NotFoundError(
            "No active voice connection for this provider account.",
            provider_connection_id=provider_connection_id,
        )

    agent = get_active_voice_agent(
        organisation=connection.organisation,
        contact_centre=connection.contact_centre,
    )
    if agent is None or agent.active_version is None:
        raise ValidationError("No active voice agent for this contact centre.")

    config = agent.active_version.config
    parsed = _parse_config(config)

    interaction, _ = get_or_create_interaction(
        connection=connection,
        provider_call_id=provider_call_id,
    )

    needs_verification = bool(
        set(parsed.tools) & VERIFICATION_REQUIRED_TOOLS
    )

    existing = (
        VoiceSession.objects.select_for_update()
        .filter(interaction=interaction)
        .exclude(
            status__in=[VoiceSession.Status.ENDED, VoiceSession.Status.FAILED]
        )
        .first()
    )
    if existing is not None:
        # Retain the original agent version for an in-flight call.
        if room_name and existing.room_name != room_name:
            existing.room_name = room_name
            existing.save(update_fields=["room_name", "updated_at"])
        return existing

    session = VoiceSession.objects.create(
        organisation=connection.organisation,
        interaction=interaction,
        voice_agent_version=agent.active_version,
        status=VoiceSession.Status.INITIALIZING,
        engine_provider="livekit",
        room_name=room_name,
        language=language or parsed.language,
        authentication_status=(
            VoiceSession.AuthenticationStatus.PENDING
            if needs_verification
            else VoiceSession.AuthenticationStatus.NOT_REQUIRED
        ),
        started_at=timezone.now(),
    )

    record_audit_event(
        organisation=connection.organisation,
        actor_type="system",
        action="voice_session.initialized",
        resource_type="voice_session",
        resource_id=str(session.id),
        metadata={"voice_agent_version_id": str(agent.active_version_id)},
    )
    return session


def allowed_tools_for_session(session: VoiceSession) -> list[str]:
    config = session.voice_agent_version.config
    return list(config.get("tools", []))


@transaction.atomic
def mark_authentication_verified(*, session: VoiceSession, customer) -> VoiceSession:
    assert_same_organisation(
        organisation=session.organisation,
        objects=[("customer", customer)],
    )
    locked = VoiceSession.objects.select_for_update().get(pk=session.pk)
    locked.authentication_status = VoiceSession.AuthenticationStatus.VERIFIED
    locked.verified_customer = customer
    locked.save(
        update_fields=[
            "authentication_status",
            "verified_customer",
            "updated_at",
        ]
    )
    record_audit_event(
        organisation=session.organisation,
        actor_type="system",
        action="voice_session.identity_verified",
        resource_type="voice_session",
        resource_id=str(session.id),
        metadata={"customer_id": str(customer.id)},
    )
    return locked


def record_voice_session_event(
    *,
    session: VoiceSession,
    event_type: str,
    source_event_id: str,
    occurred_at=None,
    payload: dict | None = None,
) -> InteractionEvent:
    try:
        event, _ = InteractionEvent.objects.get_or_create(
            source=InteractionEvent.Source.VOICE_AGENT,
            source_scope=str(session.id),
            source_event_id=source_event_id,
            defaults={
                "organisation": session.organisation,
                "interaction": session.interaction,
                "event_type": event_type,
                "occurred_at": occurred_at,
                "payload": payload or {},
            },
        )
        return event
    except IntegrityError:
        return InteractionEvent.objects.get(
            source=InteractionEvent.Source.VOICE_AGENT,
            source_scope=str(session.id),
            source_event_id=source_event_id,
        )


@transaction.atomic
def end_voice_session(
    *, session: VoiceSession, reason: str = ""
) -> VoiceSession:
    locked = VoiceSession.objects.select_for_update().get(pk=session.pk)
    if locked.status == VoiceSession.Status.ENDED:
        return locked
    locked.status = VoiceSession.Status.ENDED
    locked.ended_at = timezone.now()
    locked.termination_reason = reason
    locked.save(
        update_fields=["status", "ended_at", "termination_reason", "updated_at"]
    )
    write_outbox_event(
        organisation=locked.organisation,
        aggregate_type="voice_session",
        aggregate_id=locked.id,
        event_type="voice_session.ended",
        payload={"reason": reason},
    )
    return locked
