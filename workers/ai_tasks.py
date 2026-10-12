"""AI enrichment tasks.

Milestone 1 only defines the task boundary. The actual provider-neutral AI
interface, transcription and summary pipeline arrive in a later milestone.
"""

from __future__ import annotations

from celery import shared_task


@shared_task(
    autoretry_for=(TimeoutError, ConnectionError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def generate_interaction_summary(interaction_id: str) -> None:
    # Intentionally a no-op until the AI assistance milestone. It must never
    # block interaction completion: callers fire-and-forget through the outbox.
    return None
