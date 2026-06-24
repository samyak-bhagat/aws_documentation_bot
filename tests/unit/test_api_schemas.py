"""Unit tests for apps/api/schemas.py — no server required."""

import pytest
from pydantic import ValidationError

from apps.api.schemas import ChatRequest, ChatResponse, Citation, HealthResponse, new_session_id


class TestChatRequest:
    def test_valid_query(self):
        req = ChatRequest(query="How do I secure an S3 bucket?")
        assert req.query == "How do I secure an S3 bucket?"
        assert req.session_id is None

    def test_with_session_id(self):
        req = ChatRequest(query="What is Lambda?", session_id="abc-123")
        assert req.session_id == "abc-123"

    def test_empty_query_raises(self):
        with pytest.raises(ValidationError):
            ChatRequest(query="")

    def test_query_too_long_raises(self):
        with pytest.raises(ValidationError):
            ChatRequest(query="x" * 2001)

    def test_max_length_query_accepted(self):
        req = ChatRequest(query="x" * 2000)
        assert len(req.query) == 2000


class TestChatResponse:
    def test_valid_response(self):
        resp = ChatResponse(
            answer="Enable bucket versioning.",
            sources=[Citation(title="S3 Guide", url="https://docs.aws.amazon.com/s3/")],
            session_id="uuid-123",
            latency_ms=450.5,
        )
        assert resp.answer == "Enable bucket versioning."
        assert len(resp.sources) == 1
        assert resp.latency_ms == 450.5

    def test_empty_sources_allowed(self):
        resp = ChatResponse(answer="Not found.", sources=[], session_id="uuid-123", latency_ms=100.0)
        assert resp.sources == []


class TestCitation:
    def test_valid(self):
        c = Citation(title="S3 Security", url="https://docs.aws.amazon.com/s3/security.html")
        assert c.title == "S3 Security"
        assert "docs.aws.amazon.com" in c.url

    def test_missing_fields_raises(self):
        with pytest.raises(ValidationError):
            Citation(title="Only title")  # type: ignore[call-arg]


class TestHealthResponse:
    def test_healthy(self):
        h = HealthResponse(status="ok", mcp_connected=True)
        assert h.status == "ok"
        assert h.mcp_connected is True

    def test_unhealthy(self):
        h = HealthResponse(status="ok", mcp_connected=False)
        assert h.mcp_connected is False


class TestNewSessionId:
    def test_generates_unique_ids(self):
        ids = {new_session_id() for _ in range(10)}
        assert len(ids) == 10  # all unique

    def test_returns_string(self):
        assert isinstance(new_session_id(), str)
