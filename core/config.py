import sys
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_JWT_SECRET = "change-me-in-production"


def _resolve_command(cmd: str) -> str:
    """If `cmd` is a bare executable name, look it up inside the active venv first."""
    if Path(cmd).is_absolute():
        return cmd
    scripts_dir = Path(sys.prefix) / ("Scripts" if sys.platform == "win32" else "bin")
    candidate = scripts_dir / (cmd + (".exe" if sys.platform == "win32" else ""))
    if candidate.exists():
        return str(candidate)
    return cmd


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "production"

    # AWS / Bedrock
    aws_region: str = "us-east-1"
    bedrock_model_id: str = ""
    bedrock_embed_model_id: str = "amazon.titan-embed-text-v2:0"

    # MCP Server
    mcp_server_command: str = "uvx"
    mcp_server_args: str = "awslabs.aws-documentation-mcp-server@latest"

    # PostgreSQL
    database_url: str = ""

    # OpenSearch
    opensearch_endpoint: str = ""
    opensearch_index: str = "aws_docs"
    opensearch_username: str = ""
    opensearch_password: str = ""

    # Auth
    jwt_secret: str = _DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # Cache
    doc_cache_ttl_hours: int = 24
    max_context_messages: int = 10

    # Rate limiting
    rate_limit_per_minute: int = 20

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env.lower() == "development"

    @property
    def vector_search_enabled(self) -> bool:
        return bool(self.opensearch_endpoint)

    @property
    def mcp_server_command_resolved(self) -> str:
        return _resolve_command(self.mcp_server_command)

    @property
    def mcp_server_args_list(self) -> list[str]:
        return self.mcp_server_args.split()

    def validate_production_config(self) -> None:
        """Raise ValueError when required production settings are missing or insecure."""
        if not self.is_production:
            return

        missing: list[str] = []
        if not self.bedrock_model_id:
            missing.append("BEDROCK_MODEL_ID")
        if not self.bedrock_embed_model_id:
            missing.append("BEDROCK_EMBED_MODEL_ID")
        if not self.opensearch_endpoint:
            missing.append("OPENSEARCH_ENDPOINT")
        if not self.database_url:
            missing.append("DATABASE_URL")
        if missing:
            raise ValueError(
                f"Missing required configuration for APP_ENV=production: {', '.join(missing)}"
            )
        if self.jwt_secret == _DEFAULT_JWT_SECRET:
            raise ValueError("JWT_SECRET must be changed from the default value in production")

    @model_validator(mode="after")
    def _warn_development_defaults(self) -> "Settings":
        if self.is_development:
            return self
        return self


settings = Settings()
