"""Unit tests for services/vector/chunker.py — no network required."""

from services.vector.chunker import Chunk, _chunk_text, _split_into_sections, chunk_document


class TestSplitIntoSections:
    def test_no_headings(self):
        sections = _split_into_sections("just some plain text with no headings here")
        assert len(sections) == 1
        assert sections[0][0] == ""

    def test_markdown_headings(self):
        text = "## Section A\nContent A\n## Section B\nContent B"
        sections = _split_into_sections(text)
        assert len(sections) == 2
        assert sections[0][0] == "## Section A"
        assert "Content A" in sections[0][1]

    def test_empty_section_skipped(self):
        text = "## Empty\n## HasContent\nsome text here"
        sections = _split_into_sections(text)
        assert all(body.strip() for _, body in sections)


class TestChunkText:
    def test_short_text_not_split(self):
        text = "Short text."
        chunks = _chunk_text(text, max_chars=100)
        assert chunks == [text]

    def test_long_text_split(self):
        text = "word " * 2000  # well over max chars
        chunks = _chunk_text(text, max_chars=500, overlap=50)
        assert len(chunks) > 1

    def test_chunks_overlap(self):
        text = "A " * 600
        chunks = _chunk_text(text, max_chars=200, overlap=50)
        if len(chunks) > 1:
            # overlap means second chunk shares some content with end of first
            assert len(chunks[1]) > 0

    def test_empty_chunks_not_returned(self):
        chunks = _chunk_text("   \n   ", max_chars=100)
        assert all(c.strip() for c in chunks)


class TestChunkDocument:
    def test_returns_chunk_objects(self):
        content = "## Overview\nAmazon S3 is a storage service.\n## Features\nHigh durability."
        chunks = chunk_document(
            content=content,
            url="https://docs.aws.amazon.com/s3/",
            title="S3 Overview",
            service_name="s3",
            doc_hash="abc123",
        )
        assert len(chunks) >= 1
        assert all(isinstance(c, Chunk) for c in chunks)

    def test_url_propagated(self):
        chunks = chunk_document("Some content", "https://example.com", "Title", "s3")
        assert all(c.url == "https://example.com" for c in chunks)

    def test_service_name_propagated(self):
        chunks = chunk_document("Some content", "https://example.com", "Title", "lambda")
        assert all(c.service_name == "lambda" for c in chunks)

    def test_chunk_indices_sequential(self):
        content = "word " * 3000
        chunks = chunk_document(content, "https://example.com", "Title", "ec2")
        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_empty_content_returns_empty(self):
        chunks = chunk_document("", "https://example.com", "Title", "s3")
        assert chunks == []
