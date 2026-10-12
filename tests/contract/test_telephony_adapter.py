"""Contract tests for the telephony adapter.

Every provider adapter must satisfy the same contract. The mock adapter is
exercised here; the real adapter must pass the identical tests against its
sandbox.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from apps.telephony.providers.mock import MockTelephonyAdapter

pytestmark = pytest.mark.contract

SECRET = "test-secret"


@pytest.fixture
def adapter():
    return MockTelephonyAdapter(webhook_secret=SECRET)


def _signed(body: bytes, secret: str = SECRET) -> dict[str, str]:
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return {"x-mock-signature": signature}


def test_valid_signature_is_accepted(adapter):
    body = json.dumps({"events": []}).encode()
    assert adapter.verify_webhook(headers=_signed(body), body=body) is True


def test_invalid_signature_is_rejected(adapter):
    body = json.dumps({"events": []}).encode()
    is_valid = adapter.verify_webhook(
        headers={"x-mock-signature": "nope"}, body=body
    )
    assert is_valid is False
    assert adapter.verify_webhook(headers={}, body=body) is False


def test_parse_webhook_normalises_events(adapter):
    payload = {
        "events": [
            {
                "connection_id": "acct-1",
                "call_id": "call-1",
                "event_id": "evt-1",
                "type": "call.started",
                "occurred_at": "2026-10-12T10:30:00Z",
                "from": "+2348011111111",
                "to": "+2348000000000",
            }
        ]
    }
    body = json.dumps(payload).encode()

    events = adapter.parse_webhook(headers=_signed(body), body=body)

    assert len(events) == 1
    event = events[0]
    assert event.provider_connection_id == "acct-1"
    assert event.provider_call_id == "call-1"
    assert event.provider_event_id == "evt-1"
    assert event.event_type == "call.started"


def test_parse_webhook_accepts_single_event(adapter):
    payload = {
        "connection_id": "acct-1",
        "call_id": "call-1",
        "event_id": "evt-1",
        "type": "call.ended",
    }
    body = json.dumps(payload).encode()

    events = adapter.parse_webhook(headers=_signed(body), body=body)

    assert [e.event_type for e in events] == ["call.ended"]


def test_capabilities_declared_explicitly(adapter):
    capabilities = adapter.capabilities()
    assert capabilities.inbound_voice is True
    assert capabilities.bidirectional_audio_stream is True
    assert capabilities.transfer is True
    assert capabilities.recording_access is False
