"""Vector indexer — upsert embedded chunks into Qdrant or OpenSearch."""

from __future__ import annotations

import asyncio
import uuid

from core.config import settings
from core.logging import get_logger
from services.vector.chunker import Chunk, chunk_document
from services.vector.embedder import embed_texts

logger = get_logger(__name__)

_UPSERT_BATCH = 50


def _chunk_id(url: str, chunk_index: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{url}#{chunk_index}"))


def _service_from_url(url: str) -> str:
    parts = url.lower().split("/")
    for i, part in enumerate(parts):
        if part in ("amazon", "aws") and i + 1 < len(parts):
            candidate = parts[i + 1].split(".")[0]
            if candidate and len(candidate) > 1:
                return candidate
    try:
        idx = parts.index("docs.aws.amazon.com")
        return parts[idx + 1] if idx + 1 < len(parts) else "unknown"
    except ValueError:
        return "unknown"


async def _upsert_opensearch(points: list[dict]) -> None:
    from services.vector.opensearch_client import get_client

    client = get_client()
    index = settings.opensearch_index

    for i in range(0, len(points), _UPSERT_BATCH):
        batch = points[i : i + _UPSERT_BATCH]
        body: list[dict] = []
        for doc in batch:
            body.append({"index": {"_index": index, "_id": doc["id"]}})
            body.append(doc["source"])
        await asyncio.to_thread(client.bulk, body=body, refresh=False)


async def _upsert_qdrant(points: list) -> None:
    from qdrant_client.http.models import PointStruct

    from services.vector.client import COLLECTION_NAME, get_client

    client = get_client()
    structs = [
        PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"]) for p in points
    ]
    for i in range(0, len(structs), _UPSERT_BATCH):
        batch = structs[i : i + _UPSERT_BATCH]
        await client.upsert(collection_name=COLLECTION_NAME, points=batch)


async def index_document(
    url: str,
    title: str,
    content: str,
    doc_hash: str = "",
    service_name: str | None = None,
) -> int:
    """Chunk and embed a single document. Returns chunk count."""
    svc = service_name or _service_from_url(url)
    chunks: list[Chunk] = chunk_document(
        content=content,
        url=url,
        title=title,
        service_name=svc,
        doc_hash=doc_hash,
    )

    if not chunks:
        return 0

    texts = [c.text for c in chunks]
    vectors = await embed_texts(texts)

    if settings.use_opensearch:
        os_points: list[dict] = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            doc_id = _chunk_id(url, chunk.chunk_index)
            os_points.append(
                {
                    "id": doc_id,
                    "source": {
                        "url": chunk.url,
                        "title": chunk.title,
                        "section": chunk.section,
                        "service_name": chunk.service_name,
                        "chunk_text": chunk.text,
                        "hash": chunk.hash,
                        "chunk_index": chunk.chunk_index,
                        "embedding": vector,
                    },
                }
            )
        await _upsert_opensearch(os_points)
    else:
        qdrant_points = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            qdrant_points.append(
                {
                    "id": _chunk_id(url, chunk.chunk_index),
                    "vector": vector,
                    "payload": {
                        "url": chunk.url,
                        "title": chunk.title,
                        "section": chunk.section,
                        "service_name": chunk.service_name,
                        "chunk_text": chunk.text,
                        "hash": chunk.hash,
                        "chunk_index": chunk.chunk_index,
                    },
                }
            )
        await _upsert_qdrant(qdrant_points)

    logger.info("Indexed document", extra={"url": url, "chunks": len(chunks)})
    return len(chunks)


async def index_all_cached(db_session: object) -> dict[str, int]:
    """Re-index every document in the PostgreSQL doc_cache."""
    from sqlalchemy import select

    from services.cache.models import DocCache

    result = await db_session.execute(select(DocCache).where(DocCache.deprecated.is_(False)))  # type: ignore[attr-defined]
    docs = result.scalars().all()

    stats = {"total": len(docs), "chunks": 0, "errors": 0}
    for doc in docs:
        try:
            n = await index_document(
                url=doc.url,
                title=doc.title or "",
                content=doc.content,
                doc_hash=doc.hash,
            )
            stats["chunks"] += n
        except Exception as exc:
            logger.error("Indexing failed", extra={"url": doc.url, "error": str(exc)})
            stats["errors"] += 1

    logger.info("Bulk indexing complete", extra=stats)
    return stats
