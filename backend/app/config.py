"""Typed settings, loaded from environment. No secrets are hard-coded.

In Azure these come from Container Apps secrets / Key Vault references, never the
image. See deploy/azure and SECURITY.md.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: str = Field(default="dev")  # dev | staging | prod
    log_level: str = Field(default="INFO")

    # Postgres (system of record)
    database_url: str = Field(default="postgresql://maria:maria@db:5432/maria")

    # Redis (locks, idempotency, cache, and the default message bus)
    redis_url: str = Field(default="redis://redis:6379/0")

    # Message bus / store. "redis_streams" (default, MVP) or "kafka" (scale phase).
    bus_backend: str = Field(default="redis_streams")  # redis_streams | kafka
    bus_stream: str = Field(default="maria.events")    # stream / topic name
    bus_group: str = Field(default="maria.workers")    # consumer group
    kafka_bootstrap: str = Field(default="")           # only used when bus_backend=kafka

    # Qdrant (RAG)
    qdrant_url: str = Field(default="http://qdrant:6333")
    qdrant_collection: str = Field(default="maria_rag")
    embedding_dim: int = Field(default=768)            # Gemma-class embedding size
    cloud_embeddings: bool = Field(default=False)      # keep self-hosted embeddings; Tier-1 excluded from RAG

    # API auth — the mobile app sends a bearer token. Rotate via secret store.
    api_token: str = Field(default="")  # MUST be set in staging/prod

    # CORS — exact origins only; never "*" in prod.
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # Ollama Cloud (Tier 2/3 cloud LLM only — Tier 1 never leaves the device).
    # OpenAI-compatible endpoint; auth is a Bearer API key. Ollama's cloud does not
    # retain or train on prompts (privacy parity with the old data_collection:deny).
    ollama_api_key: str = Field(default="")
    ollama_base_url: str = Field(default="https://ollama.com/v1")
    # The only AI engine (the on-device/SLM path was removed). On the paid "Pro"
    # plan, gemma4:31b and additional models (deepseek, gpt-oss, ...) are available
    # behind one key with no free-tier caps. Add more ids here to enable fallback/
    # routing across cloud models.
    ollama_models: list[str] = Field(default_factory=lambda: ["gemma4:31b"])

    # External integrations (service credentials — NOT interactive MCP; see audit item #5)
    plane_base_url: str = Field(default="")
    plane_api_key: str = Field(default="")
    plane_workspace_slug: str = Field(default="")
    notion_token: str = Field(default="")

    # Langfuse (self-hosted tracing)
    langfuse_host: str = Field(default="http://langfuse:3000")
    langfuse_public_key: str = Field(default="")
    langfuse_secret_key: str = Field(default="")

    @property
    def is_prod(self) -> bool:
        return self.env.lower() in {"prod", "production", "staging"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
