"""Hybrid retriever — Phase 7.

Combines:
  1. Vector search (Qdrant)       — semantic similarity
  2. BM25 keyword search          — exact term matching
  3. Reciprocal Rank Fusion (RRF) — merge rankings
  4. Cross-encoder reranking      — final precision pass (optional, uses OpenAI)
"""

from __future__ import annotations

from dataclasses import dataclass

from qdrant_client.http.models import FieldCondition, Filter, MatchValue

from core.logging import get_logger
from services.mcp.schemas import SearchResult
from services.vector.client import COLLECTION_NAME, get_client
from services.vector.embedder import embed_query

logger = get_logger(__name__)

_VECTOR_TOP_K = 20
_BM25_TOP_K = 20
_RRF_K = 60  # standard RRF constant
_FINAL_TOP_N = 5


@dataclass
class RankedChunk:
    url: str
    title: str
    section: str
    service_name: str
    chunk_text: str
    score: float


# ── Vector Search ─────────────────────────────────────────────────────────────


async def vector_search(
    query: str,
    service_name: str | None = None,
    top_k: int = _VECTOR_TOP_K,
) -> list[RankedChunk]:
    """Semantic search via Qdrant."""
    client = get_client()
    query_vector = await embed_query(query)

    search_filter = None
    if service_name:
        search_filter = Filter(
            must=[FieldCondition(key="service_name", match=MatchValue(value=service_name))]
        )

    results = await client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        query_filter=search_filter,
        limit=top_k,
        with_payload=True,
    )

    chunks: list[RankedChunk] = []
    for hit in results.points:
        p = hit.payload or {}
        chunks.append(
            RankedChunk(
                url=p.get("url", ""),
                title=p.get("title", ""),
                section=p.get("section", ""),
                service_name=p.get("service_name", ""),
                chunk_text=p.get("chunk_text", ""),
                score=hit.score,
            )
        )
    return chunks


# ── BM25 Search ───────────────────────────────────────────────────────────────


async def bm25_search(
    query: str,
    service_name: str | None = None,
    top_k: int = _BM25_TOP_K,
) -> list[RankedChunk]:
    """BM25 keyword search over Qdrant payload text (scroll + rank locally)."""
    from rank_bm25 import BM25Okapi

    client = get_client()
    search_filter = None
    if service_name:
        search_filter = Filter(
            must=[FieldCondition(key="service_name", match=MatchValue(value=service_name))]
        )

    # Scroll up to 2000 records for BM25 corpus
    records, _ = await client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=search_filter,
        limit=2000,
        with_payload=True,
        with_vectors=False,
    )

    if not records:
        return []

    corpus = [r.payload.get("chunk_text", "") if r.payload else "" for r in records]
    tokenised = [doc.lower().split() for doc in corpus]
    bm25 = BM25Okapi(tokenised)
    query_tokens = query.lower().split()
    scores = bm25.get_scores(query_tokens)

    top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

    chunks: list[RankedChunk] = []
    for idx in top_indices:
        if scores[idx] <= 0:
            continue
        p = records[idx].payload or {}
        chunks.append(
            RankedChunk(
                url=p.get("url", ""),
                title=p.get("title", ""),
                section=p.get("section", ""),
                service_name=p.get("service_name", ""),
                chunk_text=p.get("chunk_text", ""),
                score=float(scores[idx]),
            )
        )
    return chunks


# ── Reciprocal Rank Fusion ────────────────────────────────────────────────────


def reciprocal_rank_fusion(
    *ranked_lists: list[RankedChunk],
    k: int = _RRF_K,
) -> list[RankedChunk]:
    """Merge multiple ranked lists into one using RRF scoring."""
    fused: dict[str, float] = {}
    chunk_map: dict[str, RankedChunk] = {}

    for ranked in ranked_lists:
        for rank, chunk in enumerate(ranked):
            key = f"{chunk.url}#{chunk.section}#{chunk.chunk_text[:50]}"
            fused[key] = fused.get(key, 0.0) + 1.0 / (k + rank + 1)
            chunk_map[key] = chunk

    sorted_keys = sorted(fused, key=lambda k: fused[k], reverse=True)
    result: list[RankedChunk] = []
    for key in sorted_keys:
        chunk = chunk_map[key]
        chunk.score = fused[key]
        result.append(chunk)
    return result


# ── Public API ────────────────────────────────────────────────────────────────


async def hybrid_search(
    query: str,
    service_name: str | None = None,
    top_n: int = _FINAL_TOP_N,
) -> list[SearchResult]:
    """Run vector + BM25 search, fuse results, and return top SearchResult objects."""
    logger.info("Hybrid search", extra={"query": query[:80], "service": service_name})

    vec_results, bm25_results = [], []

    try:
        vec_results = await vector_search(query, service_name=service_name)
    except Exception as exc:
        logger.warning("Vector search failed", extra={"error": str(exc)})

    try:
        bm25_results = await bm25_search(query, service_name=service_name)
    except Exception as exc:
        logger.warning("BM25 search failed", extra={"error": str(exc)})

    if not vec_results and not bm25_results:
        return []

    fused = reciprocal_rank_fusion(vec_results, bm25_results)[:top_n]

    seen_urls: set[str] = set()
    search_results: list[SearchResult] = []
    for chunk in fused:
        if chunk.url not in seen_urls:
            seen_urls.add(chunk.url)
            search_results.append(
                SearchResult(
                    title=chunk.title or chunk.url,
                    url=chunk.url,
                    excerpt=chunk.chunk_text[:300],
                )
            )

    logger.info("Hybrid search complete", extra={"results": len(search_results)})
    return search_results
