"""FastAPI application — Phase 3.

Lifespan:
  - Opens a single MCP session on startup (shared by all requests)
  - Builds the LangGraph agent once and stores it on app.state
  - Closes the MCP session cleanly on shutdown
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agents.graph.builder import build_graph
from apps.api.routers import chat, health
from core.logging import get_logger
from services.mcp.client import MCPClient
from services.mcp.tools import AWSDocsMCPTools

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Start the MCP server and compile the agent graph on startup; tear down on shutdown."""
    logger.info("Starting up — connecting to MCP server")
    client = MCPClient()
    try:
        await client.connect()
        mcp_tools = AWSDocsMCPTools(client)
        app.state.graph = build_graph(mcp_tools)
        app.state.mcp_connected = True
        logger.info("MCP connected — agent ready")
    except Exception as exc:
        logger.error("MCP connection failed", extra={"error": str(exc)})
        app.state.graph = None
        app.state.mcp_connected = False

    yield  # ── server is running ─────────────────────────────────────────

    logger.info("Shutting down — closing MCP session")
    await client.disconnect()
    app.state.mcp_connected = False


def create_app() -> FastAPI:
    app = FastAPI(
        title="AWS Documentation Assistant",
        description="Answers AWS questions using only official AWS documentation via MCP.",
        version="0.3.0",
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
