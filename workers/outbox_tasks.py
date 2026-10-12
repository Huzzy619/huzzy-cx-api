"""Outbox publisher.

Claims unpublished outbox rows and hands them to the broker. Consumers must
still process events idempotently: at-least-once delivery is assumed, not
exactly-once.
"""

from __future__ import annotations

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.common.outbox import OutboxEvent


@shared_task
def publish_outbox_events(batch_size: int = 100) -> int:
    published = 0
    pending_ids = list(
        OutboxEvent.objects.filter(status=OutboxEvent.Status.PENDING)
        .order_by("created_at")
        .values_list("id", flat=True)[:batch_size]
    )
    for event_id in pending_ids:
        with transaction.atomic():
            event = (
                OutboxEvent.objects.select_for_update(skip_locked=True)
                .filter(pk=event_id, status=OutboxEvent.Status.PENDING)
                .first()
            )
            if event is None:
                continue
            envelope = event.envelope()
            try:
                from config.celery import app

                app.send_task(
                    "workers.outbox_tasks.handle_domain_event",
                    args=[envelope],
                    queue="default",
                )
            except Exception as exc:  # noqa: BLE001
                event.attempts += 1
                event.last_error = str(exc)[:2000]
                event.status = OutboxEvent.Status.FAILED
                event.save(update_fields=["attempts", "last_error", "status"])
                continue
            event.status = OutboxEvent.Status.PUBLISHED
            event.attempts += 1
            event.published_at = timezone.now()
            event.save(
                update_fields=["status", "attempts", "published_at"]
            )
            published += 1
    return published


@shared_task
def handle_domain_event(envelope: dict) -> None:
    """Route a published domain event to its handler.

    Handlers must be idempotent. This is a placeholder dispatch table that
    grows as consumers are implemented.
    """

    event_type = envelope.get("event_type", "")
    handlers = {
        "interaction.ended": _on_interaction_ended,
    }
    handler = handlers.get(event_type)
    if handler is not None:
        handler(envelope)


def _on_interaction_ended(envelope: dict) -> None:
    from workers.interaction_tasks import process_ended_interaction

    process_ended_interaction.delay(envelope["aggregate_id"])
