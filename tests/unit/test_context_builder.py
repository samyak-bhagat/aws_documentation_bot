"""Unit tests for agents/nodes/context_builder.py — no LLM or MCP required."""

from agents.nodes.context_builder import _MAX_TOTAL_CONTEXT, context_builder_node


def _make_doc(url: str, title: str, content: str) -> dict:
    return {"url": url, "title": title, "content": content, "sections": []}


class TestContextBuilder:
    def test_single_document(self):
        state = {
            "user_query": "S3 security",
            "documents": [
                _make_doc("https://docs.aws.amazon.com/s3/", "S3 Security", "Enable encryption.")
            ],
        }
        result = context_builder_node(state)
        assert "Enable encryption." in result["context"]
        assert "S3 Security" in result["context"]

    def test_deduplicates_same_url(self):
        doc = _make_doc("https://docs.aws.amazon.com/s3/", "S3", "Content A")
        state = {"user_query": "test", "documents": [doc, doc]}
        result = context_builder_node(state)
        # Should appear only once
        assert result["context"].count("Content A") == 1

    def test_empty_documents(self):
        state = {"user_query": "test", "documents": []}
        result = context_builder_node(state)
        assert result["context"] == ""

    def test_multiple_documents_separated(self):
        docs = [
            _make_doc("https://docs.aws.amazon.com/s3/", "S3 Guide", "S3 content"),
            _make_doc("https://docs.aws.amazon.com/ec2/", "EC2 Guide", "EC2 content"),
        ]
        state = {"user_query": "test", "documents": docs}
        result = context_builder_node(state)
        assert "S3 content" in result["context"]
        assert "EC2 content" in result["context"]
        assert "---" in result["context"]  # separator present

    def test_context_truncated_at_limit(self):
        # Each doc contributes ~3000 chars of content + ~50 chars of header.
        # Use 6 docs so their combined size (~18 300 chars) exceeds _MAX_TOTAL_CONTEXT (12 000).
        from agents.nodes.context_builder import _MAX_CONTENT_PER_DOC

        docs = [
            _make_doc(
                f"https://docs.aws.amazon.com/svc{i}/", f"Doc {i}", "y" * _MAX_CONTENT_PER_DOC
            )
            for i in range(6)
        ]
        state = {"user_query": "test", "documents": docs}
        result = context_builder_node(state)
        assert len(result["context"]) <= _MAX_TOTAL_CONTEXT + 50
        assert "[Context truncated]" in result["context"]

    def test_source_url_included(self):
        state = {
            "user_query": "test",
            "documents": [
                _make_doc("https://docs.aws.amazon.com/lambda/", "Lambda", "Lambda content")
            ],
        }
        result = context_builder_node(state)
        assert "https://docs.aws.amazon.com/lambda/" in result["context"]
