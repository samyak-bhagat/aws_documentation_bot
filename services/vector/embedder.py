"""Embedding helper — OpenAI (local) or Amazon Bedrock Titan (AWS)."""

from __future__ import annotations

import asyncio
import json

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

_OPENAI_MODEL = "text-embedding-3-small"
_BATCH_SIZE = 100

_openai_client = None
_bedrock_client = None


def _get_openai():
    global _openai_client
    if _openai_client is None:
        from openai import AsyncOpenAI

        _openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _openai_client


def _get_bedrock():
    global _bedrock_client
    if _bedrock_client is None:
        import boto3

        _bedrock_client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
    return _bedrock_client


async def _embed_openai(texts: list[str]) -> list[list[float]]:
    client = _get_openai()
    all_vectors: list[list[float]] = []

    for i in range(0, len(texts), _BATCH_SIZE):
        batch = texts[i : i + _BATCH_SIZE]
        response = await client.embeddings.create(model=_OPENAI_MODEL, input=batch)
        all_vectors.extend([item.embedding for item in response.data])
        if i + _BATCH_SIZE < len(texts):
            await asyncio.sleep(0.1)

    return all_vectors


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

    if settings.use_bedrock:
        return await _embed_bedrock(texts)
    return await _embed_openai(texts)


async def embed_query(text: str) -> list[float]:
    """Embed a single query string."""
    vectors = await embed_texts([text])
    return vectors[0]
