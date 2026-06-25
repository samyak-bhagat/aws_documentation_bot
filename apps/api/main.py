"""FastAPI application — Phase 5.

Lifespan:
  - Opens a single MCP session on startup (shared by all requests)
  - Initialises PostgreSQL tables (if DATABASE_URL is set)
  - Builds the LangGraph agent once and stores it on app.state
  - Closes MCP session and DB engine cleanly on shutdown
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agents.graph.builder import build_graph
from apps.api.routers import admin, chat, health
from core.config import settings
from core.logging import get_logger
from services.mcp.client import MCPClient
from services.mcp.tools import AWSDocsMCPTools
from services.sync.scheduler import start_scheduler, stop_scheduler

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup: connect MCP + init DB. Shutdown: close both cleanly."""
    # ── Database (optional — skipped if DATABASE_URL is empty) ────────
    app.state.db_available = False
    if settings.database_url:
        try:
            from core.database import init_db

            await init_db()
            app.state.db_available = True
            logger.info("PostgreSQL connected and tables ready")
        except Exception as exc:
            logger.warning(
                "PostgreSQL unavailable — running without DB cache", extra={"error": str(exc)}
            )

    # ── MCP server ────────────────────────────────────────────────────
    logger.info("Starting up — connecting to MCP server")
    client = MCPClient()
    try:
        await client.connect()
        mcp_tools = AWSDocsMCPTools(client)
        app.state.mcp_tools = mcp_tools
        app.state.mcp_client = client
        app.state.graph = build_graph(mcp_tools)  # graph without per-request DB session
        app.state.mcp_connected = True
        logger.info("MCP connected — agent ready")

        # Start daily knowledge sync scheduler
        app.state.scheduler = start_scheduler(mcp_tools, db_available=app.state.db_available)
    except Exception as exc:
        logger.error("MCP connection failed", extra={"error": str(exc)})
        app.state.graph = None
        app.state.mcp_tools = None
        app.state.mcp_client = client
        app.state.mcp_connected = False

    yield  # ── server is running ──────────────────────────────────────

    logger.info("Shutting down")
    stop_scheduler()
    await client.disconnect()
    app.state.mcp_connected = False

    if app.state.db_available:
        from core.database import close_db

        await close_db()


def create_app() -> FastAPI:
    app = FastAPI(
        title="AWS Documentation Assistant",
        description="Answers AWS questions using only official AWS documentation via MCP.",
        version="0.5.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8501"],  # Streamlit UI in Phase 8
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(admin.router)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "apps.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
