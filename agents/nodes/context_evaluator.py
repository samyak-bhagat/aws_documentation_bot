"""Node: decide whether the retrieved context is sufficient to answer the question."""

from agents.graph.state import AgentState
from core.logging import get_logger

logger = get_logger(__name__)

_MIN_CONTEXT_CHARS = 300  # below this threshold we consider context insufficient


def context_evaluator_node(state: AgentState) -> dict:
    context = state.get("context", "")
    sufficient = len(context) >= _MIN_CONTEXT_CHARS

    logger.info(
        "Context evaluated",
        extra={"sufficient": sufficient, "context_length": len(context)},
    )
    return {"context_sufficient": sufficient}
