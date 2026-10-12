"""Authentication for the internal voice worker API.

The worker authenticates as a service identity, separate from end-user
authentication. In production this is replaced by workload identity or
short-lived service credentials; the shared-secret comparison here is a
placeholder that still uses constant-time comparison and fails closed.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass

from django.conf import settings
from ninja.security import HttpBearer


@dataclass(frozen=True)
class VoiceWorkerPrincipal:
    worker_id: str
    kind: str = "voice_worker"


class VoiceWorkerAuth(HttpBearer):
    def authenticate(self, request, token):  # noqa: ARG002
        expected = settings.VOICE_WORKER_TOKEN
        if not expected:
            return None
        if not hmac.compare_digest(token or "", expected):
            return None
        return VoiceWorkerPrincipal(worker_id="voice-worker")
