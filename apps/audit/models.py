"""Audit events.

Audit rows record who did what to which resource. They are append-only at the
application level and never store secrets or full sensitive payloads.
"""

from __future__ import annotations

import uuid

from django.db import models

from apps.common.models import UUIDModel


class AuditEvent(UUIDModel):
    class ActorType(models.TextChoices):
        USER = "user", "User"
        AGENT = "agent", "Agent"
        SYSTEM = "system", "System"
        AI = "ai", "AI"
        INTEGRATION = "integration", "Integration"

    organisation = models.ForeignKey(
        "organisations.Organisation",
        on_delete=models.PROTECT,
        related_name="audit_events",
    )
    actor_type = models.CharField(max_length=20, choices=ActorType.choices)
    actor_id = models.CharField(max_length=255, blank=True)
    action = models.CharField(max_length=120)
    resource_type = models.CharField(max_length=80)
    resource_id = models.CharField(max_length=255, blank=True)
    occurred_at = models.DateTimeField()
    correlation_id = models.UUIDField(default=uuid.uuid4)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["organisation", "-occurred_at"],
                name="audit_org_occurred_idx",
            ),
            models.Index(
                fields=["resource_type", "resource_id"],
                name="audit_resource_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.action}:{self.resource_type}:{self.resource_id}"


def record_audit_event(
    *,
    organisation,
    actor_type: str,
    action: str,
    resource_type: str,
    resource_id: str = "",
    actor_id: str = "",
    correlation_id=None,
    metadata: dict | None = None,
) -> AuditEvent:
    from django.utils import timezone

    kwargs = {
        "organisation": organisation,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "occurred_at": timezone.now(),
        "metadata": metadata or {},
    }
    if correlation_id is not None:
        kwargs["correlation_id"] = correlation_id
    return AuditEvent.objects.create(**kwargs)
