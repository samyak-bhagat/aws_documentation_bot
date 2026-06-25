"""OpenAI embedding helper — Phase 7.

Uses text-embedding-3-small (1536-d) to keep costs low.
Batches up to 100 texts per API call.
"""

from __future__ import annotations

import asyncio

from openai import AsyncOpenAI

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

_EMBED_MODEL = "text-embedding-3-small"
_BATCH_SIZE = 100

_client: AsyncOpenAI | None = None


def _get_openai() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Return a list of embedding vectors (one per input text)."""
    if not texts:
        return []

    client = _get_openai()
    all_vectors: list[list[float]] = []

    for i in range(0, len(texts), _BATCH_SIZE):
        batch = texts[i : i + _BATCH_SIZE]
        response = await client.embeddings.create(model=_EMBED_MODEL, input=batch)
        all_vectors.extend([item.embedding for item in response.data])
        if i + _BATCH_SIZE < len(texts):
            await asyncio.sleep(0.1)  # gentle rate-limit pause

    return all_vectors


async def embed_query(text: str) -> list[float]:
    """Embed a single query string."""
    vectors = await embed_texts([text])
    return vectors[0]
