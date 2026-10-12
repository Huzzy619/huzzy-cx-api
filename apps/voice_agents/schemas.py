"""Voice agent schemas: configuration validation and API contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from ninja import Schema
from pydantic import BaseModel, ConfigDict, Field

# Tools the platform understands. Tenant configuration may only select from
# this set; it can never introduce new executable behaviour.
APPROVED_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "search_approved_knowledge",
        "get_transaction_status",
        "get_support_case",
        "create_support_case",
        "request_human_handoff",
        "end_interaction",
    }
)

# Tools that require a verified customer before they may run.
VERIFICATION_REQUIRED_TOOLS: frozenset[str] = frozenset(
    {
        "get_transaction_status",
        "get_support_case",
        "create_support_case",
    }
)


class WelcomeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str | None = Field(default=None, max_length=600)
    user_speak_first: bool = True


class TranscriptionConfig(BaseModel):
    """Speech pipeline selection. Endpoints live in worker settings, not here."""

    model_config = ConfigDict(extra="forbid")

    stt_model: str | None = Field(default=None, max_length=120)
    tts_model: str | None = Field(default=None, max_length=120)
    background_noise_denoising: bool = False
    speaker_diarization: bool = False


class SpeechConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    responsiveness: int = Field(default=5, ge=0, le=10)
    interruption_sensitivity: int = Field(default=5, ge=0, le=10)
    silence_reminder_interval: int = Field(default=5, ge=3, le=10)
    # Worker maps this to a LiveKit BuiltinAudioClip; unknown values are ignored.
    ambient_sound: str | None = Field(default=None, max_length=40)


class CallConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voice_mail_detection: bool = False
    end_call_after_silence: int | None = Field(default=None, ge=3)
    ringing_duration: int | None = Field(default=None, ge=3)
    media_encryption: str | None = Field(default=None, max_length=40)


class EscalationTriggerConditions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_asks_for_human: bool = False
    anger_or_frustration_detected: bool = False
    query_is_beyond_agent_scope: bool = False
    payment_dispute_raised: bool = False
    legal_compliance_topic: bool = False


class EscalationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enable_escalation: bool = False
    trigger_conditions: EscalationTriggerConditions | None = None
    call_transfer_number: str | None = Field(default=None, max_length=40)
    handoff_message: str | None = Field(default=None, max_length=600)
    email_addresses: list[str] = Field(default_factory=list)


class CallSecurityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sensitive_data_masking: bool = False
    post_call_data_extraction: bool = False


class VoiceAgentConfig(BaseModel):
    """Validated voice-agent configuration.

    Values are non-executable data. Provider credentials must not appear here.
    This schema is mirrored (Django-free) by the voice worker; keep both in
    sync.
    """

    model_config = ConfigDict(extra="forbid")

    greeting: str = Field(min_length=1, max_length=600)
    language: str = Field(default="en-NG", max_length=20)
    model: str = Field(min_length=1, max_length=120)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    voice: str | None = Field(default=None, max_length=80)
    system_prompt: str | None = Field(default=None, max_length=8000)
    tools: list[str] = Field(default_factory=list)
    default_queue_id: UUID | None = None
    max_call_seconds: int = Field(default=600, ge=30, le=3600)

    welcome_config: WelcomeConfig | None = None
    transcription_config: TranscriptionConfig | None = None
    speech_config: SpeechConfig | None = None
    call_config: CallConfig | None = None
    escalation_config: EscalationConfig | None = None
    call_security_config: CallSecurityConfig | None = None
    recording_disclosure: str | None = Field(default=None, max_length=600)
    read_recording_disclosure: bool = False

    def validate_tools(self) -> None:
        unknown = set(self.tools) - APPROVED_TOOL_NAMES
        if unknown:
            raise ValueError(
                f"Unsupported tools: {sorted(unknown)}"
            )


# ---------------------------------------------------------------------------
# Public configuration API
# ---------------------------------------------------------------------------


class VoiceAgentCreateInput(Schema):
    contact_centre_id: UUID
    name: str = Field(min_length=1, max_length=120)


class VoiceAgentVersionCreateInput(Schema):
    config: dict


class VoiceAgentVersionRead(Schema):
    id: UUID
    version: int
    status: str
    config: dict
    published_at: datetime | None = None


class VoiceAgentRead(Schema):
    id: UUID
    name: str
    status: str
    active_version_id: UUID | None = None


# ---------------------------------------------------------------------------
# Internal worker API
# ---------------------------------------------------------------------------


class SessionInitializeInput(Schema):
    provider_connection_id: str
    provider_call_id: str
    room_name: str = Field(min_length=1, max_length=255)
    language: str | None = None


class SessionInitializeOutput(Schema):
    interaction_id: UUID
    voice_session_id: UUID
    organisation_id: UUID
    voice_agent_version_id: UUID
    config: dict
    allowed_tools: list[str]
    greeting: str
    language: str


class TransactionStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voice_session_id: UUID
    transaction_reference: str = Field(min_length=1, max_length=120)
    idempotency_key: str = Field(min_length=1, max_length=255)


class TransactionStatusOutput(Schema):
    transaction_reference: str
    status: Literal[
        "pending",
        "successful",
        "failed",
        "reversed",
        "unknown",
    ]
    amount_display: str | None = None
    currency: str | None = None
    customer_message: str


class KnowledgeSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voice_session_id: UUID
    query: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=255)


class KnowledgeMatch(Schema):
    document_id: str
    title: str
    snippet: str


class KnowledgeSearchOutput(Schema):
    query: str
    matches: list[KnowledgeMatch]


class SupportCaseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voice_session_id: UUID
    reference: str | None = Field(default=None, max_length=64)
    subject: str | None = Field(default=None, max_length=255)
    idempotency_key: str = Field(min_length=1, max_length=255)


class SupportCaseOutput(Schema):
    reference: str
    subject: str
    status: str
    created_via: str


class HandoffInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voice_session_id: UUID
    queue_id: UUID | None = None
    reason: str = Field(default="", max_length=255)


class HandoffOutput(Schema):
    status: Literal["requested", "no_agent_available", "rejected"]
    queue_id: UUID | None = None
    fallback_message: str = ""


class SessionEventInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str = Field(min_length=1, max_length=100)
    source_event_id: str = Field(min_length=1, max_length=255)
    occurred_at: datetime | None = None
    payload: dict = Field(default_factory=dict)


class SessionEndInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="", max_length=120)


class SessionEndOutput(Schema):
    voice_session_id: UUID
    status: str
