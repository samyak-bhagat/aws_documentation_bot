"""LLM factory — Amazon Bedrock."""

from __future__ import annotations

from langchain_aws import ChatBedrock
from langchain_core.language_models.chat_models import BaseChatModel

from core.config import settings


def get_chat_llm() -> BaseChatModel:
    """Return the configured Bedrock chat model."""
    if not settings.bedrock_model_id:
        raise RuntimeError("BEDROCK_MODEL_ID is not configured")

    return ChatBedrock(
        model_id=settings.bedrock_model_id,
        region_name=settings.aws_region,
        model_kwargs={"temperature": 0},
    )
