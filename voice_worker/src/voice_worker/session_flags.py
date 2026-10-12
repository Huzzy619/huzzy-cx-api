"""Typed session flags stored on ``JobContext.proc.userdata``.

These are mutable per-job values shared between the tools, runtime and the
session-end callback. They survive because ``JobProcess.userdata`` returns the
underlying dict, which is mutated in place.
"""

from __future__ import annotations

from typing import Any, TypedDict

from livekit.agents import JobContext

_SESSION_FLAGS_KEY = "kora_session_flags"


class SessionFlags(TypedDict, total=False):
    organisation_id: str | None
    voice_session_id: str | None
    interaction_id: str | None
    agent_config: dict[str, Any]
    transferred: bool
    final_status: str
    hangup_cause: str
    disconnect_reason: str
    amd_result: str


SessionFlagsDict = SessionFlags


def get_session_flags(ctx: JobContext) -> SessionFlags:
    userdata = ctx.proc.userdata
    flags = userdata.setdefault(_SESSION_FLAGS_KEY, {})
    if not isinstance(flags, dict):
        flags = {}
        userdata[_SESSION_FLAGS_KEY] = flags
    return flags  # type: ignore[return-value]


def session_flags_as_dict(flags: SessionFlags) -> dict[str, Any]:
    return dict(flags)
