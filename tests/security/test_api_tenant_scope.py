"""Security tests for tenant-scoped API access."""

from __future__ import annotations

import pytest
from django.test import Client

from apps.organisations.models import Membership
from tests import factories

pytestmark = pytest.mark.security


def _auth_headers(organisation_id) -> dict[str, str]:
    return {
        "HTTP_AUTHORIZATION": "Bearer test-token",
        "HTTP_X_ORGANISATION_ID": str(organisation_id),
    }


def test_agent_can_read_own_organisation_interaction(db):
    interaction = factories.InteractionFactory()
    user = factories.UserFactory()
    Membership.objects.create(
        organisation=interaction.organisation,
        user=user,
        role=Membership.Role.AGENT,
    )

    client = Client()
    client.force_login(user)
    response = client.get(
        f"/api/v1/interactions/{interaction.id}",
        **_auth_headers(interaction.organisation_id),
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(interaction.id)


def test_cross_tenant_interaction_is_not_disclosed(db):
    interaction = factories.InteractionFactory()
    outsider = factories.UserFactory()
    Membership.objects.create(
        organisation=factories.OrganisationFactory(),
        user=outsider,
        role=Membership.Role.AGENT,
    )

    client = Client()
    client.force_login(outsider)
    response = client.get(
        f"/api/v1/interactions/{interaction.id}",
        **_auth_headers(interaction.organisation_id),
    )

    # Membership of the target organisation is required; the resource must not
    # be disclosed to the outsider.
    assert response.status_code in {401, 403}


def test_unauthenticated_request_is_rejected(db):
    interaction = factories.InteractionFactory()
    response = Client().get(
        f"/api/v1/interactions/{interaction.id}",
        HTTP_AUTHORIZATION="Bearer test-token",
    )
    assert response.status_code == 401
