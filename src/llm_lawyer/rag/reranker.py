"""Voyage cross-encoder reranker (``rerank-2.5``).

Re-scores (query, chunk) pairs after the initial bi-encoder retrieval; used
downstream of :func:`rag.retriever.retrieve` when ``use_reranker=True``.
Industry benchmarks report +28–48% NDCG@10 lift over dense retrieval alone.

Shares the Voyage circuit-breaker with :mod:`rag.embeddings`: once a
rate-limit or transport failure trips
:data:`rag.embeddings._voyage_skip_until`, rerank calls short-circuit to
input order (no API call, no log spam) until the cooldown expires.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TypeVar

from llm_lawyer.config import get_settings
from llm_lawyer.rag.embeddings import (
    _voyage as _voyage_client,
    _voyage_on_cooldown,
    _trip_breaker,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class RerankedItem:
    item: object
    score: float
    original_score: float


def _rerank_sync(query: str, docs: list[str]) -> list[tuple[int, float]]:
    s = get_settings()
    if not docs:
        return []
    # Share the Voyage circuit breaker with embeddings — when Voyage is
    # rate-limited, skip rerank entirely and return input order.
    if _voyage_on_cooldown():
        return [(i, 0.0) for i in range(len(docs))]
    try:
        res = _voyage_client().rerank(
            query=query,
            documents=docs,
            model=s.voyage_rerank_model,
            top_k=len(docs),
        )
        return [(r.index, float(r.relevance_score)) for r in res.results]
    except Exception as e:
        _trip_breaker()
        logger.warning(
            "rerank failed (%s); skipping for cooldown window",
            type(e).__name__,
        )
        return [(i, 0.0) for i in range(len(docs))]


async def rerank_texts(
    query: str,
    items: list[T],
    get_text,
    top_k: int | None = None,
) -> list[T]:
    """Rerank a list of items by their text. `get_text(item)` extracts the
    string the reranker scores against. Returns items ordered by relevance
    descending, truncated to top_k if provided."""
    if not items:
        return []
    texts = [get_text(i) for i in items]
    ranking = await asyncio.to_thread(_rerank_sync, query, texts)
    ordered = [items[i] for i, _score in ranking]
    return ordered[:top_k] if top_k else ordered
