"""Amazon OpenSearch client — Phase 7 AWS.

k-NN vector index for semantic search. Uses IAM SigV4 in AWS; optional basic auth locally.
"""

from __future__ import annotations

import asyncio
from typing import Any

import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

INDEX_NAME = "aws_docs"
VECTOR_SIZE = 1024  # amazon.titan-embed-text-v2:0

_client: OpenSearch | None = None


def _build_client(endpoint: str) -> OpenSearch:
    host = endpoint.removeprefix("https://").removeprefix("http://").rstrip("/")

    if settings.opensearch_username and settings.opensearch_password:
        http_auth = (settings.opensearch_username, settings.opensearch_password)
    else:
        session = boto3.Session(region_name=settings.aws_region)
        creds = session.get_credentials()
        if creds is None:
            raise RuntimeError("No AWS credentials for OpenSearch IAM auth")
        http_auth = AWS4Auth(
            creds.access_key,
            creds.secret_key,
            settings.aws_region,
            "es",
            session_token=creds.token,
        )

    return OpenSearch(
        hosts=[{"host": host, "port": 443}],
        http_auth=http_auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=30,
    )


def get_client() -> OpenSearch:
    if _client is None:
        raise RuntimeError("OpenSearch not initialised — call init_opensearch() first")
    return _client


def _index_mapping() -> dict[str, Any]:
    return {
        "settings": {"index": {"knn": True}},
        "mappings": {
            "properties": {
                "url": {"type": "keyword"},
                "title": {"type": "text"},
                "section": {"type": "keyword"},
                "service_name": {"type": "keyword"},
                "chunk_text": {"type": "text"},
                "hash": {"type": "keyword"},
                "chunk_index": {"type": "integer"},
                "embedding": {
                    "type": "knn_vector",
                    "dimension": VECTOR_SIZE,
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "faiss",
                    },
                },
            }
        },
    }


async def init_opensearch(endpoint: str | None = None) -> OpenSearch:
    global _client
    url = endpoint or settings.opensearch_endpoint
    if not url:
        raise ValueError("OPENSEARCH_ENDPOINT is not set")

    _client = _build_client(url)
    index = settings.opensearch_index or INDEX_NAME

    exists = await asyncio.to_thread(_client.indices.exists, index=index)
    if not exists:
        await asyncio.to_thread(_client.indices.create, index=index, body=_index_mapping())
        logger.info("OpenSearch index created", extra={"index": index})
    else:
        logger.info("OpenSearch index already exists", extra={"index": index})

    return _client


async def close_opensearch() -> None:
    global _client
    _client = None
    logger.info("OpenSearch client closed")


async def index_has_docs(service_name: str | None = None) -> bool:
    client = get_client()
    index = settings.opensearch_index or INDEX_NAME

    body: dict[str, Any] = {"query": {"match_all": {}}}
    if service_name:
        body = {"query": {"term": {"service_name": service_name}}}

    result = await asyncio.to_thread(client.count, index=index, body=body)
    return int(result.get("count", 0)) > 0
