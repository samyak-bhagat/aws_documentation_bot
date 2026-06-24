"""Node: fetch full content for the top N search results.

Cache hierarchy:
  1. PostgreSQL (DocCacheRepository) — persistent, TTL-aware  [Phase 5+]
  2. In-memory dict — session-scoped fallback when DB is unavailable
"""

from sqlalchemy.ext.asyncio import AsyncSession

from agents.graph.state import AgentState
from core.logging import get_logger
from services.mcp.schemas import DocumentContent
from services.mcp.tools import AWSDocsMCPTools

logger = get_logger(__name__)

# In-memory fallback cache (used when PostgreSQL is not configured)
_page_cache: dict[str, DocumentContent] = {}

_TOP_N = 3  # number of search results to read in full
_MAX_CHARS = 8000  # max chars to fetch per page


def make_doc_reader(mcp_tools: AWSDocsMCPTools, db_session: AsyncSession | None = None):
    """Return a LangGraph node function with MCP tools and optional DB session injected."""

    async def node(state: AgentState) -> dict:
        search_results = state.get("search_results", [])
        top = [r for r in search_results if r.get("url")][:_TOP_N]

        documents: list[dict] = []
        for result in top:
            url: str = result["url"]
            title_from_search: str = result.get("title", "")

            doc = await _resolve_doc(url, title_from_search, mcp_tools, db_session)
            documents.append(
                {
                    "url": doc.url,
                    "title": doc.title or title_from_search,
                    "content": doc.content,
                    "sections": doc.sections,
                }
            )

        logger.info("Doc reading complete", extra={"docs_read": len(documents)})
        return {"documents": documents}

    return node


async def _resolve_doc(
    url: str,
    title_hint: str,
    mcp_tools: AWSDocsMCPTools,
    db_session: AsyncSession | None,
) -> DocumentContent:
    """Return doc content from DB cache, in-memory cache, or MCP (in that order)."""
    from services.cache.repository import DocCacheRepository

    # ── Try PostgreSQL cache ───────────────────────────────────────────
    if db_session is not None:
        repo = DocCacheRepository(db_session)
        entry = await repo.get(url)
        if entry and repo.is_fresh(entry):
            logger.info("DB cache hit", extra={"url": url})
            return DocumentContent(
                url=entry.url,
                title=entry.title,
                content=entry.content,
                sections=[],
            )

    # ── Try in-memory cache ───────────────────────────────────────────
    if url in _page_cache:
        logger.info("In-memory cache hit", extra={"url": url})
        return _page_cache[url]

    # ── Fetch from MCP ────────────────────────────────────────────────
    logger.info("Fetching from MCP", extra={"url": url})
    doc = await mcp_tools.read_documentation(url, max_length=_MAX_CHARS)

    # Persist to PostgreSQL if available
    if db_session is not None:
        repo = DocCacheRepository(db_session)
        await repo.upsert(url=url, title=doc.title or title_hint, content=doc.content)

    # Always populate in-memory cache as fast path
    _page_cache[url] = doc
    return doc
