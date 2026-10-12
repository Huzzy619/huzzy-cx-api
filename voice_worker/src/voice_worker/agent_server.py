"""LiveKit Agents worker entrypoint for Kora CX voice sessions."""

from __future__ import annotations

import json
import logging

from livekit.agents import AgentServer, JobContext, cli

from voice_worker.config import get_settings
from voice_worker.runtime import run_voice_job
from voice_worker.session_end import on_session_end

logger = logging.getLogger(__name__)

server = AgentServer()


@server.rtc_session(
    agent_name=get_settings().voice_agent_name,
    on_session_end=on_session_end,
)
async def entrypoint(ctx: JobContext) -> None:
    try:
        metadata = json.loads(ctx.job.metadata or "{}")
    except json.JSONDecodeError:
        metadata = {}
    await run_voice_job(ctx, metadata)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    cli.run_app(server)


if __name__ == "__main__":
    main()
