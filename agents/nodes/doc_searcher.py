"""Node: search AWS documentation via MCP and store ranked results."""

from services.mcp.tools import AWSDocsMCPTools
from agents.graph.state import AgentState
from core.logging import get_logger

logger = get_logger(__name__)

_SEARCH_LIMIT = 5


def make_doc_searcher(mcp_tools: AWSDocsMCPTools):
    """Return a LangGraph node function with MCP tools injected."""

    async def node(state: AgentState) -> dict:
        query = state["optimized_query"]
        logger.info("Searching docs", extra={"query": query})

        results = await mcp_tools.search_documentation(query, limit=_SEARCH_LIMIT)
        serialised = [r.model_dump() for r in results]

        logger.info("Search complete", extra={"result_count": len(serialised)})
        return {"search_results": serialised}

    return node
