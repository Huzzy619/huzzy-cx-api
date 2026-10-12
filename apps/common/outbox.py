"""Transactional outbox.

Domain state changes and their corresponding events are written in the same
database transaction. A separate publisher (``workers.outbox_tasks``) claims
unpublished rows and delivers them to the broker. This avoids the failure mode
where the database commits a change but the process crashes before the event is
published.
"""

from __future__ import annotations

import uuid

from django.db import models

from apps.common.models import UUIDModel


class OutboxEvent(UUIDModel):
    """A durable domain event awaiting publication.

    The event envelope is assembled when the event is published so that the
    stored payload stays minimal and free of secrets.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PUBLISHED = "published", "Published"
        FAILED = "failed", "Failed"

    organisation = models.ForeignKey(
        "organisations.Organisation",
        on_delete=models.PROTECT,
        related_name="outbox_events",
    )
    aggregate_type = models.CharField(max_length=80)
    aggregate_id = models.UUIDField()
    event_type = models.CharField(max_length=100)
    schema_version = models.PositiveSmallIntegerField(default=1)
    payload = models.JSONField(default=dict, blank=True)
    correlation_id = models.UUIDField(default=uuid.uuid4)
    causation_id = models.CharField(max_length=255, blank=True)

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    occurred_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["status", "created_at"],
                name="outbox_status_created_idx",
            ),
            models.Index(
                fields=["aggregate_type", "aggregate_id"],
                name="outbox_aggregate_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} ({self.aggregate_type}:{self.aggregate_id})"

    def envelope(self) -> dict:
        """Build the canonical event envelope for publication."""

        return {
            "event_id": str(self.id),
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "organisation_id": str(self.organisation_id),
            "aggregate_type": self.aggregate_type,
            "aggregate_id": str(self.aggregate_id),
            "occurred_at": self.occurred_at.isoformat(),
            "recorded_at": self.created_at.isoformat(),
            "correlation_id": str(self.correlation_id),
            "causation_id": self.causation_id or None,
            "payload": self.payload,
        }


def write_outbox_event(
    *,
    organisation,
    aggregate_type: str,
    aggregate_id,
    event_type: str,
    payload: dict | None = None,
    occurred_at=None,
    correlation_id=None,
    causation_id: str = "",
    schema_version: int = 1,
) -> OutboxEvent:
    """Insert an outbox row.

    Call this inside the same ``transaction.atomic()`` block as the state
    change it describes.
    """

    from django.utils import timezone

    if occurred_at is None:
        occurred_at = timezone.now()

    kwargs = {
        "organisation": organisation,
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "event_type": event_type,
        "schema_version": schema_version,
        "payload": payload or {},
        "occurred_at": occurred_at,
        "causation_id": causation_id,
    }
    if correlation_id is not None:
        kwargs["correlation_id"] = correlation_id

    return OutboxEvent.objects.create(**kwargs)
