"""Node: generate a grounded answer from the retrieved context using the LLM."""

from pathlib import Path

from langchain_openai import ChatOpenAI

from agents.graph.state import AgentState
from core.logging import get_logger

logger = get_logger(__name__)

_PROMPT = (Path(__file__).parent.parent / "prompts" / "answer_generation.txt").read_text()

_FALLBACK = (
    "I could not find this information in the AWS documentation provided."
)


def make_answer_generator(llm: ChatOpenAI):
    """Return a LangGraph node function with the LLM injected."""

    async def node(state: AgentState) -> dict:
        context = state.get("context", "")
        user_query = state["user_query"]

        if not context.strip():
            logger.info("No context available — returning fallback answer")
            return {"answer": _FALLBACK}

        prompt = _PROMPT.format(context=context, user_query=user_query)
        logger.info("Generating answer")

        response = await llm.ainvoke(prompt)
        answer = response.content if hasattr(response, "content") else str(response)

        logger.info("Answer generated", extra={"answer_length": len(answer)})
        return {"answer": answer}

    return node
