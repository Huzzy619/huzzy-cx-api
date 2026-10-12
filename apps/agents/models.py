"""Agent profile and queue membership models.

These records are durable configuration. An agent's real-time *presence* is
ephemeral operational state and lives in Redis (see ``apps.agents.presence``).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.common.models import TimestampedModel, UUIDModel
from apps.contact_centres.models import Queue
from apps.organisations.models import Organisation


class AgentProfile(UUIDModel, TimestampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        DISABLED = "disabled", "Disabled"

    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.PROTECT,
        related_name="agents",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="kora_agent_profiles",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    skills = models.JSONField(default=list, blank=True)
    languages = models.JSONField(default=list, blank=True)
    max_concurrent_voice_calls = models.PositiveSmallIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "user"],
                name="uniq_agent_user_per_org",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organisation", "status"],
                name="agent_org_status_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"agent:{self.user_id}"

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.ACTIVE


class AgentQueueMembership(UUIDModel, TimestampedModel):
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.PROTECT,
        related_name="agent_queue_memberships",
    )
    agent = models.ForeignKey(
        AgentProfile,
        on_delete=models.CASCADE,
        related_name="queue_memberships",
    )
    queue = models.ForeignKey(
        Queue,
        on_delete=models.CASCADE,
        related_name="agent_memberships",
    )
    priority = models.PositiveSmallIntegerField(default=100)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["agent", "queue"],
                name="uniq_agent_queue",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organisation", "queue", "agent"],
                name="agentqueue_org_queue_agent_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.agent_id}->{self.queue_id}"
