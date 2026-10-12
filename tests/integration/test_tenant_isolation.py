"""Tenant isolation tests."""

from __future__ import annotations

import pytest

from apps.common.exceptions import TenantIsolationError, ValidationError
from apps.routing.services import request_transfer
from apps.telephony.ports import CanonicalVoiceEvent
from apps.telephony.services import ingest_provider_event
from tests import factories

pytestmark = pytest.mark.integration


def test_ingested_interaction_inherits_connection_organisation(db):
    org = factories.OrganisationFactory()
    other_org = factories.OrganisationFactory()
    contact_centre = factories.ContactCentreFactory(organisation=org)
    factories.ChannelConnectionFactory(
        organisation=org,
        contact_centre=contact_centre,
        provider_account_id="acct-tenant",
    )

    result = ingest_provider_event(
        event=CanonicalVoiceEvent(
            provider_connection_id="acct-tenant",
            provider_call_id="call-tenant",
            provider_event_id="evt-tenant",
            event_type="call.started",
        )
    )

    interaction = result.interaction
    assert interaction.organisation_id == org.id
    assert interaction.organisation_id != other_org.id
    # The related tenant-scoped records all share the same organisation.
    assert interaction.contact_centre.organisation_id == org.id
    assert interaction.channel_connection.organisation_id == org.id


def test_assert_same_organisation_rejects_cross_tenant(db):
    from apps.common.tenancy import assert_same_organisation
    from apps.customers.models import Customer

    org = factories.OrganisationFactory()
    foreign_customer = Customer.objects.create(
        organisation=factories.OrganisationFactory(),
        display_name="Foreign",
    )

    with pytest.raises(TenantIsolationError):
        assert_same_organisation(
            organisation=org,
            objects=[("customer", foreign_customer)],
        )


def test_transfer_to_foreign_queue_is_rejected(db):
    interaction = factories.InteractionFactory()
    foreign_queue = factories.QueueFactory()  # different organisation

    with pytest.raises(TenantIsolationError):
        request_transfer(
            interaction=interaction,
            destination_queue_id=foreign_queue.id,
        )


def test_transfer_to_same_tenant_queue_is_recorded(db):
    interaction = factories.InteractionFactory()
    interaction.status = interaction.Status.ACTIVE
    interaction.save(update_fields=["status"])
    queue = factories.QueueFactory(organisation=interaction.organisation)

    result = request_transfer(
        interaction=interaction,
        destination_queue_id=queue.id,
    )

    assert result.interaction_id == interaction.id
    assert result.destination_queue_id == queue.id


def test_transfer_of_terminal_interaction_fails(db):
    from apps.interactions.models import Interaction

    interaction = factories.InteractionFactory(status=Interaction.Status.COMPLETED)
    queue = factories.QueueFactory(organisation=interaction.organisation)

    with pytest.raises(ValidationError):
        request_transfer(
            interaction=interaction,
            destination_queue_id=queue.id,
        )
