"""Provider-neutral adapters for voicebot business data.

The model must never infer business facts. These providers are the only way a
tool obtains authoritative transaction or knowledge data, and the default
implementations deliberately return an explicit ``unknown``/empty result until
a customer integration is configured.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from django.conf import settings

TransactionState = Literal[
    "pending", "successful", "failed", "reversed", "unknown"
]


@dataclass(frozen=True)
class TransactionStatus:
    reference: str
    status: TransactionState
    customer_message: str
    amount_display: str | None = None
    currency: str | None = None


@dataclass(frozen=True)
class KnowledgeMatch:
    document_id: str
    title: str
    snippet: str


class TransactionStatusProvider(Protocol):
    def get_status(
        self, *, organisation, customer, reference: str
    ) -> TransactionStatus: ...


class KnowledgeProvider(Protocol):
    def search(
        self, *, organisation, query: str, limit: int = 3
    ) -> list[KnowledgeMatch]: ...


class UnavailableTransactionProvider:
    """Default provider used until a fintech integration is configured."""

    def get_status(
        self, *, organisation, customer, reference: str
    ) -> TransactionStatus:
        return TransactionStatus(
            reference=reference,
            status="unknown",
            customer_message=(
                "I couldn't retrieve that transaction right now. "
                "I can pass you to a colleague who can check it."
            ),
        )


class EmptyKnowledgeProvider:
    """Default provider returning no approved content."""

    def search(
        self, *, organisation, query: str, limit: int = 3
    ) -> list[KnowledgeMatch]:
        return []


def get_transaction_provider() -> TransactionStatusProvider:
    provider = settings.AI_PROVIDER  # replaced by the configured integration
    if provider == "stub":
        return UnavailableTransactionProvider()
    return UnavailableTransactionProvider()


def get_knowledge_provider() -> KnowledgeProvider:
    return EmptyKnowledgeProvider()
