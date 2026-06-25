"""Vector store facade — Qdrant (local) or OpenSearch (AWS)."""

from __future__ import annotations

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

COLLECTION_NAME = "aws_docs"
VECTOR_SIZE = 1024 if settings.use_bedrock else 1536


async def init_vector_store(url: str | None = None) -> None:
    if settings.use_opensearch:
        from services.vector.opensearch_client import init_opensearch

        await init_opensearch(url or settings.opensearch_endpoint)
        return

    if settings.use_qdrant:
        from services.vector.client import init_qdrant

        await init_qdrant(url or settings.qdrant_url)
        return

    raise ValueError("No vector store configured (set OPENSEARCH_ENDPOINT or QDRANT_URL)")


async def close_vector_store() -> None:
    if settings.use_opensearch:
        from services.vector.opensearch_client import close_opensearch

        await close_opensearch()
        return

    if settings.use_qdrant:
        from services.vector.client import close_qdrant

        await close_qdrant()


async def collection_has_docs(service_name: str | None = None) -> bool:
    if settings.use_opensearch:
        from services.vector.opensearch_client import index_has_docs

        return await index_has_docs(service_name)

    if settings.use_qdrant:
        from services.vector.client import collection_has_docs as qdrant_has_docs

        return await qdrant_has_docs(service_name)

    return False
