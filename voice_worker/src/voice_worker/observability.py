"""Session metrics / observability handlers for the voice agent.

Latency and usage are logged locally; a compact usage summary is also recorded
against the platform session so billing/reporting stays server-side.
"""

from __future__ import annotations

import logging
from typing import Any

from livekit.agents import (
    AgentSession,
    ConversationItemAddedEvent,
    JobContext,
    SessionUsageUpdatedEvent,
)
from livekit.agents.llm import ChatMessage

from voice_worker.session_flags import get_session_flags

logger = logging.getLogger(__name__)


def _log_usage_summary(usage: Any, *, label: str) -> None:
    model_usage = getattr(usage, "model_usage", None) or []
    if not model_usage:
        logger.info("%s - no model usage recorded", label)
        return
    for entry in model_usage:
        logger.info(
            "%s - %s/%s: %s",
            label,
            getattr(entry, "provider", "?"),
            getattr(entry, "model", "?"),
            entry,
        )


def attach_session_observability(session: AgentSession, ctx: JobContext) -> None:
    """Subscribe to metrics events (register before ``session.start``)."""
    logged_final = {"done": False}

    @session.on("conversation_item_added")
    def _on_conversation_item_added(ev: ConversationItemAddedEvent) -> None:
        if not isinstance(ev.item, ChatMessage) or ev.item.role != "assistant":
            return
        metrics = ev.item.metrics
        e2e = metrics.get("e2e_latency")
        if e2e is not None:
            logger.info("End-to-end latency: %.3fs", e2e)
        ttft = metrics.get("llm_node_ttft")
        ttfb = metrics.get("tts_node_ttfb")
        if ttft is not None or ttfb is not None:
            logger.info(
                "Pipeline latency - LLM TTFT: %s, TTS TTFB: %s",
                f"{ttft:.3f}s" if ttft is not None else "n/a",
                f"{ttfb:.3f}s" if ttfb is not None else "n/a",
            )

    @session.on("session_usage_updated")
    def _on_session_usage_updated(ev: SessionUsageUpdatedEvent) -> None:
        for usage in ev.usage.model_usage:
            logger.debug(
                "Usage update - %s/%s: %s", usage.provider, usage.model, usage
            )

    def _log_final_usage() -> None:
        if logged_final["done"]:
            return
        logged_final["done"] = True
        usage = getattr(session, "usage", None)
        if usage is None:
            logger.debug("session.usage unavailable at close")
            return
        _log_usage_summary(usage, label="Final session usage")
        _record_usage(ctx, usage)

    @session.on("close")
    def _on_close(_ev: Any) -> None:
        _log_final_usage()

    async def _on_shutdown(_reason: str = "") -> None:
        _log_final_usage()

    ctx.add_shutdown_callback(_on_shutdown)


def _record_usage(ctx: JobContext, usage: Any) -> None:
    flags = get_session_flags(ctx)
    voice_session_id = flags.get("voice_session_id")
    if not voice_session_id:
        return
    # The runtime stores the shared client on job userdata under "kora_client".
    client = ctx.proc.userdata.get("kora_client")
    if client is None:
        return
    model_usage = [
        {
            "provider": getattr(entry, "provider", None),
            "model": getattr(entry, "model", None),
        }
        for entry in (getattr(usage, "model_usage", None) or [])
    ]
    try:
        # Fire-and-forget: usage recording must never break session teardown.
        import asyncio

        asyncio.create_task(
            client.record_event(
                voice_session_id=voice_session_id,
                event_type="voice_session.usage",
                source_event_id=f"usage:{voice_session_id}",
                payload={"model_usage": model_usage},
            )
        )
    except Exception:
        logger.exception("Failed to schedule usage event for %s", voice_session_id)
