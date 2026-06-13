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

    # Redis (queues, locks, idempotency)
    redis_url: str = Field(default="redis://redis:6379/0")

    # Qdrant (RAG)
    qdrant_url: str = Field(default="http://qdrant:6333")
    qdrant_collection: str = Field(default="maria_rag")

    # API auth — the mobile app sends a bearer token. Rotate via secret store.
    api_token: str = Field(default="")  # MUST be set in staging/prod

    # CORS — exact origins only; never "*" in prod.
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # OpenRouter (Tier 2/3 cloud LLM only — Tier 1 never leaves the device)
    openrouter_api_key: str = Field(default="")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1")
    openrouter_models: list[str] = Field(
        default_factory=lambda: ["google/gemma-4-31b:free", "google/gemma-4-26b-a4b:free"]
    )

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
