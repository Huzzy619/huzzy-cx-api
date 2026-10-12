"""LangGraph state schemas for the supervisor and RAG graphs."""

from __future__ import annotations

from enum import Enum, StrEnum
from operator import add
from typing import Annotated, Any, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph import MessagesState
from pydantic import BaseModel, Field


class MessageIntent(Enum):
    KNOWLEDGE_BASE_INQUIRY = "knowledge_base_inquiry"
    GENERAL_CHAT = "general_chat"


class ParentGraphState(TypedDict):
    messages: list[AnyMessage]
    customer_id: str
    chat_id: str
    organisation_id: str
    voice_session_id: NotRequired[str]
    current_user_message: NotRequired[str | None]

    intent: NotRequired[MessageIntent | str | None]
    rag_response: NotRequired[dict | None]
    context: NotRequired[dict[str, Any]]
    agent_config: NotRequired[dict | None]
    summarized_messages: NotRequired[list[AnyMessage]]


class SituationClassification(TypedDict):
    """Output of the situation-analysis call."""

    intent: MessageIntent


class ParentGraphNodes(StrEnum):
    RAG_AGENT = "rag_agent"
    CLASSIFY_INTENT = "classify_intent"
    GENERATE_FINAL_ANSWER = "generate_final_answer"
    SUMMARIZE = "summarize"


class RAGState(MessagesState):
    organisation_id: str
    voice_session_id: str | None
    user_query: str | None
    retrieved_documents: Annotated[list, add]


class GradeDocuments(BaseModel):
    """Grade documents using a binary score for relevance check."""

    binary_score: str = Field(
        description="Relevance score: 'yes' if relevant, or 'no' if not relevant"
    )
