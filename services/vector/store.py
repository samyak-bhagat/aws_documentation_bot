"""Vector store facade — Amazon OpenSearch."""

from __future__ import annotations

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

INDEX_NAME = "aws_docs"
VECTOR_SIZE = 1024


async def init_vector_store(url: str | None = None) -> None:
    from services.vector.opensearch_client import init_opensearch

    endpoint = url or settings.opensearch_endpoint
    if not endpoint:
        raise ValueError("OPENSEARCH_ENDPOINT is not set")
    await init_opensearch(endpoint)


async def close_vector_store() -> None:
    from services.vector.opensearch_client import close_opensearch

    await close_opensearch()


async def collection_has_docs(service_name: str | None = None) -> bool:
    from services.vector.opensearch_client import index_has_docs

    return await index_has_docs(service_name)
