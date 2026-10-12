"""Support case records created through approved integrations or the voicebot.

Case data stays minimal: the authoritative case may live in the customer's own
ticketing system, and this record holds the reference and status needed to
support the caller.
"""

from __future__ import annotations

from django.db import models

from apps.common.models import TimestampedModel, UUIDModel


class SupportCase(UUIDModel, TimestampedModel):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        PENDING = "pending", "Pending"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    class CreatedVia(models.TextChoices):
        VOICE = "voice", "Voice agent"
        MANUAL = "manual", "Manual"
        INTEGRATION = "integration", "Integration"

    organisation = models.ForeignKey(
        "organisations.Organisation",
        on_delete=models.PROTECT,
        related_name="support_cases",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_cases",
    )
    reference = models.CharField(max_length=64)
    subject = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OPEN
    )
    external_reference = models.CharField(max_length=255, blank=True)
    created_via = models.CharField(
        max_length=20, choices=CreatedVia.choices, default=CreatedVia.VOICE
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "reference"],
                name="uniq_support_case_reference_per_org",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organisation", "status"],
                name="support_case_org_status_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.reference
