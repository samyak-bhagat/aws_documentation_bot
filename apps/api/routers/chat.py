"""POST /chat — run the research agent and return a grounded answer."""

import time
import uuid

from fastapi import APIRouter, HTTPException, Request

from apps.api.schemas import ChatRequest, ChatResponse, Citation
from agents.graph.state import AgentState
from core.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request) -> ChatResponse:
    compiled_graph = getattr(request.app.state, "graph", None)
    if compiled_graph is None:
        raise HTTPException(status_code=503, detail="Agent not initialised — MCP server may be down.")

    session_id = body.session_id or str(uuid.uuid4())
    logger.info("Chat request received", extra={"session_id": session_id, "query": body.query})

    initial_state: AgentState = {
        "user_query": body.query,
        "session_id": session_id,
    }

    start = time.perf_counter()
    try:
        result = await compiled_graph.ainvoke(initial_state)
    except Exception as exc:
        logger.error("Agent error", extra={"error": str(exc)})
        raise HTTPException(status_code=500, detail=f"Agent error: {exc}") from exc
    latency_ms = (time.perf_counter() - start) * 1000

    answer: str = result.get("answer", "I could not find this information in the AWS documentation provided.")
    raw_citations: list[dict] = result.get("citations", [])
    sources = [Citation(title=c["title"], url=c["url"]) for c in raw_citations]

    logger.info(
        "Chat response ready",
        extra={"session_id": session_id, "latency_ms": round(latency_ms, 1), "sources": len(sources)},
    )
    return ChatResponse(
        answer=answer,
        sources=sources,
        session_id=session_id,
        latency_ms=round(latency_ms, 1),
    )
