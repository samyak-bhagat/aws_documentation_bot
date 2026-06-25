import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # OpenAI (local dev)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # AWS / Bedrock (production)
    aws_region: str = "us-east-1"
    bedrock_model_id: str = ""
    bedrock_embed_model_id: str = "amazon.titan-embed-text-v2:0"

    # MCP Server
    mcp_server_command: str = "uvx"
    mcp_server_args: str = "awslabs.aws-documentation-mcp-server@latest"

    # PostgreSQL (Phase 5+)
    database_url: str = ""

    # Qdrant (local dev)
    qdrant_url: str = ""
    qdrant_collection: str = "aws_docs"

    # OpenSearch (AWS)
    opensearch_endpoint: str = ""
    opensearch_index: str = "aws_docs"
    opensearch_username: str = ""
    opensearch_password: str = ""

    # Auth (Phase 8+)
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # Cache
    doc_cache_ttl_hours: int = 24
    max_context_messages: int = 10

    # Rate limiting (Phase 8+)
    rate_limit_per_minute: int = 20

    @property
    def use_bedrock(self) -> bool:
        return bool(self.bedrock_model_id)

    @property
    def use_opensearch(self) -> bool:
        return bool(self.opensearch_endpoint)

    @property
    def use_qdrant(self) -> bool:
        return bool(self.qdrant_url) and not self.use_opensearch

    @property
    def vector_search_enabled(self) -> bool:
        return self.use_opensearch or self.use_qdrant

    @property
    def mcp_server_command_resolved(self) -> str:
        """Return the absolute path to the MCP server command, venv-aware."""
        return _resolve_command(self.mcp_server_command)

    @property
    def mcp_server_args_list(self) -> list[str]:
        """Split MCP_SERVER_ARGS into a list for subprocess."""
        return self.mcp_server_args.split()


settings = Settings()
