"""End-of-session callback: close the platform session and record a report."""

from __future__ import annotations

import logging
from typing import Any

from livekit.agents import JobContext

from voice_worker.session_flags import (
    SessionFlags,
    get_session_flags,
    session_flags_as_dict,
)

logger = logging.getLogger(__name__)

__all__ = ["SessionFlags", "get_session_flags", "merge_job_metadata", "on_session_end"]


def merge_job_metadata(ctx: JobContext) -> dict[str, Any]:
    import json

    try:
        metadata = json.loads(ctx.job.metadata or "{}")
    except json.JSONDecodeError:
        metadata = {}
    metadata.update(session_flags_as_dict(get_session_flags(ctx)))
    return metadata


async def on_session_end(ctx: JobContext) -> None:
    flags = get_session_flags(ctx)
    client = ctx.proc.userdata.get("kora_client")
    voice_session_id = flags.get("voice_session_id")
    if client is None or not voice_session_id:
        logger.warning("Session end without a client/session id; nothing to finalise")
        return

    reason = flags.get("hangup_cause") or flags.get("disconnect_reason") or "completed"

    report: dict[str, Any] | None = None
    try:
        report = ctx.make_session_report().to_dict()
    except Exception:
        logger.exception("make_session_report failed for room %s", ctx.room.name)

    try:
        await client.record_event(
            voice_session_id=voice_session_id,
            event_type="voice_session.report",
            source_event_id=f"report:{voice_session_id}",
            payload=report or {},
        )
    except Exception:
        logger.exception("Failed to record session report for %s", voice_session_id)

    try:
        await client.end_session(voice_session_id=voice_session_id, reason=str(reason))
    except Exception:
        logger.exception("Failed to end platform session %s", voice_session_id)
