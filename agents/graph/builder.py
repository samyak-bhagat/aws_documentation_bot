"""
LangGraph research agent — Phase 2.

Graph topology:
  START
    → query_analyzer
    → doc_searcher
    → doc_reader
    → context_builder
    → context_evaluator
        ├─[sufficient]─────────────────────→ answer_generator
        ├─[insufficient, retry < 2]────────→ broaden_search → doc_searcher
        └─[insufficient, retry >= 2]───────→ answer_generator  (fallback)
    → citation_formatter
    → END

CLI usage:
    python -m agents.graph.builder "How do I secure an S3 bucket?"
"""

from __future__ import annotations

import asyncio
import sys
import uuid

from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from agents.graph.state import AgentState
from agents.nodes.answer_generator import make_answer_generator
from agents.nodes.citation_formatter import citation_formatter_node
from agents.nodes.context_builder import context_builder_node
from agents.nodes.context_evaluator import context_evaluator_node
from agents.nodes.doc_reader import make_doc_reader
from agents.nodes.doc_searcher import make_doc_searcher
from agents.nodes.query_analyzer import make_query_analyzer
from core.config import settings
from core.logging import get_logger
from services.mcp.client import get_mcp_client
from services.mcp.tools import AWSDocsMCPTools

logger = get_logger(__name__)

_MAX_RETRIES = 2


def _broaden_query(query: str, retry_count: int) -> str:
    """Expand a query when initial results are insufficient."""
    suffixes = ["overview guide", "best practices documentation", "AWS official guide"]
    suffix = suffixes[min(retry_count, len(suffixes) - 1)]
    return f"{query} {suffix}"


def _make_broaden_search_node():
    def node(state: AgentState) -> dict:
        current_query = state.get("optimized_query", state["user_query"])
        retry = state.get("retry_count", 0)
        new_query = _broaden_query(current_query, retry)
        logger.info(
            "Broadening search",
            extra={"old_query": current_query, "new_query": new_query, "retry": retry + 1},
        )
        return {
            "optimized_query": new_query,
            "retry_count": retry + 1,
            "search_results": [],
            "documents": [],
            "context": "",
        }

    return node


def _route_after_evaluation(state: AgentState) -> str:
    """Conditional edge: decide what happens after context evaluation."""
    if state.get("context_sufficient", False):
        return "answer_generator"
    retry = state.get("retry_count", 0)
    if retry < _MAX_RETRIES:
        return "broaden_search"
    return "answer_generator"  # fallback — answer with whatever context we have


def build_graph(mcp_tools: AWSDocsMCPTools) -> StateGraph:
    """Construct and compile the LangGraph research agent."""
    llm = ChatOpenAI(
        model=settings.openai_model,
        temperature=0,
        api_key=settings.openai_api_key,
    )

    graph = StateGraph(AgentState)

    # ── Nodes ─────────────────────────────────────────────────────────
    graph.add_node("query_analyzer", make_query_analyzer(llm))
    graph.add_node("doc_searcher", make_doc_searcher(mcp_tools))
    graph.add_node("doc_reader", make_doc_reader(mcp_tools))
    graph.add_node("context_builder", context_builder_node)
    graph.add_node("context_evaluator", context_evaluator_node)
    graph.add_node("broaden_search", _make_broaden_search_node())
    graph.add_node("answer_generator", make_answer_generator(llm))
    graph.add_node("citation_formatter", citation_formatter_node)

    # ── Edges ─────────────────────────────────────────────────────────
    graph.add_edge(START, "query_analyzer")
    graph.add_edge("query_analyzer", "doc_searcher")
    graph.add_edge("doc_searcher", "doc_reader")
    graph.add_edge("doc_reader", "context_builder")
    graph.add_edge("context_builder", "context_evaluator")

    graph.add_conditional_edges(
        "context_evaluator",
        _route_after_evaluation,
        {
            "answer_generator": "answer_generator",
            "broaden_search": "broaden_search",
        },
    )

    graph.add_edge("broaden_search", "doc_searcher")
    graph.add_edge("answer_generator", "citation_formatter")
    graph.add_edge("citation_formatter", END)

    return graph.compile()


# ── CLI entry point ────────────────────────────────────────────────────────────


async def _run(user_query: str) -> None:
    async with get_mcp_client() as client:
        mcp_tools = AWSDocsMCPTools(client)
        compiled = build_graph(mcp_tools)

        initial_state: AgentState = {
            "user_query": user_query,
            "session_id": str(uuid.uuid4()),
        }

        logger.info("Agent starting", extra={"query": user_query})
        result = await compiled.ainvoke(initial_state)

    print("\n" + "=" * 60)
    print("Answer:")
    print("=" * 60)
    print(result.get("answer", "No answer generated."))
    print("\nSources:")
    for citation in result.get("citations", []):
        print(f"  - {citation['title']}")
        print(f"    {citation['url']}")
    print("=" * 60)


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "How do I secure an S3 bucket?"
    asyncio.run(_run(query))
