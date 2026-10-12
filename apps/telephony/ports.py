"""Telephony adapter contract.

The adapter is the boundary between provider-specific webhook/audio semantics
and the rest of the platform. ``telephony.providers`` may depend on this
contract but must not own interaction business rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class CanonicalVoiceEvent:
    """A provider event normalised into the platform's own vocabulary."""

    provider_connection_id: str
    provider_call_id: str
    provider_event_id: str
    event_type: str
    occurred_at: str | None = None
    from_number: str | None = None
    to_number: str | None = None
    raw_event: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InboundCallInstructions:
    """Provider-neutral instructions the adapter translates for the provider.

    Some providers answer calls by returning instructions in the webhook
    response rather than through a separate API call.
    """

    action: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderCapabilities:
    inbound_voice: bool
    bidirectional_audio_stream: bool
    stream_audio_format: str | None
    stream_transport: str | None
    transfer: bool
    recording_access: bool
    recording_webhook: bool


@runtime_checkable
class TelephonyAdapter(Protocol):
    def verify_webhook(self, *, headers: dict[str, str], body: bytes) -> bool: ...

    def parse_webhook(
        self, *, headers: dict[str, str], body: bytes
    ) -> list[CanonicalVoiceEvent]: ...

    def build_inbound_instructions(
        self,
        *,
        call: CanonicalVoiceEvent,
        public_stream_url: str,
    ) -> InboundCallInstructions: ...

    def capabilities(self) -> ProviderCapabilities: ...
