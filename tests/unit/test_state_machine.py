"""Unit tests for the canonical interaction state machine."""

from __future__ import annotations

import pytest

from apps.common.exceptions import InvalidTransitionError
from apps.interactions.models import Interaction
from apps.interactions.state import (
    TERMINAL_STATES,
    is_transition_allowed,
    validate_transition,
)

S = Interaction.Status


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.CREATED, S.QUEUED),
        (S.QUEUED, S.RINGING),
        (S.RINGING, S.ACTIVE),
        (S.ACTIVE, S.ON_HOLD),
        (S.ON_HOLD, S.ACTIVE),
        (S.ACTIVE, S.TRANSFERRING),
        (S.ACTIVE, S.ENDED),
        (S.ENDED, S.PROCESSING),
        (S.PROCESSING, S.COMPLETED),
    ],
)
def test_allowed_transitions(current, target):
    assert is_transition_allowed(current, target)
    validate_transition(current_status=current, target_status=target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.COMPLETED, S.ACTIVE),
        (S.FAILED, S.ENDED),
        (S.ENDED, S.ACTIVE),
        (S.ACTIVE, S.RINGING),
    ],
)
def test_invalid_transitions_raise(current, target):
    assert not is_transition_allowed(current, target)
    with pytest.raises(InvalidTransitionError):
        validate_transition(current_status=current, target_status=target)


def test_terminal_states_have_no_outgoing_transitions():
    assert TERMINAL_STATES == {S.COMPLETED, S.FAILED}
    for state in TERMINAL_STATES:
        assert is_transition_allowed(state, S.ACTIVE) is False
        assert is_transition_allowed(state, S.ENDED) is False


def test_same_status_is_idempotent():
    assert is_transition_allowed(S.ACTIVE, S.ACTIVE)
