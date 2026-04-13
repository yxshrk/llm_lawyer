"""Typed application settings loaded from ``.env`` via pydantic-settings.

Single source of truth for all env-backed configuration — Supabase connection
strings, LLM provider keys + models, RAG parameters, CORS origins. Call
:func:`get_settings` anywhere in the backend; the result is memoised.
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "llm-lawyer"
    environment: Literal["dev", "staging", "prod"] = "dev"
    log_level: str = "INFO"

    # Supabase / Postgres
    supabase_url: str = Field(default="")
    supabase_key: str = Field(default="", description="Service role key")
    supabase_storage_bucket: str = Field(default="docs")
    database_url: str = Field(
        default="",
        description="Async Postgres URL, e.g. postgresql+asyncpg://...",
    )

    # LLM providers — tried in priority order, falling back on quota/auth/connection errors.
    llm_providers: list[str] = Field(
        default_factory=lambda: ["openai", "gemini", "groq"]
    )

    openai_api_key: str = Field(default="")
    openai_model: str = Field(default="gpt-5.2")

    gemini_api_key: str = Field(default="")
    gemini_model: str = Field(default="gemini-2.5-flash")

    groq_api_key: str = Field(default="")
    groq_model: str = Field(default="llama-3.3-70b-versatile")

    llm_max_output_tokens: int = 3000  # avoid mid-citation truncation in Q&A
    # Temperature per task; structured JSON tasks want low, narrative tasks higher.
    llm_temp_structured: float = 0.1
    llm_temp_narrative: float = 0.4

    voyage_api_key: str = Field(default="")
    voyage_model: str = Field(default="voyage-law-2")
    voyage_rerank_model: str = Field(default="rerank-2.5")
    embedding_dim: int = 1024

    # Web search for opposing counsel case research
    tavily_api_key: str = Field(default="")

    # Relevancy thresholds (cosine similarity-based)
    relevancy_high_threshold: float = 0.55
    relevancy_low_threshold: float = 0.30

    # RAG
    chunk_size_tokens: int = 500
    chunk_overlap_tokens: int = 50
    retrieval_top_k: int = 8

    # CORS
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
