import asyncio
import logging
import time
from functools import lru_cache

import voyageai
from openai import OpenAI

from llm_lawyer.config import get_settings

logger = logging.getLogger(__name__)

# Circuit breaker: once Voyage rate-limits, skip it entirely for this long
# before retrying. Stops the log filling with one warning per embed call.
_VOYAGE_COOLDOWN_SECONDS = 300
_voyage_skip_until: float = 0.0


@lru_cache
def _voyage() -> voyageai.Client:
    s = get_settings()
    return voyageai.Client(api_key=s.voyage_api_key)


@lru_cache
def _openai() -> OpenAI:
    s = get_settings()
    return OpenAI(api_key=s.openai_api_key)


def _voyage_on_cooldown() -> bool:
    """Used by the reranker module to skip Voyage rerank when it's clearly
    rate-limited — shares the same circuit breaker window as embeddings."""
    return time.time() < _voyage_skip_until


def _trip_breaker() -> None:
    global _voyage_skip_until
    _voyage_skip_until = time.time() + _VOYAGE_COOLDOWN_SECONDS


def _embed_voyage(texts: list[str], input_type: str) -> list[list[float]]:
    s = get_settings()
    out: list[list[float]] = []
    BATCH = 64
    for i in range(0, len(texts), BATCH):
        batch = texts[i : i + BATCH]
        res = _voyage().embed(batch, model=s.voyage_model, input_type=input_type)
        out.extend(res.embeddings)
    return out


def _embed_openai(texts: list[str]) -> list[list[float]]:
    s = get_settings()
    # text-embedding-3-small supports the ``dimensions`` parameter so we can
    # match our pgvector schema (1024-dim) without a migration.
    res = _openai().embeddings.create(
        model="text-embedding-3-small",
        input=texts,
        dimensions=s.embedding_dim,
    )
    return [d.embedding for d in res.data]


def _embed_sync(texts: list[str], input_type: str) -> list[list[float]]:
    """Try Voyage first (legal-domain model). Fall back to OpenAI on rate
    limit or transport failure so the demo never stalls. After a Voyage
    failure we skip it entirely for ``_VOYAGE_COOLDOWN_SECONDS`` — avoids
    spamming the log with the same warning on every call."""
    if not texts:
        return []
    s = get_settings()
    try_voyage = bool(s.voyage_api_key) and not _voyage_on_cooldown()
    if try_voyage:
        try:
            return _embed_voyage(texts, input_type)
        except Exception as e:
            _trip_breaker()
            logger.warning(
                "Voyage embed failed (%s); using OpenAI for next %ds",
                type(e).__name__, _VOYAGE_COOLDOWN_SECONDS,
            )
    if not s.openai_api_key:
        raise RuntimeError(
            "No embedding provider available (Voyage off and no OPENAI_API_KEY)"
        )
    return _embed_openai(texts)


async def embed_documents(texts: list[str]) -> list[list[float]]:
    """Batch-embed texts for storage."""
    return await asyncio.to_thread(_embed_sync, texts, "document")


async def embed_query(text: str) -> list[float]:
    result = await asyncio.to_thread(_embed_sync, [text], "query")
    return result[0] if result else []
