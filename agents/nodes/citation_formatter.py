"""Node: build a deduplicated citation list from the documents that were read."""

from agents.graph.state import AgentState
from core.logging import get_logger

logger = get_logger(__name__)


def citation_formatter_node(state: AgentState) -> dict:
    documents = state.get("documents", [])

    seen: set[str] = set()
    citations: list[dict] = []

    for doc in documents:
        url = doc.get("url", "")
        if not url or url in seen:
            continue
        seen.add(url)
        citations.append(
            {
                "title": doc.get("title") or url,
                "url": url,
            }
        )

    logger.info("Citations formatted", extra={"count": len(citations)})
    return {"citations": citations}
