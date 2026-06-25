"""Hybrid retriever — OpenSearch vector + BM25 + RRF."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from core.config import settings
from core.logging import get_logger
from core.telemetry import trace_span
from services.mcp.schemas import SearchResult
from services.vector.embedder import embed_query

logger = get_logger(__name__)

_VECTOR_TOP_K = 20
_BM25_TOP_K = 20
_RRF_K = 60
_FINAL_TOP_N = 5


@dataclass
class RankedChunk:
    url: str
    title: str
    section: str
    service_name: str
    chunk_text: str
    score: float


async def _opensearch_vector_search(
    query: str,
    service_name: str | None = None,
    top_k: int = _VECTOR_TOP_K,
) -> list[RankedChunk]:
    from services.vector.opensearch_client import get_client

    client = get_client()
    index = settings.opensearch_index
    query_vector = await embed_query(query)

    knn_clause: dict = {"embedding": {"vector": query_vector, "k": top_k}}
    if service_name:
        body = {
            "size": top_k,
            "query": {
                "bool": {
                    "filter": [{"term": {"service_name": service_name}}],
                    "must": [{"knn": knn_clause}],
                }
            },
        }
    else:
        body = {"size": top_k, "query": {"knn": knn_clause}}

    with trace_span("opensearch.vector_search", {"index": index}):
        result = await asyncio.to_thread(client.search, index=index, body=body)

    chunks: list[RankedChunk] = []
    for hit in result.get("hits", {}).get("hits", []):
        src = hit.get("_source", {})
        chunks.append(
            RankedChunk(
                url=src.get("url", ""),
                title=src.get("title", ""),
                section=src.get("section", ""),
                service_name=src.get("service_name", ""),
                chunk_text=src.get("chunk_text", ""),
                score=float(hit.get("_score", 0)),
            )
        )
    return chunks


async def _opensearch_bm25_search(
    query: str,
    service_name: str | None = None,
    top_k: int = _BM25_TOP_K,
) -> list[RankedChunk]:
    from services.vector.opensearch_client import get_client

    client = get_client()
    index = settings.opensearch_index

    must: list[dict] = [{"match": {"chunk_text": query}}]
    filters: list[dict] = []
    if service_name:
        filters.append({"term": {"service_name": service_name}})

    body = {
        "size": top_k,
        "query": {"bool": {"must": must, "filter": filters}},
    }
    with trace_span("opensearch.bm25_search", {"index": index}):
        result = await asyncio.to_thread(client.search, index=index, body=body)

    chunks: list[RankedChunk] = []
    for hit in result.get("hits", {}).get("hits", []):
        src = hit.get("_source", {})
        chunks.append(
            RankedChunk(
                url=src.get("url", ""),
                title=src.get("title", ""),
                section=src.get("section", ""),
                service_name=src.get("service_name", ""),
                chunk_text=src.get("chunk_text", ""),
                score=float(hit.get("_score", 0)),
            )
        )
    return chunks


async def vector_search(
    query: str,
    service_name: str | None = None,
    top_k: int = _VECTOR_TOP_K,
) -> list[RankedChunk]:
    return await _opensearch_vector_search(query, service_name, top_k)


async def bm25_search(
    query: str,
    service_name: str | None = None,
    top_k: int = _BM25_TOP_K,
) -> list[RankedChunk]:
    return await _opensearch_bm25_search(query, service_name, top_k)


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
