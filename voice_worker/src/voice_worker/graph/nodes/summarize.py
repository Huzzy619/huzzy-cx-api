"""Conversation summarization node and message sanitization helper."""

from __future__ import annotations

from langchain_core.messages import AnyMessage
from langmem.short_term import SummarizationNode

from voice_worker.graph.providers import create_chat_model

_model = create_chat_model()
summarization_model = _model.bind(max_tokens=1024)

summarization_node = SummarizationNode(
    model=summarization_model,
    max_tokens_before_summary=4000,
    max_tokens=4000,
    max_summary_tokens=1024,
)


def messages_safe_for_llm(messages: list[AnyMessage]) -> list[AnyMessage]:
    """Strip AI messages that contain tool_calls with no paired ToolMessages.

    Passing such messages to the LLM causes a 400 error because OpenAI requires
    every ``tool_call_id`` to be answered by a ToolMessage.
    """
    out: list[AnyMessage] = []
    for message in messages:
        if getattr(message, "tool_calls", None):
            continue
        out.append(message)
    return out
