"""Support case services used by the voicebot tools."""

from __future__ import annotations

import uuid

from django.db import transaction

from apps.integrations.models import SupportCase


@transaction.atomic
def create_support_case(
    *,
    organisation,
    customer=None,
    subject: str,
    reference: str | None = None,
    created_via: str = SupportCase.CreatedVia.VOICE,
) -> SupportCase:
    if not reference:
        reference = f"CASE-{uuid.uuid4().hex[:10].upper()}"
    case, _ = SupportCase.objects.get_or_create(
        organisation=organisation,
        reference=reference,
        defaults={
            "customer": customer,
            "subject": subject,
            "created_via": created_via,
            "status": SupportCase.Status.OPEN,
        },
    )
    return case


def get_support_case(*, organisation, customer, reference: str) -> SupportCase | None:
    return SupportCase.objects.filter(
        organisation=organisation,
        customer=customer,
        reference=reference,
    ).first()
