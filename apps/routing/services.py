"""Routing domain services.

Routing decides where an eligible interaction should go. It may query agent
and queue availability but must not invoke an LLM to decide ordinary routing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from django.db import transaction

from apps.common.exceptions import ValidationError
from apps.common.outbox import write_outbox_event
from apps.common.tenancy import assert_same_organisation
from apps.contact_centres.models import Queue
from apps.interactions.models import Interaction


@dataclass(frozen=True)
class TransferRequest:
    interaction_id: uuid.UUID
    destination_queue_id: uuid.UUID
    transfer_request_id: uuid.UUID


@dataclass(frozen=True)
class HandoffOutcome:
    status: Literal["requested", "no_agent_available", "rejected"]
    queue_id: uuid.UUID | None = None
    fallback_message: str = ""


@transaction.atomic
def request_human_handoff(
    *,
    interaction: Interaction,
    queue_id=None,
    default_queue_id=None,
    reason: str = "",
) -> HandoffOutcome:
    """Queue an interaction for a human agent.

    This records the request and resolves an eligible queue. It does not claim
    a transfer has happened: the telephony/voice layer must confirm that.
    """

    from apps.agents.models import AgentProfile, AgentQueueMembership

    locked = Interaction.objects.select_for_update().get(pk=interaction.pk)
    if locked.is_terminal:
        return HandoffOutcome(status="rejected", fallback_message="Call has ended.")

    candidate_id = queue_id or default_queue_id or locked.queue_id
    queue = None
    if candidate_id is not None:
        queue = Queue.objects.filter(pk=candidate_id, is_active=True).first()
    if queue is None:
        return HandoffOutcome(
            status="rejected",
            fallback_message=(
                "I couldn't find a team to pass you to right now. "
                "I can create a support case instead."
            ),
        )

    assert_same_organisation(
        organisation=locked.organisation,
        objects=[("queue", queue)],
    )

    has_agents = AgentQueueMembership.objects.filter(
        queue=queue,
        agent__status=AgentProfile.Status.ACTIVE,
    ).exists()

    write_outbox_event(
        organisation=locked.organisation,
        aggregate_type="interaction",
        aggregate_id=locked.id,
        event_type="interaction.handoff_requested",
        payload={
            "queue_id": str(queue.id),
            "reason": reason,
            "has_available_agents": has_agents,
        },
        correlation_id=locked.correlation_id,
    )

    if not has_agents:
        return HandoffOutcome(
            status="no_agent_available",
            queue_id=queue.id,
            fallback_message=(
                "All our colleagues are busy. I can create a support case "
                "and someone will call you back."
            ),
        )
    return HandoffOutcome(status="requested", queue_id=queue.id)


@transaction.atomic
def request_transfer(
    *, interaction, destination_queue_id, actor=None
) -> TransferRequest:
    """Validate and record a transfer request.

    The request is only a record: the telephony provider must confirm the
    transfer and the interaction state is updated from provider events.
    """

    destination = Queue.objects.filter(pk=destination_queue_id, is_active=True).first()
    if destination is None:
        raise ValidationError("Destination queue is not available.")

    assert_same_organisation(
        organisation=interaction.organisation,
        objects=[("destination_queue", destination)],
    )

    link = Interaction.objects.select_for_update().get(pk=interaction.id)
    if link.is_terminal:
        raise ValidationError("Cannot transfer a terminal interaction.")

    return TransferRequest(
        interaction_id=link.id,
        destination_queue_id=destination.id,
        transfer_request_id=uuid.uuid4(),
    )
