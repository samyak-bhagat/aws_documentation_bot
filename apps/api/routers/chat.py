"""POST /chat — run the research agent and return a grounded answer."""

import time
import uuid

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from agents.graph.builder import build_graph
from agents.graph.state import AgentState
from apps.api.schemas import ChatRequest, ChatResponse, Citation
from core.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


async def _get_optional_db(request: Request) -> AsyncSession | None:
    """Return a DB session if the database is available, else None."""
    if not getattr(request.app.state, "db_available", False):
        return None
    from core.database import get_session

    async for session in get_session():
        return session
    return None


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request) -> ChatResponse:
    mcp_tools = getattr(request.app.state, "mcp_tools", None)
    if mcp_tools is None:
        raise HTTPException(
            status_code=503, detail="Agent not initialised — MCP server may be down."
        )

    session_id = body.session_id or str(uuid.uuid4())
    logger.info("Chat request received", extra={"session_id": session_id, "query": body.query})

    # ── Optionally load chat history for multi-turn context ───────────
    history_context = ""
    db_session = await _get_optional_db(request)
    if db_session is not None:
        from services.memory.repository import ChatMemoryRepository

        mem = ChatMemoryRepository(db_session)
        history_context = await mem.format_history(session_id)

    # ── Build graph with per-request DB session ───────────────────────
    compiled = build_graph(mcp_tools, db_session)

    initial_state: AgentState = {
        "user_query": body.query,
        "session_id": session_id,
    }

    # Prepend chat history to the user query when multi-turn is active
    if history_context:
        initial_state["user_query"] = (
            f"[Previous conversation]\n{history_context}\n\n[New question]\n{body.query}"
        )

    start = time.perf_counter()
    try:
        result = await compiled.ainvoke(initial_state)
    except Exception as exc:
        logger.error("Agent error", extra={"error": str(exc)})
        raise HTTPException(status_code=500, detail=f"Agent error: {exc}") from exc
    latency_ms = (time.perf_counter() - start) * 1000

    answer: str = result.get(
        "answer", "I could not find this information in the AWS documentation provided."
    )
    raw_citations: list[dict] = result.get("citations", [])
    sources = [Citation(title=c["title"], url=c["url"]) for c in raw_citations]

    # ── Persist messages to DB ────────────────────────────────────────
    if db_session is not None:
        from services.memory.repository import ChatMemoryRepository

        mem = ChatMemoryRepository(db_session)
        await mem.add_message(session_id, role="user", content=body.query)
        await mem.add_message(
            session_id,
            role="assistant",
            content=answer,
            citations=[c.model_dump() for c in sources],
            latency_ms=round(latency_ms, 1),
        )
        await db_session.close()

    logger.info(
        "Chat response ready",
        extra={
            "session_id": session_id,
            "latency_ms": round(latency_ms, 1),
            "sources": len(sources),
        },
    )
    return ChatResponse(
        answer=answer,
        sources=sources,
        session_id=session_id,
        latency_ms=round(latency_ms, 1),
    )
