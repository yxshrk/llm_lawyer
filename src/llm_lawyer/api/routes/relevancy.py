"""Relevancy filtering (PRD §4.4).

For each document in a case:
  1. Build a case query from the Case Context Memo (case_summary + key_legal_issues + custom_rules).
  2. Embed it once via Voyage.
  3. For each document's chunks, compute cosine similarity with pgvector.
  4. Aggregate to a doc-score (max-k mean of top chunks).
  5. Thresholds classify the doc RELEVANT / UNCERTAIN / IRRELEVANT.
  6. UNCERTAIN docs get a short LLM reasoning pass with top chunks + case memory.
  7. Persist on the document row and log to the audit trail.

Streams NDJSON so the frontend can render per-doc progress live.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llm_lawyer import audit
from llm_lawyer.config import get_settings
from llm_lawyer.db.models import Chunk, Document, Memory
from llm_lawyer.db.session import SessionLocal
from llm_lawyer.llm import client as llm_client
from llm_lawyer.llm import prompts as PROMPTS
from llm_lawyer.llm.structured import extract_json
from llm_lawyer.rag.embeddings import embed_query
from llm_lawyer.rag.reranker import rerank_texts

logger = logging.getLogger(__name__)
router = APIRouter(tags=["relevancy"])


# Which memory kinds feed the "case query" vector for relevancy. Using
# case_summary + key_legal_issues + custom_rules gives the best signal
# (ignore jurisdiction/dates since those aren't textually close to chunks).
_QUERY_KINDS = ("case_summary", "key_legal_issues", "custom_rules")


async def _build_case_query(session: AsyncSession, case_id: uuid.UUID) -> str:
    rows = (
        await session.execute(
            select(Memory).where(Memory.case_id == case_id)
        )
    ).scalars().all()
    parts: list[str] = []
    for m in rows:
        if m.kind in _QUERY_KINDS and m.content.strip():
            parts.append(m.content.strip())
    return "\n\n".join(parts) or "General case review."


def _aggregate_score(distances: list[float], top_k: int = 5) -> float:
    """Given cosine distances (lower=closer), return a 0..1 score.
    Uses mean of top-k distances → similarity."""
    if not distances:
        return 0.0
    top = sorted(distances)[:top_k]
    mean_dist = sum(top) / len(top)
    return max(0.0, min(1.0, 1.0 - mean_dist))


@router.post("/cases/{case_id}/relevancy/stream")
async def stream_relevancy(case_id: uuid.UUID):
    """Score every document in the case. Stream per-doc results."""

    async def gen():
        async with SessionLocal() as session:
            s = get_settings()
            case_query = await _build_case_query(session, case_id)
            yield json.dumps({
                "type": "started",
                "case_id": str(case_id),
                "query_preview": case_query[:160],
            }) + "\n"

            qvec = await embed_query(case_query)

            # Only classify "own" documents; opposing production is not culled
            # for relevancy (PRD §4.7 is a separate pipeline).
            docs = list(
                (
                    await session.execute(
                        select(Document)
                        .where(
                            Document.case_id == case_id,
                            Document.production_type == "own",
                        )
                        .order_by(Document.created_at.desc())
                    )
                ).scalars().all()
            )
            yield json.dumps({"type": "stage", "stage": "scoring", "doc_count": len(docs)}) + "\n"

            # Render LLM system prompt once (used only for UNCERTAIN docs).
            memory_ctx = await PROMPTS.load_memory_context(session, case_id)
            relevancy_system = PROMPTS.render(PROMPTS.RELEVANCY_SYSTEM, memory_ctx)

            for d in docs:
                # Pull distances for every chunk of this document.
                distance = Chunk.embedding.cosine_distance(qvec).label("distance")
                rows = (
                    await session.execute(
                        select(Chunk, distance)
                        .where(Chunk.document_id == d.id)
                        .order_by(distance)
                        .limit(20)
                    )
                ).all()
                if not rows:
                    yield json.dumps({
                        "type": "doc",
                        "document_id": str(d.id),
                        "title": d.title,
                        "label": "irrelevant",
                        "score": 0.0,
                        "reasoning": "No indexed content.",
                    }) + "\n"
                    continue

                distances = [float(r[1]) for r in rows]
                score = _aggregate_score(distances)

                # Rerank top candidates for a more accurate borderline score.
                top_texts = [r[0].text for r in rows[:10]]
                try:
                    reranked = await rerank_texts(
                        case_query, top_texts, get_text=lambda t: t, top_k=5
                    )
                    # top_texts is list[str]; reranked returns strings in new order.
                    top_for_llm = reranked
                except Exception:
                    top_for_llm = top_texts[:5]

                # Threshold bands.
                if score >= s.relevancy_high_threshold:
                    label = "relevant"
                    reasoning = f"High semantic alignment (mean top-k sim {score:.2f})."
                elif score < s.relevancy_low_threshold:
                    label = "irrelevant"
                    reasoning = f"Low semantic alignment (mean top-k sim {score:.2f})."
                else:
                    # UNCERTAIN — LLM pass for reasoning.
                    label = "uncertain"
                    reasoning = f"Borderline similarity {score:.2f}."
                    user_content = (
                        f"Document title: {d.title}\n"
                        f"Retrieval score (cosine): {score:.3f}\n"
                        f"Top passages:\n\n"
                        + "\n\n".join(f"— {t[:400]}" for t in top_for_llm)
                    )
                    try:
                        llm_result = await llm_client.chat_completion(
                            [
                                {"role": "system", "content": relevancy_system},
                                {"role": "user", "content": user_content},
                            ],
                            task="structured",
                            json_mode=True,
                        )
                        data = extract_json(llm_result.text) or {}
                        if isinstance(data, dict):
                            lbl = str(data.get("label", "uncertain")).lower().strip()
                            if lbl in {"relevant", "uncertain", "irrelevant"}:
                                label = lbl
                            reasoning = str(data.get("reasoning", reasoning))[:2000]
                    except Exception as e:
                        logger.warning("LLM relevancy reasoning failed: %s", e)

                d.relevancy_label = label
                d.relevancy_score = score
                d.relevancy_reasoning = reasoning
                d.relevancy_classified_at = datetime.now(timezone.utc)

                await audit.log_event(
                    session,
                    action="relevancy_classified",
                    case_id=case_id,
                    document_id=d.id,
                    actor="ai",
                    summary=f"{label} (score={score:.2f})",
                    metadata={"score": score, "label": label},
                )
                await session.commit()

                yield json.dumps({
                    "type": "doc",
                    "document_id": str(d.id),
                    "title": d.title,
                    "label": label,
                    "score": score,
                    "reasoning": reasoning,
                }) + "\n"

            yield json.dumps({"type": "done", "total": len(docs)}) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")
