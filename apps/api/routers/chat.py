"""POST /chat — run the research agent and return a grounded answer."""

import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from agents.graph.builder import build_graph
from agents.graph.state import AgentState
from apps.api.schemas import ChatRequest, ChatResponse, Citation
from core.config import settings
from core.logging import get_logger
from services.auth.jwt import TokenPayload, get_current_user

limiter = Limiter(key_func=get_remote_address)

router = APIRouter()
logger = get_logger(__name__)


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def chat(
    body: ChatRequest,
    request: Request,
    current_user: TokenPayload = Depends(get_current_user),  # noqa: B008
) -> ChatResponse:
    mcp_tools = getattr(request.app.state, "mcp_tools", None)
    if mcp_tools is None:
        raise HTTPException(
            status_code=503, detail="Agent not initialised — MCP server may be down."
        )

    session_id = body.session_id or str(uuid.uuid4())
    logger.info(
        "Chat request received",
        extra={"session_id": session_id, "query": body.query, "user_id": current_user.sub},
    )

    db_available = getattr(request.app.state, "db_available", False)

    # Use the session factory directly so the session lifecycle is fully
    # owned by this request handler — avoids early generator cleanup errors.
    if db_available:
        from core.database import _session_factory

        if _session_factory is None:
            db_available = False

    if db_available:
        from core.database import _session_factory  # noqa: F811
        from services.memory.repository import ChatMemoryRepository

        async with _session_factory() as db_session:  # type: ignore[misc]
            history_context = await ChatMemoryRepository(db_session).format_history(session_id)
            compiled = build_graph(mcp_tools, db_session)
            initial_state: AgentState = {"user_query": body.query, "session_id": session_id}
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

            mem = ChatMemoryRepository(db_session)
            await mem.add_message(session_id, role="user", content=body.query)
            await mem.add_message(
                session_id,
                role="assistant",
                content=answer,
                citations=[c.model_dump() for c in sources],
                latency_ms=round(latency_ms, 1),
            )
    else:
        # No DB — run without memory or cache persistence
        compiled = build_graph(mcp_tools)
        initial_state = {"user_query": body.query, "session_id": session_id}

        start = time.perf_counter()
        try:
            result = await compiled.ainvoke(initial_state)
        except Exception as exc:
            logger.error("Agent error", extra={"error": str(exc)})
            raise HTTPException(status_code=500, detail=f"Agent error: {exc}") from exc
        latency_ms = (time.perf_counter() - start) * 1000

        answer = result.get(
            "answer", "I could not find this information in the AWS documentation provided."
        )
        raw_citations = result.get("citations", [])
        sources = [Citation(title=c["title"], url=c["url"]) for c in raw_citations]

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
