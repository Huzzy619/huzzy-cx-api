"""Supervisor node that delegates to the RAG graph."""

from __future__ import annotations

from typing import cast

from langchain_core.runnables import RunnableConfig

from voice_worker.graph.rag_graph import RAGAgentGraph
from voice_worker.graph.state import ParentGraphState, RAGState


async def call_rag_graph(state: ParentGraphState) -> dict:
    initial_state = cast(
        RAGState,
        {
            "messages": [
                {"role": "user", "content": state.get("current_user_message") or ""}
            ],
            "user_query": state.get("current_user_message") or "",
            "organisation_id": state["organisation_id"],
            "voice_session_id": state.get("voice_session_id"),
        },
    )
    config: RunnableConfig = {
        "configurable": {
            "thread_id": f"{state['chat_id']}_rag",
            "customer_id": state.get("customer_id"),
            "organisation_id": state["organisation_id"],
            "voice_session_id": state.get("voice_session_id"),
        }
    }
    response = await RAGAgentGraph().process_query(initial_state, config)
    return {"rag_response": response}
