"""API schemas for interactions.

Schemas are kept separate from ORM models so internal fields cannot leak into
public API contracts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from ninja import Schema
from pydantic import Field


class QueueSummary(Schema):
    id: UUID
    name: str


class CustomerSummary(Schema):
    id: UUID
    display_name: str


class InteractionCapabilities(Schema):
    hold: bool = False
    transfer: bool = False
    recording_available: bool = False


class InteractionRead(Schema):
    id: UUID
    channel: Literal["voice"]
    direction: str
    status: str
    queue: QueueSummary | None = None
    customer: CustomerSummary | None = None
    started_at: datetime | None = None
    answered_at: datetime | None = None
    ended_at: datetime | None = None
    disposition_code: str = ""
    ai_enrichment_status: str
    capabilities: InteractionCapabilities = InteractionCapabilities()


class DispositionInput(Schema):
    code: str = Field(min_length=1, max_length=80)
    notes: str = Field(default="", max_length=4000)


class TransferInput(Schema):
    queue_id: UUID


class ErrorResponse(Schema):
    code: str
    message: str
