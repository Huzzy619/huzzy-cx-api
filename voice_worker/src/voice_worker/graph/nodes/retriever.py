"""RAG retriever tool and query nodes.

Retrieval is delegated to an injected async search callable so the worker never
holds a vector-store credential: the platform's knowledge API performs the
search. Configure it once at startup with :func:`set_knowledge_search`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.types import Command

from voice_worker.graph.providers import create_chat_model
from voice_worker.graph.state import RAGState

KnowledgeSearch = Callable[[str, str | None, str], Awaitable[list[dict[str, Any]]]]

_response_model = create_chat_model()
_search: KnowledgeSearch | None = None


def set_knowledge_search(search: KnowledgeSearch | None) -> None:
    """Register the platform knowledge-search function used by the retriever."""
    global _search
    _search = search


@tool
async def retrieve_knowledge_base_documents(
    query: str, config: RunnableConfig
) -> Command:
    """Search the business knowledge base and return matching documents.

    Use when the caller asks about documented business information: FAQs,
    policies, opening hours, contact information, or how-to guides.

    Args:
        query: A descriptive search phrase.

    Returns relevant knowledge base documents for this organisation.
    """
    configurable = config.get("configurable", {})
    organisation_id = str(configurable.get("organisation_id") or "")
    voice_session_id = configurable.get("voice_session_id")
    documents = (
        await _search(organisation_id, voice_session_id, query)
        if _search is not None
        else []
    )
    return Command(
        update={
            "retrieved_documents": [documents],
            "messages": [
                ToolMessage(
                    "Successfully retrieved knowledge base documents",
                    tool_call_id=config.get("tool_call_id", ""),
                )
            ],
        }
    )


def generate_query(state: RAGState) -> dict:
    response = _response_model.bind_tools([retrieve_knowledge_base_documents]).invoke(
        state["messages"],
        config={
            "configurable": {
                "organisation_id": state["organisation_id"],
                "voice_session_id": state.get("voice_session_id"),
            }
        },
    )
    return {"messages": [response]}


REWRITE_SYSTEM_PROMPT = """You are a query rewriter for a knowledge-base search.

The caller's question may be vague, misspelled, or ambiguous. Rewrite it into a
clear, specific question that will retrieve the most relevant documents.

Rules:
- Preserve the caller's original intent.
- Output only the improved question. No explanation, no preamble, no quotes.
"""


def rewrite_question(state: RAGState) -> dict:
    question = state["user_query"]
    response = _response_model.invoke(
        [
            {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]
    )
    return {"messages": [HumanMessage(content=response.content)]}


def return_relevant_docs(state: RAGState) -> dict:
    return {"rag_response": state["retrieved_documents"]}
