"""Embedding helper — Amazon Bedrock Titan."""

from __future__ import annotations

import asyncio
import json

import boto3

from core.config import settings
from core.logging import get_logger
from core.telemetry import trace_span

logger = get_logger(__name__)

_bedrock_client = None


def _get_bedrock():
    global _bedrock_client
    if _bedrock_client is None:
        _bedrock_client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
    return _bedrock_client


async def _embed_bedrock(texts: list[str]) -> list[list[float]]:
    client = _get_bedrock()
    vectors: list[list[float]] = []

    for text in texts:
        body = json.dumps(
            {
                "inputText": text,
                "dimensions": 1024,
                "normalize": True,
            }
        )
        with trace_span("bedrock.embed", {"model": settings.bedrock_embed_model_id}):
            response = await asyncio.to_thread(
                client.invoke_model,
                modelId=settings.bedrock_embed_model_id,
                body=body.encode(),
                contentType="application/json",
                accept="application/json",
            )
        payload = json.loads(response["body"].read())
        vectors.append(payload["embedding"])

    return vectors


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Return a list of embedding vectors (one per input text)."""
    if not texts:
        return []
    if not settings.bedrock_embed_model_id:
        raise RuntimeError("BEDROCK_EMBED_MODEL_ID is not configured")
    return await _embed_bedrock(texts)


async def embed_query(text: str) -> list[float]:
    """Embed a single query string."""
    vectors = await embed_texts([text])
    return vectors[0]
