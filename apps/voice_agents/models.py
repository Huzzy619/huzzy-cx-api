"""Voice agent configuration and session models.

Kora CX is multi-tenant: a fintech configures its own voice agent through
versioned, immutable configuration records rather than deploying code. Tenant
users never submit executable graph definitions or arbitrary tool code.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.common.models import TimestampedModel, UUIDModel


class VoiceAgent(UUIDModel, TimestampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        ARCHIVED = "archived", "Archived"

    organisation = models.ForeignKey(
        "organisations.Organisation",
        on_delete=models.PROTECT,
        related_name="voice_agents",
    )
    contact_centre = models.ForeignKey(
        "contact_centres.ContactCentre",
        on_delete=models.PROTECT,
        related_name="voice_agents",
    )
    name = models.CharField(max_length=120)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    active_version = models.ForeignKey(
        "voice_agents.VoiceAgentVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "name"],
                name="uniq_voice_agent_name_per_org",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organisation", "status"],
                name="voice_agent_org_status_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class VoiceAgentVersion(UUIDModel, TimestampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    voice_agent = models.ForeignKey(
        VoiceAgent,
        on_delete=models.PROTECT,
        related_name="versions",
    )
    version = models.PositiveSmallIntegerField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    # Validated, non-executable configuration. Secrets are never stored here.
    config = models.JSONField(default=dict, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kora_published_voice_versions",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["voice_agent", "version"],
                name="uniq_voice_agent_version",
            ),
        ]
        indexes = [
            models.Index(
                fields=["voice_agent", "status"],
                name="voice_version_agent_status_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.voice_agent_id}:v{self.version}"

    @property
    def is_published(self) -> bool:
        return self.status == self.Status.PUBLISHED


class VoiceSession(UUIDModel, TimestampedModel):
    """One real-time execution of an interaction through the voice engine.

    An ``Interaction`` is the durable contact-centre record; a ``VoiceSession``
    is the live media/conversation execution and references the exact agent
    version used so a call can be investigated later.
    """

    class Status(models.TextChoices):
        INITIALIZING = "initializing", "Initializing"
        ACTIVE = "active", "Active"
        ENDED = "ended", "Ended"
        FAILED = "failed", "Failed"

    class AuthenticationStatus(models.TextChoices):
        NOT_REQUIRED = "not_required", "Not required"
        PENDING = "pending", "Pending"
        VERIFIED = "verified", "Verified"
        FAILED = "failed", "Failed"

    organisation = models.ForeignKey(
        "organisations.Organisation",
        on_delete=models.PROTECT,
        related_name="voice_sessions",
    )
    interaction = models.ForeignKey(
        "interactions.Interaction",
        on_delete=models.PROTECT,
        related_name="voice_sessions",
    )
    voice_agent_version = models.ForeignKey(
        VoiceAgentVersion,
        on_delete=models.PROTECT,
        related_name="sessions",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.INITIALIZING
    )
    engine_provider = models.CharField(max_length=40, default="livekit")
    room_name = models.CharField(max_length=255, blank=True)
    engine_session_reference = models.CharField(max_length=255, blank=True)
    language = models.CharField(max_length=20, default="en-NG")

    authentication_status = models.CharField(
        max_length=20,
        choices=AuthenticationStatus.choices,
        default=AuthenticationStatus.NOT_REQUIRED,
    )
    verified_customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="voice_sessions",
    )

    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    termination_reason = models.CharField(max_length=120, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["engine_provider", "room_name"],
                condition=~models.Q(room_name=""),
                name="uniq_voice_engine_room",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organisation", "status"],
                name="voice_session_org_status_idx",
            ),
            models.Index(
                fields=["interaction", "status"],
                name="voice_session_interaction_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"voice-session:{self.id}"

    def is_verified(self) -> bool:
        return (
            self.authentication_status == self.AuthenticationStatus.VERIFIED
            and self.verified_customer_id is not None
        )


class VoiceToolInvocation(UUIDModel, TimestampedModel):
    """Lifecycle record of a voicebot tool call.

    ``input_digest`` is a hash for correlation; raw sensitive arguments are
    never persisted. Security-relevant authorization decisions are also
    captured through the audit mechanism.
    """

    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        SUCCEEDED = "succeeded", "Succeeded"
        DENIED = "denied", "Denied"
        FAILED = "failed", "Failed"

    organisation = models.ForeignKey(
        "organisations.Organisation",
        on_delete=models.PROTECT,
        related_name="voice_tool_invocations",
    )
    voice_session = models.ForeignKey(
        VoiceSession,
        on_delete=models.CASCADE,
        related_name="tool_invocations",
    )
    interaction = models.ForeignKey(
        "interactions.Interaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="voice_tool_invocations",
    )
    tool_name = models.CharField(max_length=80)
    tool_version = models.CharField(max_length=20, default="1")
    idempotency_key = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.REQUESTED
    )
    requested_by = models.CharField(max_length=80, default="voice_worker")
    approved_by = models.CharField(max_length=80, blank=True)
    input_digest = models.CharField(max_length=64, blank=True)
    result_reference = models.CharField(max_length=255, blank=True)
    result = models.JSONField(default=dict, blank=True)
    error_code = models.CharField(max_length=80, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "idempotency_key"],
                name="uniq_voice_tool_idempotency",
            ),
        ]
        indexes = [
            models.Index(
                fields=["voice_session", "tool_name"],
                name="voice_tool_session_tool_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.tool_name}:{self.status}"
