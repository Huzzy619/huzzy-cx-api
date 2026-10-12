"""Interaction domain services.

State changes and their outbox events are written inside a single transaction.
Event uniqueness is protected by a database constraint; the duplicate-insert
race is handled by catching that constraint rather than trusting a preliminary
existence check.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from django.db import IntegrityError, transaction

from apps.common.outbox import write_outbox_event
from apps.interactions.models import Interaction, InteractionEvent
from apps.interactions.state import (
    TERMINAL_STATES,
    is_transition_allowed,
)


@dataclass(frozen=True)
class DomainEventInput:
    """A provider-neutral event to apply to an interaction."""

    source: str
    source_event_id: str
    event_type: str
    source_scope: str = ""
    occurred_at: datetime | None = None
    payload: dict = field(default_factory=dict)
    correlation_id: uuid.UUID | None = None


class ApplyOutcome(StrEnum):
    APPLIED = "applied"
    DUPLICATE = "duplicate"
    IGNORED_UNKNOWN = "ignored_unknown"
    IGNORED_TERMINAL = "ignored_terminal"
    IGNORED_OUT_OF_ORDER = "ignored_out_of_order"


@dataclass(frozen=True)
class ApplyResult:
    interaction: Interaction
    outcome: ApplyOutcome

    @property
    def applied(self) -> bool:
        return self.outcome is ApplyOutcome.APPLIED


# Canonical mapping from provider event names to the internal state machine.
PROVIDER_TRANSITIONS: dict[str, str] = {
    "call.started": Interaction.Status.CREATED,
    "call.queued": Interaction.Status.QUEUED,
    "call.routing": Interaction.Status.ROUTING,
    "call.ringing": Interaction.Status.RINGING,
    "call.answered": Interaction.Status.ACTIVE,
    "call.on_hold": Interaction.Status.ON_HOLD,
    "call.off_hold": Interaction.Status.ACTIVE,
    "call.transferring": Interaction.Status.TRANSFERRING,
    "call.transferred": Interaction.Status.QUEUED,
    "call.ended": Interaction.Status.ENDED,
}

# Maps an applied target status to the outbox event type it publishes.
STATUS_EVENT_TYPES: dict[str, str] = {
    Interaction.Status.CREATED: "interaction.created",
    Interaction.Status.QUEUED: "interaction.queued",
    Interaction.Status.ROUTING: "interaction.routed",
    Interaction.Status.RINGING: "interaction.ringing",
    Interaction.Status.ACTIVE: "interaction.answered",
    Interaction.Status.ON_HOLD: "interaction.on_hold",
    Interaction.Status.TRANSFERRING: "interaction.transferring",
    Interaction.Status.ENDED: "interaction.ended",
}


@transaction.atomic
def apply_interaction_event(
    *,
    interaction_id,
    event: DomainEventInput,
) -> ApplyResult:
    """Record an event and apply its state transition if valid.

    The interaction row is locked for the duration so two concurrent events
    cannot both apply an incompatible transition.
    """

    interaction = (
        Interaction.objects.select_for_update().get(pk=interaction_id)
    )

    try:
        with transaction.atomic():
            InteractionEvent.objects.create(
                organisation_id=interaction.organisation_id,
                interaction=interaction,
                source=event.source,
                source_scope=event.source_scope,
                source_event_id=event.source_event_id,
                event_type=event.event_type,
                occurred_at=event.occurred_at,
                payload=event.payload,
            )
    except IntegrityError:
        # Scoped to the event unique constraint by construction. If a
        # different integrity error occurred, re-raise it for monitoring.
        if InteractionEvent.objects.filter(
            source=event.source,
            source_scope=event.source_scope,
            source_event_id=event.source_event_id,
        ).exists():
            return ApplyResult(interaction, ApplyOutcome.DUPLICATE)
        raise

    target_status = PROVIDER_TRANSITIONS.get(event.event_type)
    if target_status is None:
        # Unknown events are retained for diagnostics and reconciliation.
        return ApplyResult(interaction, ApplyOutcome.IGNORED_UNKNOWN)

    if interaction.status in TERMINAL_STATES:
        return ApplyResult(interaction, ApplyOutcome.IGNORED_TERMINAL)

    if target_status == interaction.status:
        _mark_processed(interaction, event)
        return ApplyResult(interaction, ApplyOutcome.IGNORED_OUT_OF_ORDER)

    if not is_transition_allowed(interaction.status, target_status):
        # Out-of-order or late events are not applied, but the event record
        # above is retained so the timeline can be reconciled.
        _mark_processed(interaction, event)
        return ApplyResult(interaction, ApplyOutcome.IGNORED_OUT_OF_ORDER)

    _apply_transition(interaction, target_status=target_status, event=event)
    return ApplyResult(interaction, ApplyOutcome.APPLIED)


def _apply_transition(
    interaction: Interaction,
    *,
    target_status: str,
    event: DomainEventInput,
) -> None:
    update_fields = ["status", "updated_at"]

    if target_status == Interaction.Status.ACTIVE and interaction.answered_at is None:
        interaction.answered_at = event.occurred_at
        update_fields.append("answered_at")

    if target_status == Interaction.Status.ENDED:
        interaction.ended_at = event.occurred_at
        update_fields.append("ended_at")
        if interaction.ai_enrichment_status == (
            Interaction.AIEnrichmentStatus.NOT_APPLICABLE
        ):
            interaction.ai_enrichment_status = (
                Interaction.AIEnrichmentStatus.PENDING
            )
            update_fields.append("ai_enrichment_status")

    interaction.status = target_status
    interaction.save(update_fields=update_fields)

    outbox_event_type = STATUS_EVENT_TYPES.get(target_status)
    if outbox_event_type:
        write_outbox_event(
            organisation=interaction.organisation,
            aggregate_type="interaction",
            aggregate_id=interaction.id,
            event_type=outbox_event_type,
            payload={
                "channel": interaction.channel,
                "direction": interaction.direction,
                "status": interaction.status,
            },
            occurred_at=event.occurred_at,
            correlation_id=event.correlation_id or interaction.correlation_id,
            causation_id=event.source_event_id,
        )


def _mark_processed(interaction: Interaction, event: DomainEventInput) -> None:
    from django.utils import timezone

    InteractionEvent.objects.filter(
        source=event.source,
        source_scope=event.source_scope,
        source_event_id=event.source_event_id,
    ).update(processed_at=timezone.now())


@transaction.atomic
def mark_completed(*, interaction_id) -> Interaction:
    """Finalise an ended interaction once post-call work is done.

    A completed interaction must have a consistent end state: ``ended_at`` is
    set and the status is terminal.
    """

    interaction = Interaction.objects.select_for_update().get(pk=interaction_id)
    if interaction.status in TERMINAL_STATES:
        return interaction
    if not is_transition_allowed(interaction.status, Interaction.Status.COMPLETED):
        interaction.status = Interaction.Status.FAILED
        interaction.save(update_fields=["status", "updated_at"])
        write_outbox_event(
            organisation=interaction.organisation,
            aggregate_type="interaction",
            aggregate_id=interaction.id,
            event_type="interaction.failed",
            payload={"reason": "invalid_completion_state"},
            correlation_id=interaction.correlation_id,
        )
        return interaction

    interaction.status = Interaction.Status.COMPLETED
    interaction.save(update_fields=["status", "updated_at"])
    write_outbox_event(
        organisation=interaction.organisation,
        aggregate_type="interaction",
        aggregate_id=interaction.id,
        event_type="interaction.completed",
        payload={"channel": interaction.channel},
        correlation_id=interaction.correlation_id,
    )
    return interaction


@transaction.atomic
def submit_disposition(
    *,
    interaction_id,
    code: str,
    notes: str = "",
    actor=None,
) -> Interaction:
    """Record a final disposition for an interaction.

    This only mutates platform state; it does not claim the external call has
    changed. Agents may submit a disposition once the call has ended.
    """

    interaction = Interaction.objects.select_for_update().get(pk=interaction_id)
    interaction.disposition_code = code
    interaction.save(update_fields=["disposition_code", "updated_at"])

    if interaction.status == Interaction.Status.ENDED:
        interaction.status = Interaction.Status.PROCESSING
        interaction.save(update_fields=["status", "updated_at"])

    write_outbox_event(
        organisation=interaction.organisation,
        aggregate_type="interaction",
        aggregate_id=interaction.id,
        event_type="interaction.disposition_submitted",
        payload={"disposition_code": code, "has_notes": bool(notes)},
        correlation_id=interaction.correlation_id,
    )
    return interaction
