"""Knowledge-base search tool backed by the Kora CX platform.

Retrieval and content approval live server-side, so the worker never holds a
vector-store credential. If the query takes too long the tool speaks a brief
status update (replicated from the reference voice stack).
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from livekit.agents import RunContext, function_tool

from voice_worker.builders.context import VoiceAgentContext


def _idempotency_key(prefix: str) -> str:
    return f"{prefix}:{uuid.uuid4().hex}"


def context_from(run_context: RunContext) -> VoiceAgentContext | None:
    userdata = getattr(run_context.session, "userdata", None)
    if isinstance(userdata, VoiceAgentContext):
        return userdata
    return None


async def search_knowledge_tool(run_context: RunContext, query: str) -> dict[str, Any]:
    """Search Kora CX's approved knowledge base for the answer.

    Use this for product, policy, or troubleshooting questions. Answers are
    limited to approved content; never invent information beyond the result.
    """
    ctx = context_from(run_context)
    if ctx is None:
        return {"matches": [], "error": "session_unavailable"}
    return await ctx.client.search_knowledge(
        voice_session_id=ctx.voice_session_id,
        query=query,
        idempotency_key=_idempotency_key("knowledge"),
    )


async def _search_with_status_update(
    run_context: RunContext, ctx: VoiceAgentContext, query: str
) -> dict[str, Any]:
    async def _speak_status_update(delay: float = 1.0) -> None:
        await asyncio.sleep(delay)
        await run_context.session.generate_reply(
            instructions=(
                f'You are searching the knowledge base for "{query}" but it is '
                "taking a little while. Briefly update the caller on your progress."
            )
        )

    task = asyncio.create_task(_speak_status_update())
    try:
        return await search_knowledge_tool(run_context, query)
    finally:
        task.cancel()


def build_knowledge_tool() -> Any:
    @function_tool(name="search_approved_knowledge")
    async def knowledge_search(run_context: RunContext, query: str) -> dict[str, Any]:
        """Search Kora CX's approved knowledge base for product, policy, or
        troubleshooting questions. Prefer this over guessing.

        Args:
            query: A descriptive search phrase.
        """
        ctx = context_from(run_context)
        if ctx is None:
            return {"matches": [], "error": "session_unavailable"}
        return await _search_with_status_update(run_context, ctx, query)

    return knowledge_search
