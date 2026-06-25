"""Unit tests for the RRF logic in services/vector/retriever.py — no network required."""

from services.vector.retriever import RankedChunk, reciprocal_rank_fusion


def _chunk(url: str, section: str = "", text: str = "t", score: float = 1.0) -> RankedChunk:
    return RankedChunk(
        url=url, title="", section=section, service_name="s3", chunk_text=text, score=score
    )


class TestReciprocalRankFusion:
    def test_single_list_preserved(self):
        items = [_chunk("https://a.com"), _chunk("https://b.com")]
        fused = reciprocal_rank_fusion(items)
        assert len(fused) == 2

    def test_higher_ranked_item_wins(self):
        list_a = [_chunk("https://best.com"), _chunk("https://second.com")]
        list_b = [_chunk("https://best.com"), _chunk("https://other.com")]
        fused = reciprocal_rank_fusion(list_a, list_b)
        # "best.com" appears first in both lists → should have highest RRF score
        assert fused[0].url == "https://best.com"

    def test_deduplication(self):
        same = _chunk("https://dup.com")
        fused = reciprocal_rank_fusion([same, same], [same])
        urls = [c.url for c in fused]
        assert urls.count("https://dup.com") == 1

    def test_empty_lists(self):
        fused = reciprocal_rank_fusion([], [])
        assert fused == []

    def test_scores_are_positive(self):
        items = [_chunk(f"https://doc{i}.com") for i in range(5)]
        fused = reciprocal_rank_fusion(items)
        assert all(c.score > 0 for c in fused)

    def test_descending_score_order(self):
        list_a = [_chunk(f"https://doc{i}.com") for i in range(5)]
        list_b = [_chunk(f"https://doc{i}.com") for i in range(5)]
        fused = reciprocal_rank_fusion(list_a, list_b)
        scores = [c.score for c in fused]
        assert scores == sorted(scores, reverse=True)
