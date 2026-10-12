"""Interaction API endpoints.

Handlers resolve an authenticated principal and an organisation-scoped
interaction. Fast lookups by UUID are not a substitute for authorisation: the
query is always scoped to the principal's organisation.
"""

from __future__ import annotations

from uuid import UUID

from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.errors import HttpError

from apps.common.exceptions import KoraError
from apps.common.permissions import Permission
from apps.interactions.models import Interaction
from apps.interactions.schemas import (
    DispositionInput,
    InteractionRead,
    TransferInput,
)
from apps.interactions.services import submit_disposition
from apps.organisations.auth import SessionMembershipAuth

router = Router(tags=["interactions"], auth=SessionMembershipAuth())


def get_authorised_interaction(request, interaction_id: UUID) -> Interaction:
    principal = request.auth
    return get_object_or_404(
        Interaction.objects.select_related("queue", "customer").filter(
            organisation_id=principal.organisation_id,
        ),
        id=interaction_id,
    )


@router.get("/{interaction_id}", response=InteractionRead)
def get_interaction(request, interaction_id: UUID):
    interaction = get_authorised_interaction(request, interaction_id)
    principal = request.auth
    if not (
        principal.has_permission(Permission.INTERACTIONS_READ_QUEUE)
        or principal.has_permission(Permission.INTERACTIONS_READ_ASSIGNED)
    ):
        raise HttpError(403, "You cannot access this interaction.")
    return interaction


@router.post("/{interaction_id}/disposition", response={200: dict})
def post_disposition(
    request,
    interaction_id: UUID,
    payload: DispositionInput,
):
    interaction = get_authorised_interaction(request, interaction_id)
    request.auth.require(Permission.INTERACTIONS_DISPOSITION)
    try:
        updated = submit_disposition(
            interaction_id=interaction.id,
            code=payload.code,
            notes=payload.notes,
            actor=request.auth,
        )
    except KoraError as exc:
        raise HttpError(exc.http_status, exc.message) from exc
    return {"id": str(updated.id), "disposition_code": updated.disposition_code}


@router.post("/{interaction_id}/transfer", response={202: dict})
def post_transfer(
    request,
    interaction_id: UUID,
    payload: TransferInput,
):
    interaction = get_authorised_interaction(request, interaction_id)
    request.auth.require(Permission.INTERACTIONS_TRANSFER)
    # Transfer must be coordinated with the telephony provider. This endpoint
    # only records the request and returns 202; it must not claim the external
    # call has moved.
    from apps.routing.services import request_transfer

    try:
        result = request_transfer(
            interaction=interaction,
            destination_queue_id=payload.queue_id,
            actor=request.auth,
        )
    except KoraError as exc:
        raise HttpError(exc.http_status, exc.message) from exc
    return {
        "status": "accepted",
        "interaction_id": str(interaction.id),
        "transfer_request_id": str(result.transfer_request_id),
    }
