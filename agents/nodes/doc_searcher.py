"""Node: search AWS documentation.

Strategy (Phase 7+):
  1. If Qdrant has indexed docs for this service → hybrid search (vector + BM25 + RRF)
  2. Otherwise → fall back to MCP keyword search and update cache/index
"""

from agents.graph.state import AgentState
from core.logging import get_logger
from services.mcp.tools import AWSDocsMCPTools

logger = get_logger(__name__)

_SEARCH_LIMIT = 5


def make_doc_searcher(mcp_tools: AWSDocsMCPTools):
    """Return a LangGraph node function with MCP tools injected."""

    async def node(state: AgentState) -> dict:
        query = state["optimized_query"]
        logger.info("Searching docs", extra={"query": query})

        # ── Try hybrid search if Qdrant has any indexed docs ─────────────
        # Check without service filter — semantic search handles relevance.
        # Service name is passed as a soft hint, not a hard filter.
        try:
            from services.vector.retriever import hybrid_search
            from services.vector.store import collection_has_docs

            has_docs = await collection_has_docs()  # no service filter
            if has_docs:
                results = await hybrid_search(query, service_name=None, top_n=_SEARCH_LIMIT)
                if results:
                    logger.info("Hybrid search used", extra={"result_count": len(results)})
                    return {"search_results": [r.model_dump() for r in results]}
        except Exception as exc:
            logger.warning(
                "Hybrid search unavailable — falling back to MCP", extra={"error": str(exc)}
            )

        # ── Fallback: MCP search ──────────────────────────────────────
        results = await mcp_tools.search_documentation(query, limit=_SEARCH_LIMIT)
        serialised = [r.model_dump() for r in results]
        logger.info("MCP search used", extra={"result_count": len(serialised)})
        return {"search_results": serialised}

    return node
