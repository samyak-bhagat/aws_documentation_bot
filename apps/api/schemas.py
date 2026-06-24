import uuid

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="The AWS question to answer")
    session_id: str | None = Field(None, description="Optional session ID for multi-turn (Phase 5+)")


class Citation(BaseModel):
    title: str
    url: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[Citation]
    session_id: str
    latency_ms: float


class HealthResponse(BaseModel):
    status: str        # "ok"
    mcp_connected: bool


def new_session_id() -> str:
    return str(uuid.uuid4())
