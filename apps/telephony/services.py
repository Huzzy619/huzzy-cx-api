"""Telephony ingestion services.

This is the seam between provider-specific events and the interaction domain.
The provider adapter parses provider payloads; this service resolves the
tenant connection, creates or reconciles the interaction and delegates state
changes to ``apps.interactions.services``.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.utils.dateparse import parse_datetime

from apps.common.exceptions import NotFoundError
from apps.common.outbox import write_outbox_event
from apps.common.tenancy import assert_same_organisation
from apps.contact_centres.models import ChannelConnection
from apps.interactions.models import Interaction
from apps.interactions.services import (
    ApplyOutcome,
    DomainEventInput,
    apply_interaction_event,
)
from apps.telephony.ports import CanonicalVoiceEvent


@dataclass(frozen=True)
class IngestOutcome:
    interaction: Interaction
    outcome: ApplyOutcome
    interaction_created: bool = False

    @property
    def accepted(self) -> bool:
        return self.outcome is not ApplyOutcome.DUPLICATE

    @property
    def duplicate(self) -> bool:
        return self.outcome is ApplyOutcome.DUPLICATE


@dataclass(frozen=True)
class IngestSummary:
    accepted: int = 0
    duplicates: int = 0
    outcomes: tuple[IngestOutcome, ...] = ()


def ingest_provider_events(
    *, events: list[CanonicalVoiceEvent]
) -> IngestSummary:
    accepted = 0
    duplicates = 0
    outcomes: list[IngestOutcome] = []
    for event in events:
        result = ingest_provider_event(event=event)
        outcomes.append(result)
        if result.duplicate:
            duplicates += 1
        else:
            accepted += 1
    return IngestSummary(
        accepted=accepted, duplicates=duplicates, outcomes=tuple(outcomes)
    )


def ingest_provider_event(*, event: CanonicalVoiceEvent) -> IngestOutcome:
    connection = resolve_active_voice_connection(
        provider_connection_id=event.provider_connection_id
    )
    if connection is None:
        raise NotFoundError(
            "No active voice connection for this provider account.",
            provider_connection_id=event.provider_connection_id,
        )

    interaction, created = get_or_create_interaction(
        connection=connection,
        provider_call_id=event.provider_call_id,
        from_number=event.from_number,
        to_number=event.to_number,
        causation_id=event.provider_event_id,
    )

    occurred_at = (
        parse_datetime(event.occurred_at) if event.occurred_at else None
    )

    result = apply_interaction_event(
        interaction_id=interaction.id,
        event=DomainEventInput(
            source="provider",
            source_scope=str(connection.id),
            source_event_id=event.provider_event_id,
            event_type=event.event_type,
            occurred_at=occurred_at,
            payload=event.raw_event,
            correlation_id=interaction.correlation_id,
        ),
    )
    return IngestOutcome(
        interaction=result.interaction,
        outcome=result.outcome,
        interaction_created=created,
    )


def resolve_active_voice_connection(
    *, provider_connection_id: str
) -> ChannelConnection | None:
    return (
        ChannelConnection.objects.select_related("organisation", "contact_centre")
        .filter(
            provider_account_id=provider_connection_id,
            channel=ChannelConnection.Channel.VOICE,
            status=ChannelConnection.Status.ACTIVE,
        )
        .first()
    )


def get_or_create_interaction(
    *,
    connection: ChannelConnection,
    provider_call_id: str,
    from_number: str | None = None,
    to_number: str | None = None,
    causation_id: str = "",
) -> tuple[Interaction, bool]:
    """Idempotently resolve the interaction for a provider call.

    Safe to call from both the telephony webhook path and the voice worker's
    session-initialisation path.
    """

    existing = Interaction.objects.filter(
        channel_connection=connection,
        provider_call_id=provider_call_id,
    ).first()
    if existing is not None:
        return existing, False

    try:
        with transaction.atomic():
            interaction = Interaction.objects.create(
                organisation=connection.organisation,
                contact_centre=connection.contact_centre,
                channel_connection=connection,
                channel=Interaction.Channel.VOICE,
                direction=Interaction.Direction.INBOUND,
                provider_call_id=provider_call_id,
                from_number=from_number or "",
                to_number=to_number or connection.inbound_number,
                status=Interaction.Status.CREATED,
            )
            assert_same_organisation(
                organisation=connection.organisation,
                objects=[
                    ("contact_centre", connection.contact_centre),
                    ("channel_connection", connection),
                ],
            )
            write_outbox_event(
                organisation=connection.organisation,
                aggregate_type="interaction",
                aggregate_id=interaction.id,
                event_type="interaction.created",
                payload={
                    "channel": interaction.channel,
                    "direction": interaction.direction,
                    "provider_call_id": provider_call_id,
                },
                correlation_id=interaction.correlation_id,
                causation_id=causation_id,
            )
            return interaction, True
    except IntegrityError:
        # A concurrent webhook created the interaction first. Re-read it.
        return (
            Interaction.objects.get(
                channel_connection=connection,
                provider_call_id=provider_call_id,
            ),
            False,
        )
