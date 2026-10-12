"""Intent classification node for the supervisor graph."""

from __future__ import annotations

from voice_worker.graph.providers import create_chat_model
from voice_worker.graph.state import (
    MessageIntent,
    ParentGraphState,
    SituationClassification,
)

_llm = create_chat_model()

INTENT_OPTIONS = ", ".join(sorted(intent.value for intent in MessageIntent))

CLASSIFICATION_PROMPT = f"""
Analyze the conversation and the latest user message to determine the intent.

Intent options: {INTENT_OPTIONS}

Guidelines:
- Use general_chat only when the user is clearly not discussing business
  information.
- Use knowledge_base_inquiry when the user asks about information that could be
  in the business knowledge base: FAQs, policies, how-to guides, opening hours,
  contact info, or other documented business information.

Output the intent.
"""


def classify_intent(state: ParentGraphState) -> dict:
    messages = state.get("messages") or []
    current_user_message = messages[-1].content if messages else ""

    classification = _llm.with_structured_output(SituationClassification).invoke(
        [{"role": "system", "content": CLASSIFICATION_PROMPT}] + messages
    )

    return {
        "classification": classification,
        "intent": getattr(classification, "intent", None),
        "current_user_message": current_user_message,
    }
