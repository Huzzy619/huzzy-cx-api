"""Telephony webhook endpoints.

The webhook handler does the minimum work needed to acknowledge the provider:
verify the signature, parse the event and persist it idempotently. It must not
run transcriptions, large lookups or LLM requests here.
"""

from __future__ import annotations

import json

from ninja import Router
from ninja.errors import HttpError

from apps.common.exceptions import KoraError
from apps.telephony.registry import get_telephony_adapter
from apps.telephony.services import ingest_provider_events

router = Router(tags=["telephony-webhooks"])


@router.post("/{provider}", response={200: dict}, auth=None)
def receive_provider_webhook(request, provider: str):
    if provider != "mock":
        raise HttpError(404, "Unknown provider.")

    adapter = get_telephony_adapter()
    body = request.body
    headers = dict(request.headers)

    if not adapter.verify_webhook(headers=headers, body=body):
        raise HttpError(401, "Invalid webhook signature.")

    try:
        events = adapter.parse_webhook(headers=headers, body=body)
    except (ValueError, json.JSONDecodeError, KeyError) as exc:
        raise HttpError(400, "Invalid webhook payload.") from exc

    try:
        summary = ingest_provider_events(events=events)
    except KoraError as exc:
        raise HttpError(exc.http_status, exc.message) from exc

    return {"accepted": summary.accepted, "duplicates": summary.duplicates}
