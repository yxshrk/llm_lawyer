"""Tavily web search — purpose-built for LLM agents.

Used in the opposing-counsel pipeline to pull public case-law, news, and
regulatory context that strengthens redaction challenges and gap arguments.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from functools import lru_cache

from llm_lawyer.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    title: str
    url: str
    content: str
    score: float


@lru_cache
def _client():
    from tavily import TavilyClient

    s = get_settings()
    if not s.tavily_api_key:
        return None
    return TavilyClient(api_key=s.tavily_api_key)


def _search_sync(query: str, max_results: int) -> list[SearchResult]:
    client = _client()
    if client is None:
        return []
    try:
        res = client.search(
            query=query,
            search_depth="advanced",
            max_results=max_results,
            include_answer=False,
            topic="general",
        )
        items = res.get("results", [])
        return [
            SearchResult(
                title=str(r.get("title", ""))[:200],
                url=str(r.get("url", "")),
                content=str(r.get("content", ""))[:1200],
                score=float(r.get("score", 0.0)),
            )
            for r in items
        ]
    except Exception as e:
        logger.warning("tavily search failed: %s", e)
        return []


async def web_search(query: str, max_results: int = 5) -> list[SearchResult]:
    return await asyncio.to_thread(_search_sync, query, max_results)


def format_for_prompt(results: list[SearchResult]) -> str:
    """Render search results as a compact block for system-prompt injection."""
    if not results:
        return "(no web results — search disabled or offline)"
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"[web-{i}] {r.title}  ({r.url})")
        if r.content:
            lines.append(r.content[:400].replace("\n", " "))
        lines.append("")
    return "\n".join(lines)
