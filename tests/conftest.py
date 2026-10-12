"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from apps.telephony.ports import CanonicalVoiceEvent
from tests import factories


@pytest.fixture
def organisation(db):
    return factories.OrganisationFactory()


@pytest.fixture
def contact_centre(db, organisation):
    return factories.ContactCentreFactory(organisation=organisation)


@pytest.fixture
def channel_connection(db, organisation, contact_centre):
    return factories.ChannelConnectionFactory(
        organisation=organisation,
        contact_centre=contact_centre,
        provider_account_id="test-account",
    )


@pytest.fixture
def call_started_event(channel_connection):
    return CanonicalVoiceEvent(
        provider_connection_id=channel_connection.provider_account_id,
        provider_call_id="provider-call-1",
        provider_event_id="evt-started-1",
        event_type="call.started",
        occurred_at="2026-10-12T10:30:00Z",
        from_number="+2348011111111",
        to_number=channel_connection.inbound_number,
        raw_event={"type": "call.started"},
    )
