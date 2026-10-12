"""Django-free mirror of the platform voice-agent configuration.

The platform validates configuration before publishing; the worker re-validates
(the same JSON arrives in the session-initialize response). ``extra="ignore"``
keeps an older worker forward-compatible when the platform adds fields.

Keep this in sync with ``apps.voice_agents.schemas.VoiceAgentConfig``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class WelcomeConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: str | None = None
    user_speak_first: bool = True


class TranscriptionConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    stt_model: str | None = None
    tts_model: str | None = None
    background_noise_denoising: bool = False
    speaker_diarization: bool = False


class SpeechConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    responsiveness: int = Field(default=5, ge=0, le=10)
    interruption_sensitivity: int = Field(default=5, ge=0, le=10)
    silence_reminder_interval: int = Field(default=5, ge=3, le=10)
    ambient_sound: str | None = None


class CallConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    voice_mail_detection: bool = False
    end_call_after_silence: int | None = None
    ringing_duration: int | None = None
    media_encryption: str | None = None


class EscalationTriggerConditions(BaseModel):
    model_config = ConfigDict(extra="ignore")

    customer_asks_for_human: bool = False
    anger_or_frustration_detected: bool = False
    query_is_beyond_agent_scope: bool = False
    payment_dispute_raised: bool = False
    legal_compliance_topic: bool = False


class EscalationConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enable_escalation: bool = False
    trigger_conditions: EscalationTriggerConditions | None = None
    call_transfer_number: str | None = None
    handoff_message: str | None = None
    email_addresses: list[str] = Field(default_factory=list)


class CallSecurityConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sensitive_data_masking: bool = False
    post_call_data_extraction: bool = False


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    greeting: str = "Hello, how can I help?"
    language: str = "en-NG"
    model: str = "openai/gpt-4o-mini"
    temperature: float = 0.0
    voice: str | None = None
    system_prompt: str | None = None
    tools: list[str] = Field(default_factory=list)
    max_call_seconds: int = 600

    welcome_config: WelcomeConfig | None = None
    transcription_config: TranscriptionConfig | None = None
    speech_config: SpeechConfig | None = None
    call_config: CallConfig | None = None
    escalation_config: EscalationConfig | None = None
    call_security_config: CallSecurityConfig | None = None
    recording_disclosure: str | None = None
    read_recording_disclosure: bool = False


def parse_agent_config(raw: dict | None) -> AgentConfig:
    if not raw:
        return AgentConfig()
    return AgentConfig.model_validate(raw)
