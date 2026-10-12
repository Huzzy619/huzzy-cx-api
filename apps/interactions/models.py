"""Interaction lifecycle models.

``interactions`` owns interaction lifecycle rules. The canonical status set is
independent of any provider's event names so provider-specific events can be
translated into a stable state machine (see ``apps.interactions.state``).
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models

from apps.common.models import TimestampedModel, UUIDModel
from apps.organisations.models import Organisation


class Interaction(UUIDModel, TimestampedModel):
    class Channel(models.TextChoices):
        VOICE = "voice", "Voice"

    class Direction(models.TextChoices):
        INBOUND = "inbound", "Inbound"
        OUTBOUND = "outbound", "Outbound"

    class Status(models.TextChoices):
        CREATED = "created", "Created"
        QUEUED = "queued", "Queued"
        ROUTING = "routing", "Routing"
        RINGING = "ringing", "Ringing"
        ACTIVE = "active", "Active"
        ON_HOLD = "on_hold", "On hold"
        TRANSFERRING = "transferring", "Transferring"
        ENDED = "ended", "Ended"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    class AIEnrichmentStatus(models.TextChoices):
        NOT_APPLICABLE = "not_applicable", "Not applicable"
        PENDING = "pending", "Pending"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.PROTECT,
        related_name="interactions",
    )
    contact_centre = models.ForeignKey(
        "contact_centres.ContactCentre",
        on_delete=models.PROTECT,
        related_name="interactions",
    )
    channel_connection = models.ForeignKey(
        "contact_centres.ChannelConnection",
        on_delete=models.PROTECT,
        related_name="interactions",
    )
    channel = models.CharField(max_length=20, choices=Channel.choices)
    direction = models.CharField(max_length=20, choices=Direction.choices)
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interactions",
    )
    queue = models.ForeignKey(
        "contact_centres.Queue",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interactions",
    )
    assigned_agent = models.ForeignKey(
        "agents.AgentProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interactions",
    )

    # Provider call identity, unique within its connection.
    provider_call_id = models.CharField(max_length=255)
    from_number = models.CharField(max_length=32, blank=True)
    to_number = models.CharField(max_length=32, blank=True)

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.CREATED
    )
    # AI enrichment is tracked separately: a summary failure must never turn a
    # completed call into a failed call.
    ai_enrichment_status = models.CharField(
        max_length=20,
        choices=AIEnrichmentStatus.choices,
        default=AIEnrichmentStatus.NOT_APPLICABLE,
    )

    started_at = models.DateTimeField(null=True, blank=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    disposition_code = models.CharField(max_length=80, blank=True)
    correlation_id = models.UUIDField(default=uuid.uuid4)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["channel_connection", "provider_call_id"],
                name="uniq_provider_call_per_connection",
            ),
            models.CheckConstraint(
                condition=models.Q(ended_at__isnull=True)
                | models.Q(answered_at__isnull=True)
                | models.Q(ended_at__gte=models.F("answered_at")),
                name="interaction_ended_after_answered",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organisation", "-started_at"],
                name="interaction_org_started_idx",
            ),
            models.Index(
                fields=["organisation", "status", "queue"],
                name="interaction_org_queue_idx",
            ),
            models.Index(
                fields=["organisation", "assigned_agent", "status"],
                name="interaction_org_agent_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.channel}:{self.provider_call_id} ({self.status})"

    @property
    def is_terminal(self) -> bool:
        return self.status in {self.Status.COMPLETED, self.Status.FAILED}


class InteractionParticipant(UUIDModel, TimestampedModel):
    class ParticipantType(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        AGENT = "agent", "Agent"
        VOICEBOT = "voicebot", "Voicebot"
        SUPERVISOR = "supervisor", "Supervisor"

    interaction = models.ForeignKey(
        Interaction,
        on_delete=models.CASCADE,
        related_name="participants",
    )
    participant_type = models.CharField(
        max_length=20, choices=ParticipantType.choices
    )
    participant_reference = models.CharField(max_length=255)
    joined_at = models.DateTimeField(null=True, blank=True)
    left_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["interaction", "participant_type"],
                name="participant_interaction_idx",
            ),
        ]


class InteractionEvent(UUIDModel):
    """Append-only record of an event that affected an interaction.

    Uniqueness is scoped by source so provider event IDs that are only unique
    per connection cannot collide across providers.
    """

    class Source(models.TextChoices):
        PROVIDER = "provider", "Provider"
        AGENT = "agent", "Agent"
        SYSTEM = "system", "System"
        WORKFLOW = "workflow", "Workflow"
        API = "api", "API"
        VOICE_AGENT = "voice_agent", "Voice agent"

    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.PROTECT,
        related_name="interaction_events",
    )
    interaction = models.ForeignKey(
        Interaction,
        on_delete=models.PROTECT,
        related_name="events",
    )
    source = models.CharField(max_length=20, choices=Source.choices)
    # For provider events this is the channel connection / provider account so
    # the dedup key is scoped correctly.
    source_scope = models.CharField(max_length=255, blank=True)
    source_event_id = models.CharField(max_length=255)
    event_type = models.CharField(max_length=100)

    occurred_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "source_scope", "source_event_id"],
                name="uniq_interaction_source_event",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organisation", "interaction", "received_at"],
                name="interaction_event_time_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.source}:{self.event_type}:{self.source_event_id}"


class InteractionAssignment(UUIDModel, TimestampedModel):
    class Status(models.TextChoices):
        OFFERED = "offered", "Offered"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        TIMED_OUT = "timed_out", "Timed out"
        ENDED = "ended", "Ended"

    interaction = models.ForeignKey(
        Interaction,
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    queue = models.ForeignKey(
        "contact_centres.Queue",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assignments",
    )
    agent = models.ForeignKey(
        "agents.AgentProfile",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assignments",
    )
    attempt_id = models.UUIDField(default=uuid.uuid4, unique=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OFFERED
    )
    assigned_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["interaction", "attempt_id"],
                name="uniq_assignment_attempt",
            ),
        ]
        indexes = [
            models.Index(
                fields=["interaction", "status"],
                name="assignment_interaction_idx",
            ),
            models.Index(
                fields=["agent", "status"],
                name="assignment_agent_status_idx",
            ),
        ]


class InteractionSummary(UUIDModel, TimestampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        REVIEWED = "reviewed", "Reviewed"

    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.PROTECT,
        related_name="interaction_summaries",
    )
    interaction = models.ForeignKey(
        Interaction,
        on_delete=models.CASCADE,
        related_name="summaries",
    )
    version = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    summary = models.TextField(blank=True)
    structured_outcome = models.JSONField(default=dict, blank=True)
    model_name = models.CharField(max_length=150, blank=True)
    prompt_version = models.CharField(max_length=50, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kora_reviewed_summaries",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["interaction", "version"],
                name="uniq_summary_version_per_interaction",
            ),
        ]

    def __str__(self) -> str:
        return f"summary:{self.interaction_id}:v{self.version}"
