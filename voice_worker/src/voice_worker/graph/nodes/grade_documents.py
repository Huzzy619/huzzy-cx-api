"""Document relevance grading node."""

from __future__ import annotations

from typing import Literal

from voice_worker.graph.providers import create_chat_model
from voice_worker.graph.state import GradeDocuments, RAGState

GRADE_SYSTEM_PROMPT = """You are a relevance grader. Assess whether a retrieved
document is relevant to a caller's question.

Grade as "yes" if the document contains information, by keyword or meaning, that
would help answer the question. Grade as "no" if the document is about a
different topic, or is empty.

Return only the binary score: "yes" or "no"."""

_grader_model = create_chat_model()


def grade_documents(
    state: RAGState,
) -> Literal["return_relevant_docs", "rewrite_question"]:
    question = state["user_query"]
    context = state["retrieved_documents"]

    response: GradeDocuments = _grader_model.with_structured_output(  # type: ignore[assignment]
        GradeDocuments
    ).invoke(
        [
            {"role": "system", "content": GRADE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Question: {question}\n\nDocument: {context}",
            },
        ]
    )
    if response.binary_score == "yes":
        return "return_relevant_docs"
    return "rewrite_question"
