"""Node: analyse the user query to extract service, intent, and an optimised search query."""

from pathlib import Path

from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from agents.graph.state import AgentState
from core.logging import get_logger

logger = get_logger(__name__)

_PROMPT = (Path(__file__).parent.parent / "prompts" / "query_analysis.txt").read_text()


class _QueryAnalysis(BaseModel):
    aws_service: str
    user_intent: str
    optimized_query: str


def make_query_analyzer(llm: ChatOpenAI):
    """Return a LangGraph node function with the LLM injected."""
    structured_llm = llm.with_structured_output(_QueryAnalysis)

    async def node(state: AgentState) -> dict:
        user_query = state["user_query"]
        logger.info("Analysing query", extra={"query": user_query})

        prompt = _PROMPT.format(user_query=user_query)
        result: _QueryAnalysis = await structured_llm.ainvoke(prompt)  # type: ignore[assignment]

        logger.info(
            "Query analysed",
            extra={
                "aws_service": result.aws_service,
                "user_intent": result.user_intent,
                "optimized_query": result.optimized_query,
            },
        )
        return {
            "aws_service": result.aws_service,
            "user_intent": result.user_intent,
            "optimized_query": result.optimized_query,
            "retry_count": 0,
            "search_results": [],
            "documents": [],
            "context": "",
        }

    return node
