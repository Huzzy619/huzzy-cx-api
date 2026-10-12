"""Integration tests for provider event ingestion.

These exercise real PostgreSQL constraints (uniqueness, row locking) and the
transactional outbox.
"""

from __future__ import annotations

import pytest

from apps.common.outbox import OutboxEvent
from apps.interactions.models import Interaction, InteractionEvent
from apps.interactions.services import ApplyOutcome
from apps.telephony.ports import CanonicalVoiceEvent
from apps.telephony.services import ingest_provider_event
from tests import factories

pytestmark = pytest.mark.integration


def _event(channel_connection, **overrides) -> CanonicalVoiceEvent:
    defaults = {
        "provider_connection_id": channel_connection.provider_account_id,
        "provider_call_id": "provider-call-1",
        "provider_event_id": "evt-1",
        "event_type": "call.started",
        "occurred_at": "2026-10-12T10:30:00Z",
    }
    defaults.update(overrides)
    return CanonicalVoiceEvent(**defaults)


def test_first_event_creates_interaction_and_outbox(db, channel_connection):
    result = ingest_provider_event(event=_event(channel_connection))

    assert result.interaction_created is True
    assert result.outcome is ApplyOutcome.IGNORED_OUT_OF_ORDER  # created == target
    assert Interaction.objects.filter(
        channel_connection=channel_connection,
        provider_call_id="provider-call-1",
    ).count() == 1
    assert OutboxEvent.objects.filter(
        event_type="interaction.created",
        aggregate_id=result.interaction.id,
    ).exists()


def test_duplicate_provider_event_is_not_applied_twice(db, channel_connection):
    event = _event(channel_connection)
    first = ingest_provider_event(event=event)
    second = ingest_provider_event(event=event)

    assert first.duplicate is False
    assert second.duplicate is True
    assert second.outcome is ApplyOutcome.DUPLICATE
    assert Interaction.objects.filter(
        channel_connection=channel_connection,
        provider_call_id=event.provider_call_id,
    ).count() == 1
    assert InteractionEvent.objects.filter(
        source="provider",
        source_event_id=event.provider_event_id,
    ).count() == 1


def test_full_lifecycle_advances_state_and_emits_outbox(db, channel_connection):
    for index, event_type in enumerate(
        ["call.started", "call.queued", "call.ringing", "call.answered", "call.ended"]
    ):
        ingest_provider_event(
            event=_event(
                channel_connection,
                provider_event_id=f"evt-{index}",
                event_type=event_type,
                occurred_at=f"2026-10-12T10:3{index}:00Z",
            )
        )

    interaction = Interaction.objects.get(
        channel_connection=channel_connection,
        provider_call_id="provider-call-1",
    )
    assert interaction.status == Interaction.Status.ENDED
    assert interaction.answered_at is not None
    assert interaction.ended_at is not None
    assert interaction.ended_at >= interaction.answered_at

    emitted = set(
        OutboxEvent.objects.filter(aggregate_id=interaction.id).values_list(
            "event_type", flat=True
        )
    )
    assert {
        "interaction.created",
        "interaction.queued",
        "interaction.ringing",
        "interaction.answered",
        "interaction.ended",
    }.issubset(emitted)


def test_late_answered_event_does_not_resurrect_ended_interaction(
    db, channel_connection
):
    for index, event_type in enumerate(
        ["call.started", "call.answered", "call.ended"]
    ):
        ingest_provider_event(
            event=_event(
                channel_connection,
                provider_event_id=f"evt-{index}",
                event_type=event_type,
                occurred_at=f"2026-10-12T10:3{index}:00Z",
            )
        )

    # A late answered event arrives after the call has ended.
    result = ingest_provider_event(
        event=_event(
            channel_connection,
            provider_event_id="evt-late",
            event_type="call.answered",
            occurred_at="2026-10-12T10:40:00Z",
        )
    )

    assert result.outcome is ApplyOutcome.IGNORED_OUT_OF_ORDER
    interaction = Interaction.objects.get(
        channel_connection=channel_connection,
        provider_call_id="provider-call-1",
    )
    assert interaction.status == Interaction.Status.ENDED


def test_event_from_unknown_connection_is_rejected(db):
    other = factories.ChannelConnectionFactory(provider_account_id="unknown-account")
    event = _event(other, provider_connection_id="does-not-exist")

    from apps.common.exceptions import NotFoundError

    with pytest.raises(NotFoundError):
        ingest_provider_event(event=event)


def test_unknown_event_type_is_retained_not_failed(db, channel_connection):
    ingest_provider_event(event=_event(channel_connection))
    result = ingest_provider_event(
        event=_event(
            channel_connection,
            provider_event_id="evt-unknown",
            event_type="call.something_new",
        )
    )

    assert result.outcome is ApplyOutcome.IGNORED_UNKNOWN
    assert InteractionEvent.objects.filter(
        source_event_id="evt-unknown"
    ).exists()
