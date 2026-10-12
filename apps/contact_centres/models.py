"""Contact centre, queue and channel connection models."""

from __future__ import annotations

from django.db import models

from apps.common.models import TimestampedModel, UUIDModel
from apps.organisations.models import Organisation


class ContactCentre(UUIDModel, TimestampedModel):
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.PROTECT,
        related_name="contact_centres",
    )
    name = models.CharField(max_length=150)
    timezone = models.CharField(max_length=64, default="Africa/Lagos")
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "name"],
                name="uniq_contact_centre_name_per_org",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Queue(UUIDModel, TimestampedModel):
    class RoutingStrategy(models.TextChoices):
        ROUND_ROBIN = "round_robin", "Round robin"
        LONGEST_IDLE = "longest_idle", "Longest idle"

    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.PROTECT,
        related_name="queues",
    )
    contact_centre = models.ForeignKey(
        ContactCentre,
        on_delete=models.PROTECT,
        related_name="queues",
    )
    name = models.CharField(max_length=150)
    routing_strategy = models.CharField(
        max_length=20,
        choices=RoutingStrategy.choices,
        default=RoutingStrategy.ROUND_ROBIN,
    )
    overflow_queue = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="overflow_sources",
    )
    max_wait_seconds = models.PositiveIntegerField(default=60)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "name"],
                name="uniq_queue_name_per_org",
            ),
            # A queue cannot overflow to itself.
            models.CheckConstraint(
                condition=~models.Q(overflow_queue=models.F("id")),
                name="queue_no_self_overflow",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organisation", "is_active"],
                name="queue_org_active_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class ChannelConnection(UUIDModel, TimestampedModel):
    class Channel(models.TextChoices):
        VOICE = "voice", "Voice"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        DISABLED = "disabled", "Disabled"

    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.PROTECT,
        related_name="channel_connections",
    )
    contact_centre = models.ForeignKey(
        ContactCentre,
        on_delete=models.PROTECT,
        related_name="channel_connections",
    )
    channel = models.CharField(max_length=20, choices=Channel.choices)
    provider = models.CharField(max_length=80)
    provider_account_id = models.CharField(max_length=200)
    inbound_number = models.CharField(max_length=32)
    # Points at a secret manager entry. Never store the raw provider secret.
    credential_reference = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_account_id", "inbound_number"],
                name="uniq_provider_inbound_number",
            ),
        ]
        indexes = [
            models.Index(
                fields=["provider", "provider_account_id"],
                name="channel_provider_account_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.inbound_number}"

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.ACTIVE
