"""Thin HTTP client for the Kora CX internal voice API.

The worker owns no business logic: it asks the platform to initialise
sessions, execute tools and record events. Every tool the model can call maps
to exactly one method here. The client is async so it never blocks the LiveKit
event loop.
"""

from __future__ import annotations

from typing import Any

import httpx

from voice_worker.config import WorkerSettings


class KoraApiError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"Kora API error {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


class KoraClient:
    def __init__(
        self, settings: WorkerSettings, *, client: httpx.AsyncClient | None = None
    ) -> None:
        self._settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=settings.kora_api_base_url,
            headers={"Authorization": f"Bearer {settings.voice_worker_token}"},
            timeout=settings.tool_timeout_seconds,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> KoraClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.post(path, json=payload)
        if response.status_code >= 400:
            raise KoraApiError(response.status_code, response.text)
        return response.json()

    async def initialize_session(
        self,
        *,
        provider_connection_id: str,
        provider_call_id: str,
        room_name: str,
        language: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "provider_connection_id": provider_connection_id,
            "provider_call_id": provider_call_id,
            "room_name": room_name,
        }
        if language:
            payload["language"] = language
        return await self._post("/internal/voice/sessions/initialize", payload)

    async def search_knowledge(
        self,
        *,
        voice_session_id: str,
        query: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return await self._post(
            "/internal/voice/tools/knowledge",
            {
                "voice_session_id": voice_session_id,
                "query": query,
                "idempotency_key": idempotency_key,
            },
        )

    async def transaction_status(
        self,
        *,
        voice_session_id: str,
        transaction_reference: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return await self._post(
            "/internal/voice/tools/transaction-status",
            {
                "voice_session_id": voice_session_id,
                "transaction_reference": transaction_reference,
                "idempotency_key": idempotency_key,
            },
        )

    async def support_case(
        self,
        *,
        voice_session_id: str,
        idempotency_key: str,
        reference: str | None = None,
        subject: str | None = None,
    ) -> dict[str, Any]:
        return await self._post(
            "/internal/voice/tools/support-cases",
            {
                "voice_session_id": voice_session_id,
                "idempotency_key": idempotency_key,
                "reference": reference,
                "subject": subject,
            },
        )

    async def request_handoff(
        self,
        *,
        voice_session_id: str,
        queue_id: str | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        return await self._post(
            "/internal/voice/handoffs",
            {
                "voice_session_id": voice_session_id,
                "queue_id": queue_id,
                "reason": reason,
            },
        )

    async def record_event(
        self,
        *,
        voice_session_id: str,
        event_type: str,
        source_event_id: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._post(
            f"/internal/voice/sessions/{voice_session_id}/events",
            {
                "event_type": event_type,
                "source_event_id": source_event_id,
                "payload": payload or {},
            },
        )

    async def end_session(
        self,
        *,
        voice_session_id: str,
        reason: str = "",
    ) -> dict[str, Any]:
        return await self._post(
            f"/internal/voice/sessions/{voice_session_id}/end",
            {"reason": reason},
        )
