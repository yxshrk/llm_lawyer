import asyncio
import logging
from functools import lru_cache

import voyageai
from openai import OpenAI

from llm_lawyer.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def _voyage() -> voyageai.Client:
    s = get_settings()
    return voyageai.Client(api_key=s.voyage_api_key)


@lru_cache
def _openai() -> OpenAI:
    s = get_settings()
    return OpenAI(api_key=s.openai_api_key)


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
    """Try Voyage first (legal-domain model). Fall back to OpenAI on
    rate-limit or transport failures so the demo never stalls."""
    if not texts:
        return []
    s = get_settings()
    if s.voyage_api_key:
        try:
            return _embed_voyage(texts, input_type)
        except Exception as e:
            logger.warning(
                "Voyage embedding failed (%s: %s); falling back to OpenAI",
                type(e).__name__, str(e)[:120],
            )
    # Fallback
    if not s.openai_api_key:
        raise RuntimeError("No embedding provider available (Voyage failed and no OPENAI_API_KEY)")
    return _embed_openai(texts)


async def embed_documents(texts: list[str]) -> list[list[float]]:
    """Batch-embed texts for storage."""
    return await asyncio.to_thread(_embed_sync, texts, "document")


async def embed_query(text: str) -> list[float]:
    result = await asyncio.to_thread(_embed_sync, [text], "query")
    return result[0] if result else []
