"""Top-level Django Ninja API.

Routers are versioned under ``/api/v1/`` by ``config.urls``. Each domain app
exposes its own router so the API surface stays close to the domain it serves.
"""

from ninja import NinjaAPI

from apps.interactions.api import router as interactions_router
from apps.telephony.api import router as telephony_router
from apps.voice_agents.api import internal_router as voice_internal_router
from apps.voice_agents.api import router as voice_agents_router

api = NinjaAPI(
    title="Kora CX API",
    version="1.0.0",
    description="Contact-centre control plane for Kora CX.",
)

api.add_router("/interactions/", interactions_router, tags=["interactions"])
api.add_router("/voice-agents/", voice_agents_router, tags=["voice-agents"])
api.add_router(
    "/internal/voice/", voice_internal_router, tags=["voice-internal"]
)
api.add_router("/webhooks/telephony/", telephony_router, tags=["telephony-webhooks"])
