"""RAG graph: query generation, retrieval, grading, and answer/rewrite loop."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from voice_worker.graph.nodes.grade_documents import grade_documents
from voice_worker.graph.nodes.retriever import (
    generate_query,
    retrieve_knowledge_base_documents,
    return_relevant_docs,
    rewrite_question,
)
from voice_worker.graph.state import RAGState


class RAGAgentGraph:
    def _build_rag_graph(self):
        graph = StateGraph(RAGState)
        graph.add_node("generate_query", generate_query)
        graph.add_node(
            "retrieve", ToolNode([retrieve_knowledge_base_documents])
        )
        graph.add_node("rewrite_question", rewrite_question)
        graph.add_node("return_relevant_docs", return_relevant_docs)

        graph.add_edge(START, "generate_query")
        graph.add_conditional_edges(
            "generate_query",
            tools_condition,
            {"tools": "retrieve", END: END},
        )
        graph.add_conditional_edges("retrieve", grade_documents)
        graph.add_edge("return_relevant_docs", END)
        graph.add_edge("rewrite_question", "generate_query")
        return graph

    async def process_query(self, initial_state: RAGState, config: RunnableConfig):
        graph = self._build_rag_graph().compile(
            checkpointer=InMemorySaver(),
            store=InMemorySaver(),  # type: ignore[arg-type]
        )
        return await graph.ainvoke(initial_state, config)
