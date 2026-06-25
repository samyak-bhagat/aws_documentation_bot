"""Unit tests for core/config.py."""

import pytest

from core.config import Settings


class TestProductionConfigValidation:
    def test_production_requires_bedrock(self):
        settings = Settings(
            app_env="production",
            bedrock_model_id="",
            opensearch_endpoint="https://search.example.com",
            database_url="postgresql+asyncpg://u:p@localhost/db",
            jwt_secret="secure-random-secret-value-here",
        )
        with pytest.raises(ValueError, match="BEDROCK_MODEL_ID"):
            settings.validate_production_config()

    def test_production_requires_opensearch(self):
        settings = Settings(
            app_env="production",
            bedrock_model_id="anthropic.claude-3",
            opensearch_endpoint="",
            database_url="postgresql+asyncpg://u:p@localhost/db",
            jwt_secret="secure-random-secret-value-here",
        )
        with pytest.raises(ValueError, match="OPENSEARCH_ENDPOINT"):
            settings.validate_production_config()

    def test_production_rejects_default_jwt_secret(self):
        settings = Settings(
            app_env="production",
            bedrock_model_id="anthropic.claude-3",
            opensearch_endpoint="https://search.example.com",
            database_url="postgresql+asyncpg://u:p@localhost/db",
            jwt_secret="change-me-in-production",
        )
        with pytest.raises(ValueError, match="JWT_SECRET"):
            settings.validate_production_config()

    def test_production_valid_config_passes(self):
        settings = Settings(
            app_env="production",
            bedrock_model_id="anthropic.claude-3",
            opensearch_endpoint="https://search.example.com",
            database_url="postgresql+asyncpg://u:p@localhost/db",
            jwt_secret="secure-random-secret-value-here",
        )
        settings.validate_production_config()

    def test_development_skips_validation(self):
        settings = Settings(app_env="development")
        settings.validate_production_config()
