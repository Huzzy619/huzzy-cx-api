"""Security tests for the internal voice worker API."""

from __future__ import annotations

import json

import pytest
from django.test import Client, override_settings

from apps.voice_agents.services import publish_voice_agent_version
from tests import factories

pytestmark = pytest.mark.security

WORKER_TOKEN = "test-worker-token"

INIT_PAYLOAD = {
    "provider_connection_id": "x",
    "provider_call_id": "y",
    "room_name": "z",
}


def _post(client, path, *, token=None, payload=None):
    headers = {}
    if token is not None:
        headers["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    return client.post(
        path,
        data=json.dumps(payload or {}),
        content_type="application/json",
        **headers,
    )


@pytest.fixture
def published_agent(db, organisation, contact_centre):
    agent = factories.VoiceAgentFactory(
        organisation=organisation, contact_centre=contact_centre
    )
    version = factories.VoiceAgentVersionFactory(voice_agent=agent, version=1)
    publish_voice_agent_version(version=version)
    agent.refresh_from_db()
    return agent


@override_settings(VOICE_WORKER_TOKEN=WORKER_TOKEN)
def test_worker_endpoint_requires_token(db):
    response = _post(
        Client(),
        "/api/v1/internal/voice/sessions/initialize",
        payload=INIT_PAYLOAD,
    )
    assert response.status_code == 401


@override_settings(VOICE_WORKER_TOKEN=WORKER_TOKEN)
def test_worker_endpoint_rejects_wrong_token(db):
    response = _post(
        Client(),
        "/api/v1/internal/voice/sessions/initialize",
        token="wrong",
        payload=INIT_PAYLOAD,
    )
    assert response.status_code == 401


@override_settings(VOICE_WORKER_TOKEN=WORKER_TOKEN)
def test_worker_can_initialize_session(db, published_agent, channel_connection):
    response = _post(
        Client(),
        "/api/v1/internal/voice/sessions/initialize",
        token=WORKER_TOKEN,
        payload={
            "provider_connection_id": channel_connection.provider_account_id,
            "provider_call_id": "provider-call-auth",
            "room_name": "room-auth",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["organisation_id"] == str(published_agent.organisation_id)
    assert body["voice_agent_version_id"] == str(published_agent.active_version_id)


@override_settings(VOICE_WORKER_TOKEN=WORKER_TOKEN)
def test_user_session_token_cannot_call_worker_api(
    db, published_agent, channel_connection
):
    user = factories.UserFactory()
    client = Client()
    client.force_login(user)
    response = _post(
        client,
        "/api/v1/internal/voice/sessions/initialize",
        token="test-token",
        payload={
            "provider_connection_id": channel_connection.provider_account_id,
            "provider_call_id": "provider-call-user",
            "room_name": "room-user",
        },
    )
    assert response.status_code == 401
