"""Integration tasks (external CRM/ticketing/transaction APIs).

Boundary only for Milestone 1. Side-effecting integrations require idempotency
keys and explicit handling of ambiguous outcomes.
"""

from __future__ import annotations

from celery import shared_task


@shared_task(
    autoretry_for=(TimeoutError, ConnectionError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=4,
)
def execute_integration_action(
    *, tool_name: str, idempotency_key: str, payload: dict
) -> None:
    return None
