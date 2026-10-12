"""Supervisor graph: intent classification, RAG delegation, and answer."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from voice_worker.graph.nodes.answer import (
    generate_final_answer,
    route_after_stage_prompt,
)
from voice_worker.graph.nodes.classify_intent import classify_intent
from voice_worker.graph.nodes.rag import call_rag_graph
from voice_worker.graph.nodes.summarize import summarization_node
from voice_worker.graph.state import (
    MessageIntent,
    ParentGraphNodes,
    ParentGraphState,
)


class SupervisorAgentGraph:
    def _build_supervisor_graph(self):
        graph = StateGraph(ParentGraphState)
        graph.add_node(ParentGraphNodes.SUMMARIZE.value, summarization_node)
        graph.add_node(ParentGraphNodes.RAG_AGENT.value, call_rag_graph)
        graph.add_node(ParentGraphNodes.CLASSIFY_INTENT.value, classify_intent)
        graph.add_node(
            ParentGraphNodes.GENERATE_FINAL_ANSWER.value, generate_final_answer
        )

        graph.add_edge(START, ParentGraphNodes.CLASSIFY_INTENT.value)
        graph.add_edge(START, ParentGraphNodes.SUMMARIZE.value)
        graph.add_conditional_edges(
            ParentGraphNodes.CLASSIFY_INTENT.value,
            route_after_stage_prompt,
            {
                MessageIntent.KNOWLEDGE_BASE_INQUIRY.value: (
                    ParentGraphNodes.RAG_AGENT.value
                ),
                MessageIntent.GENERAL_CHAT.value: (
                    ParentGraphNodes.GENERATE_FINAL_ANSWER.value
                ),
            },
        )
        graph.add_edge(
            ParentGraphNodes.RAG_AGENT.value,
            ParentGraphNodes.GENERATE_FINAL_ANSWER.value,
        )
        graph.add_edge(ParentGraphNodes.GENERATE_FINAL_ANSWER.value, END)
        return graph

    async def process_conversation(
        self,
        *,
        user_message: str,
        chat_id: str,
        customer_id: str,
        organisation_id: str,
        voice_session_id: str | None = None,
        agent_config: dict | None = None,
    ) -> str:
        graph = self._build_supervisor_graph().compile(
            checkpointer=InMemorySaver(),
            store=InMemorySaver(),  # type: ignore[arg-type]
        )
        config: RunnableConfig = {
            "configurable": {"thread_id": chat_id, "customer_id": customer_id}
        }
        initial_state = {
            "customer_id": customer_id,
            "chat_id": chat_id,
            "organisation_id": organisation_id,
            "voice_session_id": voice_session_id,
            "current_user_message": user_message,
            "messages": [{"role": "user", "content": user_message}],
            "agent_config": agent_config or {},
        }
        result = await graph.ainvoke(initial_state, config)
        return result["messages"][-1].content
