"""LLM factory — OpenAI (local dev) or Amazon Bedrock (AWS)."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from core.config import settings


def get_chat_llm() -> BaseChatModel:
    """Return the configured chat model."""
    if settings.use_bedrock:
        from langchain_aws import ChatBedrock

        return ChatBedrock(
            model_id=settings.bedrock_model_id,
            region_name=settings.aws_region,
            model_kwargs={"temperature": 0},
        )

    from langchain_openai import ChatOpenAI
    from pydantic import SecretStr

    return ChatOpenAI(
        model=settings.openai_model,
        temperature=0,
        api_key=SecretStr(settings.openai_api_key),
    )
