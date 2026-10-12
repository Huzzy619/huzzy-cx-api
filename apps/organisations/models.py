"""Organisation, membership and team models.

A user is not assigned a single global role. Membership ties a user to an
organisation with a role that applies only within that organisation.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.common.models import TimestampedModel, UUIDModel


class Organisation(UUIDModel, TimestampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100, unique=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    timezone = models.CharField(max_length=64, default="Africa/Lagos")

    class Meta:
        indexes = [
            models.Index(fields=["status"], name="org_status_idx"),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.ACTIVE


class Membership(UUIDModel, TimestampedModel):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Administrator"
        SUPERVISOR = "supervisor", "Supervisor"
        AGENT = "agent", "Agent"
        COMPLIANCE = "compliance", "Compliance reviewer"

    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.PROTECT,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="kora_memberships",
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "user"],
                name="uniq_org_membership_user",
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "is_active"],
                name="membership_user_active_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}@{self.organisation_id} ({self.role})"


class Team(UUIDModel, TimestampedModel):
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.PROTECT,
        related_name="teams",
    )
    contact_centre = models.ForeignKey(
        "contact_centres.ContactCentre",
        on_delete=models.PROTECT,
        related_name="teams",
    )
    name = models.CharField(max_length=150)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "name"],
                name="uniq_team_name_per_org",
            ),
        ]

    def __str__(self) -> str:
        return self.name
