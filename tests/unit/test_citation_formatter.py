"""Unit tests for agents/nodes/citation_formatter.py — no LLM or MCP required."""

from agents.nodes.citation_formatter import citation_formatter_node


def _doc(url: str, title: str) -> dict:
    return {"url": url, "title": title, "content": "", "sections": []}


class TestCitationFormatter:
    def test_basic_citations(self):
        state = {
            "user_query": "test",
            "documents": [
                _doc("https://docs.aws.amazon.com/s3/security.html", "S3 Security"),
                _doc("https://docs.aws.amazon.com/iam/roles.html", "IAM Roles"),
            ],
        }
        result = citation_formatter_node(state)
        assert len(result["citations"]) == 2
        urls = [c["url"] for c in result["citations"]]
        assert "https://docs.aws.amazon.com/s3/security.html" in urls
        assert "https://docs.aws.amazon.com/iam/roles.html" in urls

    def test_deduplicates_same_url(self):
        doc = _doc("https://docs.aws.amazon.com/s3/security.html", "S3 Security")
        state = {"user_query": "test", "documents": [doc, doc]}
        result = citation_formatter_node(state)
        assert len(result["citations"]) == 1

    def test_empty_documents(self):
        state = {"user_query": "test", "documents": []}
        result = citation_formatter_node(state)
        assert result["citations"] == []

    def test_skips_docs_without_url(self):
        state = {
            "user_query": "test",
            "documents": [
                {"url": "", "title": "No URL doc", "content": "", "sections": []},
                _doc("https://docs.aws.amazon.com/s3/", "S3"),
            ],
        }
        result = citation_formatter_node(state)
        assert len(result["citations"]) == 1
        assert result["citations"][0]["url"] == "https://docs.aws.amazon.com/s3/"

    def test_title_falls_back_to_url(self):
        state = {
            "user_query": "test",
            "documents": [{"url": "https://docs.aws.amazon.com/s3/", "title": "", "content": "", "sections": []}],
        }
        result = citation_formatter_node(state)
        assert result["citations"][0]["title"] == "https://docs.aws.amazon.com/s3/"
