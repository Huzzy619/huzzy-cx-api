"""Mock telephony adapter.

Used in tests and local development so the inbound path can be exercised
without a selected vendor. It performs a simple shared-secret check and parses
a small documented JSON payload. The real adapter will be implemented once a
provider passes the capability proof of concept.
"""

from __future__ import annotations

import hashlib
import hmac
import json

from django.conf import settings

from apps.telephony.ports import (
    CanonicalVoiceEvent,
    InboundCallInstructions,
    ProviderCapabilities,
)


class MockTelephonyAdapter:
    provider_slug = "mock"

    def __init__(self, *, webhook_secret: str) -> None:
        self._webhook_secret = webhook_secret

    @classmethod
    def from_settings(cls) -> MockTelephonyAdapter:
        return cls(webhook_secret=settings.TELEPHONY_WEBHOOK_SECRET)

    def verify_webhook(self, *, headers: dict[str, str], body: bytes) -> bool:
        signature = _get_header(headers, "x-mock-signature")
        if not signature:
            return False
        expected = hmac.new(
            self._webhook_secret.encode(), body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(signature, expected)

    def parse_webhook(
        self, *, headers: dict[str, str], body: bytes
    ) -> list[CanonicalVoiceEvent]:
        payload = json.loads(body)
        events = payload.get("events") if isinstance(payload, dict) else None
        if events is None:
            events = [payload]
        return [
            CanonicalVoiceEvent(
                provider_connection_id=item["connection_id"],
                provider_call_id=item["call_id"],
                provider_event_id=item["event_id"],
                event_type=item["type"],
                occurred_at=item.get("occurred_at"),
                from_number=item.get("from"),
                to_number=item.get("to"),
                raw_event=item,
            )
            for item in events
        ]

    def build_inbound_instructions(
        self,
        *,
        call: CanonicalVoiceEvent,
        public_stream_url: str,
    ) -> InboundCallInstructions:
        return InboundCallInstructions(
            action="stream", parameters={"url": public_stream_url}
        )

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            inbound_voice=True,
            bidirectional_audio_stream=True,
            stream_audio_format="pcm_16",
            stream_transport="websocket",
            transfer=True,
            recording_access=False,
            recording_webhook=False,
        )


def _get_header(headers: dict[str, str], name: str) -> str | None:
    for key, value in headers.items():
        if key.lower() == name:
            return value
    return None
