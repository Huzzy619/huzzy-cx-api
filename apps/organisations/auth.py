"""Request principal resolution.

Every request must resolve an authenticated user and an active organisation
membership. The client is never trusted to choose an organisation directly:
the supplied organisation id is validated against the user's memberships.
"""

from __future__ import annotations

from ninja.security import HttpBearer

from apps.common.exceptions import PermissionDeniedError
from apps.common.permissions import Principal
from apps.organisations.models import Membership


def resolve_principal(*, user, organisation_id) -> Principal:
    if user is None or not getattr(user, "is_authenticated", False):
        raise PermissionDeniedError("Authentication required.")

    memberships = Membership.objects.filter(user=user, is_active=True).select_related(
        "organisation"
    )
    if organisation_id is not None:
        membership = memberships.filter(organisation_id=organisation_id).first()
        if membership is None:
            raise PermissionDeniedError(
                "You are not a member of this organisation.",
                organisation_id=str(organisation_id),
            )
    else:
        membership = memberships.first()
        if membership is None:
            raise PermissionDeniedError("No active organisation membership.")

    if not membership.organisation.is_active:
        raise PermissionDeniedError("Organisation is not active.")

    return Principal.from_role(
        user_id=user.id,
        organisation_id=membership.organisation_id,
        role=membership.role,
    )


class SessionMembershipAuth(HttpBearer):
    """Bearer-token placeholder that resolves the user from the Django session.

    The token value is ignored; this exists so the API surface is wired to a
    principal while the enterprise identity backend is selected. Replace the
    body with the deployment's token/session verification.
    """

    def authenticate(self, request, token):  # noqa: ARG002
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None
        organisation_id = request.headers.get("x-organisation-id")
        try:
            return resolve_principal(user=user, organisation_id=organisation_id)
        except PermissionDeniedError:
            return None
