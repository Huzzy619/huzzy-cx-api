"""Factory Boy factories for Kora CX domain models."""

from __future__ import annotations

import factory
from django.contrib.auth import get_user_model

from apps.agents.models import AgentProfile, AgentQueueMembership
from apps.contact_centres.models import ChannelConnection, ContactCentre, Queue
from apps.customers.models import Customer, CustomerIdentifier
from apps.integrations.models import SupportCase
from apps.interactions.models import Interaction
from apps.organisations.models import Membership, Organisation, Team
from apps.voice_agents.models import (
    VoiceAgent,
    VoiceAgentVersion,
    VoiceSession,
)

DEFAULT_VOICE_CONFIG = {
    "greeting": "Hello, thanks for calling Kora CX. How can I help?",
    "language": "en-NG",
    "model": "test-model",
    "temperature": 0.0,
    "tools": [
        "search_approved_knowledge",
        "get_transaction_status",
        "request_human_handoff",
    ],
    "max_call_seconds": 600,
}

User = get_user_model()


class OrganisationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Organisation

    name = factory.Sequence(lambda n: f"Organisation {n}")
    slug = factory.Sequence(lambda n: f"organisation-{n}")


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ("username",)

    username = factory.Sequence(lambda n: f"user-{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@example.com")


class MembershipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Membership

    organisation = factory.SubFactory(OrganisationFactory)
    user = factory.SubFactory(UserFactory)
    role = Membership.Role.AGENT


class ContactCentreFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ContactCentre

    organisation = factory.SubFactory(OrganisationFactory)
    name = factory.Sequence(lambda n: f"Contact Centre {n}")


class TeamFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Team

    organisation = factory.SubFactory(OrganisationFactory)
    contact_centre = factory.SubFactory(
        ContactCentreFactory, organisation=factory.SelfAttribute("..organisation")
    )
    name = factory.Sequence(lambda n: f"Team {n}")


class QueueFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Queue

    organisation = factory.SubFactory(OrganisationFactory)
    contact_centre = factory.SubFactory(
        ContactCentreFactory, organisation=factory.SelfAttribute("..organisation")
    )
    name = factory.Sequence(lambda n: f"Queue {n}")


class ChannelConnectionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ChannelConnection

    organisation = factory.SubFactory(OrganisationFactory)
    contact_centre = factory.SubFactory(
        ContactCentreFactory, organisation=factory.SelfAttribute("..organisation")
    )
    channel = ChannelConnection.Channel.VOICE
    provider = "mock"
    provider_account_id = factory.Sequence(lambda n: f"account-{n}")
    inbound_number = factory.Sequence(lambda n: f"+234800000{n:04d}")
    credential_reference = "secret://kora/telephony/mock"
    status = ChannelConnection.Status.ACTIVE


class AgentProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AgentProfile

    organisation = factory.SubFactory(OrganisationFactory)
    user = factory.SubFactory(UserFactory)
    status = AgentProfile.Status.ACTIVE


class AgentQueueMembershipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AgentQueueMembership

    organisation = factory.SubFactory(OrganisationFactory)
    agent = factory.SubFactory(
        AgentProfileFactory, organisation=factory.SelfAttribute("..organisation")
    )
    queue = factory.SubFactory(
        QueueFactory, organisation=factory.SelfAttribute("..organisation")
    )


class CustomerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Customer

    organisation = factory.SubFactory(OrganisationFactory)
    display_name = factory.Sequence(lambda n: f"Customer {n}")


class CustomerIdentifierFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CustomerIdentifier

    organisation = factory.SubFactory(OrganisationFactory)
    customer = factory.SubFactory(
        CustomerFactory, organisation=factory.SelfAttribute("..organisation")
    )
    identifier_type = CustomerIdentifier.Type.PHONE
    normalized_value = factory.Sequence(lambda n: f"+23490000{n:04d}")


class VoiceAgentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = VoiceAgent

    organisation = factory.SubFactory(OrganisationFactory)
    contact_centre = factory.SubFactory(
        ContactCentreFactory, organisation=factory.SelfAttribute("..organisation")
    )
    name = factory.Sequence(lambda n: f"Voice Agent {n}")
    status = VoiceAgent.Status.DRAFT


class VoiceAgentVersionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = VoiceAgentVersion

    voice_agent = factory.SubFactory(VoiceAgentFactory)
    version = factory.Sequence(lambda n: n + 1)
    status = VoiceAgentVersion.Status.DRAFT
    config = factory.LazyFunction(lambda: dict(DEFAULT_VOICE_CONFIG))


class SupportCaseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SupportCase

    organisation = factory.SubFactory(OrganisationFactory)
    customer = factory.SubFactory(
        CustomerFactory, organisation=factory.SelfAttribute("..organisation")
    )
    reference = factory.Sequence(lambda n: f"CASE-{n:05d}")
    subject = "Test case"


class InteractionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Interaction

    organisation = factory.SubFactory(OrganisationFactory)
    contact_centre = factory.SubFactory(
        ContactCentreFactory, organisation=factory.SelfAttribute("..organisation")
    )
    channel_connection = factory.SubFactory(
        ChannelConnectionFactory,
        organisation=factory.SelfAttribute("..organisation"),
        contact_centre=factory.SelfAttribute("..contact_centre"),
    )
    channel = Interaction.Channel.VOICE
    direction = Interaction.Direction.INBOUND
    provider_call_id = factory.Sequence(lambda n: f"call-{n}")
    status = Interaction.Status.CREATED


class VoiceSessionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = VoiceSession

    organisation = factory.SubFactory(OrganisationFactory)
    interaction = factory.SubFactory(
        InteractionFactory, organisation=factory.SelfAttribute("..organisation")
    )
    voice_agent_version = factory.SubFactory(VoiceAgentVersionFactory)
    status = VoiceSession.Status.INITIALIZING
    engine_provider = "livekit"
    room_name = factory.Sequence(lambda n: f"room-{n}")
    language = "en-NG"
