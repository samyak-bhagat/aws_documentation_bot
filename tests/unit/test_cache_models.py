"""Unit tests for services/cache/models.py and services/cache/repository (logic only)."""

from datetime import UTC

from services.cache.models import DocCache


class TestDocCacheModel:
    def test_compute_hash_deterministic(self):
        h1 = DocCache.compute_hash("same content")
        h2 = DocCache.compute_hash("same content")
        assert h1 == h2

    def test_compute_hash_different_content(self):
        h1 = DocCache.compute_hash("content A")
        h2 = DocCache.compute_hash("content B")
        assert h1 != h2

    def test_compute_hash_length(self):
        h = DocCache.compute_hash("any content")
        assert len(h) == 64  # SHA-256 hex digest


class TestDocCacheRepositoryLogic:
    """Test the is_fresh logic without a real database."""

    def test_is_fresh_within_ttl(self):
        from datetime import datetime, timedelta
        from unittest.mock import MagicMock

        from services.cache.repository import DocCacheRepository

        repo = DocCacheRepository(MagicMock())
        entry = MagicMock()
        entry.last_fetched = datetime.now(UTC) - timedelta(hours=1)
        assert repo.is_fresh(entry) is True

    def test_is_stale_beyond_ttl(self):
        from datetime import datetime, timedelta
        from unittest.mock import MagicMock

        from services.cache.repository import DocCacheRepository

        repo = DocCacheRepository(MagicMock())
        entry = MagicMock()
        entry.last_fetched = datetime.now(UTC) - timedelta(hours=25)
        assert repo.is_fresh(entry) is False
