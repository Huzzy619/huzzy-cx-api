"""Ephemeral agent presence.

Presence is stored in Redis with an expiring lease. An abandoned browser tab
must not leave an agent available forever, so the lease is refreshed by a
heartbeat and treated as ``offline`` once it lapses. Durable assignments and
configuration remain in PostgreSQL.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from django.conf import settings
from django.core.cache import cache


class PresenceStatus(StrEnum):
    AVAILABLE = "available"
    BUSY = "busy"
    AWAY = "away"
    OFFLINE = "offline"
    AFTER_CALL_WORK = "after_call_work"


def _presence_key(organisation_id, agent_id) -> str:
    return f"presence:{organisation_id}:{agent_id}"


def _active_calls_key(organisation_id, agent_id) -> str:
    return f"presence:calls:{organisation_id}:{agent_id}"


@dataclass(frozen=True)
class PresenceRecord:
    status: PresenceStatus
    active_interactions: int


def set_presence(
    *,
    organisation_id,
    agent_id,
    status: PresenceStatus,
    ttl_seconds: int | None = None,
) -> None:
    """Record an agent's presence with an expiring lease."""

    ttl = ttl_seconds or settings.AGENT_PRESENCE_TTL_SECONDS
    key = _presence_key(organisation_id, agent_id)
    if status is PresenceStatus.OFFLINE:
        cache.delete(key)
        return
    cache.set(key, status.value, timeout=ttl)


def get_presence(*, organisation_id, agent_id) -> PresenceStatus:
    raw = cache.get(_presence_key(organisation_id, agent_id))
    if raw is None:
        return PresenceStatus.OFFLINE
    try:
        return PresenceStatus(raw)
    except ValueError:
        return PresenceStatus.OFFLINE


def touch_presence(
    *, organisation_id, agent_id, ttl_seconds: int | None = None
) -> None:
    """Refresh the lease without changing the current status (heartbeat)."""

    status = get_presence(organisation_id=organisation_id, agent_id=agent_id)
    if status is not PresenceStatus.OFFLINE:
        set_presence(
            organisation_id=organisation_id,
            agent_id=agent_id,
            status=status,
            ttl_seconds=ttl_seconds,
        )


def get_active_interactions(*, organisation_id, agent_id) -> int:
    return int(cache.get(_active_calls_key(organisation_id, agent_id)) or 0)


def increment_active_interactions(*, organisation_id, agent_id) -> int:
    key = _active_calls_key(organisation_id, agent_id)
    value = int(cache.get(key) or 0) + 1
    cache.set(key, value, timeout=settings.AGENT_PRESENCE_TTL_SECONDS * 60)
    return value


def decrement_active_interactions(*, organisation_id, agent_id) -> int:
    key = _active_calls_key(organisation_id, agent_id)
    value = max(int(cache.get(key) or 0) - 1, 0)
    cache.set(key, value, timeout=settings.AGENT_PRESENCE_TTL_SECONDS * 60)
    return value


def effective_status(
    *,
    requested: PresenceStatus,
    agent_enabled: bool,
) -> PresenceStatus:
    """Compute the status the server will actually advertise.

    An agent cannot become available if their administrative profile is
    disabled, regardless of what they request.
    """

    if not agent_enabled and requested is not PresenceStatus.OFFLINE:
        return PresenceStatus.OFFLINE
    return requested
