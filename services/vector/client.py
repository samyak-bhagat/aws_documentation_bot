"""Qdrant client singleton — Phase 7.

Manages the lifecycle of a single QdrantClient shared across the application.
Uses OpenAI text-embedding-3-small (1536-d) for all embeddings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    VectorParams,
)

from core.config import settings
from core.logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

COLLECTION_NAME = "aws_docs"
VECTOR_SIZE = 1536  # text-embedding-3-small
DISTANCE = Distance.COSINE

_client: AsyncQdrantClient | None = None


def get_client() -> AsyncQdrantClient:
    """Return the shared Qdrant client (must call init_qdrant first)."""
    if _client is None:
        raise RuntimeError("Qdrant client not initialised — call init_qdrant() first")
    return _client


async def init_qdrant(url: str | None = None) -> AsyncQdrantClient:
    """Connect to Qdrant and ensure the collection + payload indexes exist."""
    global _client
    qdrant_url = url or settings.qdrant_url
    _client = AsyncQdrantClient(url=qdrant_url)

    # Create collection if it doesn't exist
    existing = await _client.get_collections()
    names = [c.name for c in existing.collections]
    if COLLECTION_NAME not in names:
        await _client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=DISTANCE),
        )
        logger.info("Qdrant collection created", extra={"collection": COLLECTION_NAME})

        # Payload indexes for fast filtered search
        for field, schema in [
            ("service_name", PayloadSchemaType.KEYWORD),
            ("url", PayloadSchemaType.KEYWORD),
        ]:
            await _client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field,
                field_schema=schema,
            )
        logger.info("Payload indexes created")
    else:
        logger.info("Qdrant collection already exists", extra={"collection": COLLECTION_NAME})

    return _client


async def close_qdrant() -> None:
    """Close the Qdrant client connection."""
    global _client
    if _client:
        await _client.close()
        _client = None
        logger.info("Qdrant client closed")


async def collection_has_docs(service_name: str | None = None) -> bool:
    """Return True if the collection has any indexed documents (optionally filtered by service)."""
    client = get_client()
    try:
        if service_name:
            count = await client.count(
                collection_name=COLLECTION_NAME,
                count_filter=Filter(
                    must=[FieldCondition(key="service_name", match=MatchValue(value=service_name))]
                ),
            )
        else:
            count = await client.count(collection_name=COLLECTION_NAME)
        return count.count > 0
    except Exception:
        return False
