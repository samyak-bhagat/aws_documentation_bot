"""Node: merge fetched documents into a single, deduplicated context string."""

from agents.graph.state import AgentState
from core.logging import get_logger

logger = get_logger(__name__)

_MAX_CONTENT_PER_DOC = 3000  # chars per document
_MAX_TOTAL_CONTEXT = 12000  # total context chars sent to the LLM


def context_builder_node(state: AgentState) -> dict:
    documents = state.get("documents", [])

    seen_urls: set[str] = set()
    parts: list[str] = []

    for doc in documents:
        url = doc.get("url", "")
        if url in seen_urls:
            continue
        seen_urls.add(url)

        title = doc.get("title", "Untitled")
        content = doc.get("content", "")[:_MAX_CONTENT_PER_DOC]
        parts.append(f"### {title}\nSource: {url}\n\n{content}")

    context = "\n\n---\n\n".join(parts)
    # Hard cap on total context size
    if len(context) > _MAX_TOTAL_CONTEXT:
        context = context[:_MAX_TOTAL_CONTEXT] + "\n\n[Context truncated]"

    logger.info(
        "Context built",
        extra={"doc_count": len(parts), "context_length": len(context)},
    )
    return {"context": context}
