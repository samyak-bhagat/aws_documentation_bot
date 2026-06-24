"""Node: fetch full content for the top N search results, with in-memory cache."""

from agents.graph.state import AgentState
from core.logging import get_logger
from services.mcp.schemas import DocumentContent
from services.mcp.tools import AWSDocsMCPTools

logger = get_logger(__name__)

# In-memory cache keyed by URL — avoids re-fetching the same page within a session.
# Replaced by PostgreSQL in Phase 5.
_page_cache: dict[str, DocumentContent] = {}

_TOP_N = 3  # number of search results to read in full
_MAX_CHARS = 8000  # max chars to fetch per page


def make_doc_reader(mcp_tools: AWSDocsMCPTools):
    """Return a LangGraph node function with MCP tools injected."""

    async def node(state: AgentState) -> dict:
        search_results = state.get("search_results", [])
        top = [r for r in search_results if r.get("url")][:_TOP_N]

        documents: list[dict] = []
        for result in top:
            url: str = result["url"]
            if url not in _page_cache:
                logger.info("Fetching doc page", extra={"url": url})
                _page_cache[url] = await mcp_tools.read_documentation(url, max_length=_MAX_CHARS)
            else:
                logger.info("Cache hit", extra={"url": url})

            doc = _page_cache[url]
            # Carry the title from the search result if the page didn't return one
            title = doc.title or result.get("title", "")
            documents.append(
                {
                    "url": doc.url,
                    "title": title,
                    "content": doc.content,
                    "sections": doc.sections,
                }
            )

        logger.info("Doc reading complete", extra={"docs_read": len(documents)})
        return {"documents": documents}

    return node
