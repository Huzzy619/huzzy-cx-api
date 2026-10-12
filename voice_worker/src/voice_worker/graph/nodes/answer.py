"""Final answer node and intent router for the supervisor graph."""

from __future__ import annotations

from voice_worker.graph.nodes.summarize import messages_safe_for_llm
from voice_worker.graph.providers import create_chat_model
from voice_worker.graph.stage_prompt import SUPERVISOR_PROMPT
from voice_worker.graph.state import MessageIntent, ParentGraphState

_NO_CONTEXT = (
    "No existing context required, just proceed with the conversation naturally."
)


def _build_history(state: ParentGraphState) -> list:
    summarized = state.get("summarized_messages") or []
    if summarized:
        return messages_safe_for_llm(summarized)
    return messages_safe_for_llm(state["messages"])


async def generate_final_answer(state: ParentGraphState) -> dict:
    agent_config = state.get("agent_config") or {}
    current_user_message = state.get("current_user_message") or ""

    intent_value = state.get("intent")
    if hasattr(intent_value, "value"):
        intent_key = intent_value.value
    else:
        intent_key = str(intent_value or "")

    if intent_key == MessageIntent.KNOWLEDGE_BASE_INQUIRY.value:
        rag_response = state.get("rag_response") or {}
        context = (
            rag_response.get("retrieved_documents", [])
            if isinstance(rag_response, dict)
            else []
        )
    else:
        context = _NO_CONTEXT

    base_prompt = SUPERVISOR_PROMPT.format(
        question=current_user_message,
        context=context,
        intent=intent_key,
        additional_instructions=agent_config.get("system_prompt", ""),
    )

    response_model = create_chat_model(
        model_name=agent_config.get("model"),
    )
    response = await response_model.ainvoke(
        [{"role": "system", "content": base_prompt}] + _build_history(state)
    )
    return {"messages": [response]}


def route_after_stage_prompt(state: ParentGraphState) -> str:
    intent = state.get("intent")
    intent_value = intent.value if hasattr(intent, "value") else intent
    if isinstance(intent_value, str) and intent_value:
        return intent_value
    return MessageIntent.GENERAL_CHAT.value
