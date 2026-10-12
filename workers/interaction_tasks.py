"""Interaction lifecycle tasks.

These tasks are dispatched by the outbox publisher after the transaction that
wrote the domain event commits, never directly from the request path.
"""

from __future__ import annotations

from celery import shared_task


@shared_task(
    autoretry_for=(TimeoutError, ConnectionError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=4,
)
def process_ended_interaction(interaction_id: str) -> None:
    from apps.interactions.models import Interaction
    from apps.interactions.services import mark_completed

    interaction = Interaction.objects.filter(pk=interaction_id).first()
    if interaction is None or interaction.is_terminal:
        return
    if interaction.status not in {
        Interaction.Status.ENDED,
        Interaction.Status.PROCESSING,
    }:
        return

    mark_completed(interaction_id=interaction.id)
