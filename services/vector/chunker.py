"""Section-based document chunker — Phase 7.

Splits a document into overlapping chunks of ≤1000 tokens,
respecting section (heading) boundaries where possible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_MAX_CHUNK_TOKENS = 1000
_OVERLAP_TOKENS = 150
# Rough characters-per-token ratio for English text (conservative)
_CHARS_PER_TOKEN = 4

_MAX_CHUNK_CHARS = _MAX_CHUNK_TOKENS * _CHARS_PER_TOKEN  # 4000
_OVERLAP_CHARS = _OVERLAP_TOKENS * _CHARS_PER_TOKEN  # 600

# Headings: Markdown ## / ### or ALL-CAPS lines ≥ 4 chars
_HEADING_RE = re.compile(r"^(#{1,4}\s.+|[A-Z][A-Z\s]{3,})$", re.MULTILINE)


@dataclass
class Chunk:
    text: str
    section: str
    url: str
    title: str
    service_name: str
    hash: str = ""
    chunk_index: int = 0
    metadata: dict = field(default_factory=dict)


def _split_into_sections(text: str) -> list[tuple[str, str]]:
    """Return a list of (heading, body) pairs split at markdown headings."""
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return [("", text)]

    sections: list[tuple[str, str]] = []
    for i, match in enumerate(matches):
        heading = match.group().strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            sections.append((heading, body))
    return sections or [("", text)]


def _chunk_text(
    text: str, max_chars: int = _MAX_CHUNK_CHARS, overlap: int = _OVERLAP_CHARS
) -> list[str]:
    """Split text into overlapping chunks by character count."""
    if not text.strip():
        return []
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + max_chars
        chunk = text[start:end]
        # Try to break at a sentence boundary
        last_period = chunk.rfind(". ")
        if last_period > max_chars // 2:
            end = start + last_period + 1
            chunk = text[start:end]
        chunks.append(chunk.strip())
        start = end - overlap
        if start >= len(text):
            break

    return [c for c in chunks if c]


def chunk_document(
    content: str,
    url: str,
    title: str,
    service_name: str,
    doc_hash: str = "",
) -> list[Chunk]:
    """Chunk a full document into overlapping section-aware pieces."""
    sections = _split_into_sections(content)
    chunks: list[Chunk] = []
    idx = 0

    for heading, body in sections:
        for piece in _chunk_text(body):
            chunks.append(
                Chunk(
                    text=piece,
                    section=heading,
                    url=url,
                    title=title,
                    service_name=service_name,
                    hash=doc_hash,
                    chunk_index=idx,
                )
            )
            idx += 1

    return chunks
