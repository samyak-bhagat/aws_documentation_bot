"""Node: search AWS documentation.

Strategy:
  1. If OpenSearch has indexed docs → hybrid search (vector + BM25 + RRF)
  2. Otherwise → fall back to MCP keyword search
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

        try:
            from services.vector.retriever import hybrid_search
            from services.vector.store import collection_has_docs

            has_docs = await collection_has_docs()
            if has_docs:
                results = await hybrid_search(query, service_name=None, top_n=_SEARCH_LIMIT)
                if results:
                    logger.info("Hybrid search used", extra={"result_count": len(results)})
                    return {"search_results": [r.model_dump() for r in results]}
        except Exception as exc:
            logger.warning(
                "Hybrid search unavailable — falling back to MCP", extra={"error": str(exc)}
            )

        results = await mcp_tools.search_documentation(query, limit=_SEARCH_LIMIT)
        serialised = [r.model_dump() for r in results]
        logger.info("MCP search used", extra={"result_count": len(serialised)})
        return {"search_results": serialised}

    return node
