"""Unit tests for services/mcp/schemas.py — no MCP server required."""

import pytest
from pydantic import ValidationError

from services.mcp.schemas import (
    DocumentContent,
    ReadRequest,
    SearchRequest,
    SearchResult,
)


class TestSearchResult:
    def test_required_fields(self):
        result = SearchResult(title="Amazon S3 Security", url="https://docs.aws.amazon.com/s3/")
        assert result.title == "Amazon S3 Security"
        assert result.url == "https://docs.aws.amazon.com/s3/"
        assert result.excerpt is None

    def test_optional_excerpt(self):
        result = SearchResult(
            title="VPC Guide",
            url="https://docs.aws.amazon.com/vpc/",
            excerpt="Learn how to set up a Virtual Private Cloud.",
        )
        assert result.excerpt == "Learn how to set up a Virtual Private Cloud."

    def test_missing_title_raises(self):
        with pytest.raises(ValidationError):
            SearchResult(url="https://docs.aws.amazon.com/")  # type: ignore[call-arg]

    def test_missing_url_raises(self):
        with pytest.raises(ValidationError):
            SearchResult(title="Amazon S3")  # type: ignore[call-arg]


class TestDocumentContent:
    def test_required_fields(self):
        doc = DocumentContent(
            url="https://docs.aws.amazon.com/s3/security",
            title="S3 Security Best Practices",
            content="Enable bucket versioning...",
        )
        assert doc.url == "https://docs.aws.amazon.com/s3/security"
        assert doc.sections == []

    def test_sections_populated(self):
        doc = DocumentContent(
            url="https://docs.aws.amazon.com/s3/",
            title="S3 Overview",
            content="Overview content",
            sections=["Introduction", "Buckets", "Objects"],
        )
        assert len(doc.sections) == 3

    def test_missing_required_raises(self):
        with pytest.raises(ValidationError):
            DocumentContent(url="https://docs.aws.amazon.com/", title="Only title")  # type: ignore[call-arg]


class TestSearchRequest:
    def test_defaults(self):
        req = SearchRequest(query="S3 security")
        assert req.query == "S3 security"
        assert req.limit == 10

    def test_custom_limit(self):
        req = SearchRequest(query="EC2 pricing", limit=5)
        assert req.limit == 5

    def test_empty_query_raises(self):
        with pytest.raises(ValidationError):
            SearchRequest()  # type: ignore[call-arg]


class TestReadRequest:
    def test_valid(self):
        req = ReadRequest(url="https://docs.aws.amazon.com/lambda/")
        assert req.url == "https://docs.aws.amazon.com/lambda/"

    def test_missing_url_raises(self):
        with pytest.raises(ValidationError):
            ReadRequest()  # type: ignore[call-arg]
