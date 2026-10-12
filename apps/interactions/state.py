"""Canonical interaction state machine.

Vendor statuses differ, so provider events are mapped onto this internal state
machine. The map below is deliberately explicit: every permitted transition is
listed and anything else is rejected.
"""

from __future__ import annotations

from apps.common.exceptions import InvalidTransitionError
from apps.interactions.models import Interaction

S = Interaction.Status

# Terminal states must never be resurrected by a late event.
TERMINAL_STATES = frozenset({S.COMPLETED, S.FAILED})

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    S.CREATED: frozenset({S.QUEUED, S.ROUTING, S.RINGING, S.ACTIVE, S.ENDED, S.FAILED}),
    S.QUEUED: frozenset({S.ROUTING, S.RINGING, S.ACTIVE, S.QUEUED, S.ENDED, S.FAILED}),
    S.ROUTING: frozenset({S.RINGING, S.QUEUED, S.ACTIVE, S.ENDED, S.FAILED}),
    S.RINGING: frozenset({S.ACTIVE, S.QUEUED, S.ROUTING, S.ENDED, S.FAILED}),
    S.ACTIVE: frozenset({S.ON_HOLD, S.TRANSFERRING, S.ENDED, S.FAILED}),
    S.ON_HOLD: frozenset({S.ACTIVE, S.ENDED, S.FAILED}),
    S.TRANSFERRING: frozenset({S.ACTIVE, S.QUEUED, S.ENDED, S.FAILED}),
    S.ENDED: frozenset({S.PROCESSING, S.COMPLETED, S.FAILED}),
    S.PROCESSING: frozenset({S.COMPLETED, S.FAILED}),
    S.COMPLETED: frozenset(),
    S.FAILED: frozenset(),
}


def is_transition_allowed(current: str, target: str) -> bool:
    if current == target:
        # Re-asserting the current status is an idempotent no-op.
        return True
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


def validate_transition(*, current_status: str, target_status: str) -> None:
    if not is_transition_allowed(current_status, target_status):
        raise InvalidTransitionError(
            f"Cannot move interaction from {current_status!r} to {target_status!r}.",
            current_status=current_status,
            target_status=target_status,
        )
