"""Opposing Counsel Review pipeline (PRD §4.7).

Runs against documents labelled production_type='opposing'. Streams NDJSON so
the frontend can render redaction challenges and argument gaps as they arrive.

Events:
  {"type": "started", "doc_title": str, "chunk_count": int, "stage_plan": [...]}
  {"type": "stage", "stage": "redaction_challenges" | "gap_finder"}
  {"type": "batch_start", "batch": int, "total_batches": int}
  {"type": "challenge", "challenge": {...}}
  {"type": "gap", "gap": {...}}
  {"type": "done", "challenges": int, "gaps": int}
  {"type": "error", "message": str}
"""
import json
import logging
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from llm_lawyer import audit
from llm_lawyer.db.models import Chunk, Document, DocumentAnalysis, Memory
from llm_lawyer.db.session import SessionDep, SessionLocal
from llm_lawyer.integrations import web_search as websrch
from llm_lawyer.llm import client as llm_client
from llm_lawyer.llm import prompts as PROMPTS
from llm_lawyer.llm.structured import extract_json
from sqlalchemy import select as _sa_select

logger = logging.getLogger(__name__)
router = APIRouter(tags=["opposing"])


class OpposingReviewOut(BaseModel):
    document_id: uuid.UUID
    challenges: list[dict]
    gaps: list[dict]
    model: str | None


def _format_batch(chunks: list[Chunk]) -> str:
    lines = ["<excerpts>"]
    for c in chunks:
        page = f" page={c.page + 1}" if c.page is not None else ""
        lines.append(f"[chunk_ordinal={c.ordinal}{page}]")
        lines.append(c.text)
        lines.append("")
    lines.append("</excerpts>")
    return "\n".join(lines)


@router.post("/documents/{document_id}/opposing_review/stream")
async def stream_opposing_review(document_id: uuid.UUID, batch_size: int = 5):
    async def gen():
        async with SessionLocal() as session:
            doc = await session.get(Document, document_id)
            if doc is None:
                yield json.dumps({"type": "error", "message": "Document not found"}) + "\n"
                return
            if doc.production_type != "opposing":
                yield json.dumps({
                    "type": "error",
                    "message": "Opposing review only runs on production_type='opposing' documents",
                }) + "\n"
                return

            chunks = list(
                (
                    await session.execute(
                        select(Chunk)
                        .where(Chunk.document_id == document_id)
                        .order_by(Chunk.ordinal.asc())
                    )
                ).scalars().all()
            )
            if not chunks:
                yield json.dumps({"type": "error", "message": "No chunks"}) + "\n"
                return

            memory_ctx = await PROMPTS.load_memory_context(session, doc.case_id)
            total_batches = (len(chunks) + batch_size - 1) // batch_size
            yield json.dumps({
                "type": "started",
                "doc_title": doc.title,
                "chunk_count": len(chunks),
                "stage_plan": ["web_research", "redaction_challenges", "gap_finder"],
            }) + "\n"

            # --- Stage 0: web research ---
            yield json.dumps({"type": "stage", "stage": "web_research"}) + "\n"
            case_summary = memory_ctx.get("case_summary", "")
            legal_issues = memory_ctx.get("key_legal_issues", "")
            parties = memory_ctx.get("parties", "")
            # Build a case-aware search query.
            search_parts = [p for p in (case_summary, legal_issues, parties) if p and p != "(none)"]
            search_query = " | ".join(search_parts)[:300] or doc.title
            web_hits: list[websrch.SearchResult] = []
            if search_query.strip():
                web_hits = await websrch.web_search(search_query, max_results=5)
            for hit in web_hits:
                yield json.dumps({
                    "type": "web_result",
                    "title": hit.title,
                    "url": hit.url,
                    "score": hit.score,
                    "snippet": hit.content[:300],
                }) + "\n"
            memory_ctx["web_context"] = websrch.format_for_prompt(web_hits)

            # --- Stage 1: redaction challenges (batched) ---
            yield json.dumps({"type": "stage", "stage": "redaction_challenges"}) + "\n"
            challenge_system = PROMPTS.render(
                PROMPTS.OPPOSING_REDACTION_CHALLENGE_SYSTEM, memory_ctx
            )
            challenges: list[dict] = []

            for i in range(0, len(chunks), batch_size):
                batch = chunks[i : i + batch_size]
                batch_idx = (i // batch_size) + 1
                yield json.dumps({
                    "type": "batch_start",
                    "batch": batch_idx,
                    "total_batches": total_batches,
                }) + "\n"
                try:
                    result = await llm_client.chat_completion(
                        [
                            {"role": "system", "content": challenge_system},
                            {"role": "user", "content": _format_batch(batch)},
                        ],
                        task="structured",
                    )
                except Exception as e:
                    logger.warning("challenge batch %d failed: %s", batch_idx, e)
                    yield json.dumps({
                        "type": "batch_done",
                        "batch": batch_idx,
                        "created": 0,
                        "error": str(e),
                    }) + "\n"
                    continue

                data = extract_json(result.text) or []
                if not isinstance(data, list):
                    data = [data] if isinstance(data, dict) else []

                batch_created = 0
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    norm = {
                        "chunk_ordinal": item.get("chunk_ordinal"),
                        "redacted_passage": str(item.get("redacted_passage", "")).strip(),
                        "stated_category": str(item.get("stated_category", "unstated")).strip() or "unstated",
                        "challenge": str(item.get("challenge", "")).strip(),
                        "legal_basis": str(item.get("legal_basis", "")).strip(),
                        "strength": str(item.get("strength", "speculative")).strip().lower() or "speculative",
                        "recommended_action": str(item.get("recommended_action", "")).strip(),
                    }
                    if not norm["challenge"]:
                        continue
                    challenges.append(norm)
                    batch_created += 1
                    yield json.dumps({"type": "challenge", "challenge": norm}) + "\n"

                yield json.dumps({
                    "type": "batch_done",
                    "batch": batch_idx,
                    "created": batch_created,
                    "provider": result.provider,
                    "model": result.model,
                }) + "\n"

            # --- Stage 2: gap finder ---
            yield json.dumps({"type": "stage", "stage": "gap_finder"}) + "\n"
            gap_system = PROMPTS.render(PROMPTS.OPPOSING_GAP_FINDER_SYSTEM, memory_ctx)
            gaps: list[dict] = []
            try:
                gap_user = (
                    f"Document title: {doc.title}\n\n"
                    f"Excerpts from opposing counsel's production:\n\n"
                    + "\n\n".join(
                        f"[#{c.ordinal}] {c.text[:400]}" for c in chunks
                    )
                )
                result = await llm_client.chat_completion(
                    [
                        {"role": "system", "content": gap_system},
                        {"role": "user", "content": gap_user},
                    ],
                    task="structured",
                    json_mode=True,
                )
                data = extract_json(result.text)
                if isinstance(data, dict):
                    raw_gaps = data.get("gaps", [])
                    if isinstance(raw_gaps, list):
                        for g in raw_gaps:
                            if not isinstance(g, dict):
                                continue
                            norm = {
                                "expected_topic": str(g.get("expected_topic", "")).strip(),
                                "gap_description": str(g.get("gap_description", "")).strip(),
                                "significance": str(g.get("significance", "")).strip(),
                                "recommended_action": str(g.get("recommended_action", "")).strip(),
                            }
                            if not norm["gap_description"]:
                                continue
                            gaps.append(norm)
                            yield json.dumps({"type": "gap", "gap": norm}) + "\n"
                final_model = result.model
            except Exception as e:
                logger.warning("gap finder failed: %s", e)
                yield json.dumps({"type": "error", "message": f"gap finder: {e}"}) + "\n"
                final_model = None

            # Persist the analysis
            analysis = DocumentAnalysis(
                document_id=document_id,
                kind="opposing_review",
                content={
                    "challenges": challenges,
                    "gaps": gaps,
                    "web_sources": [
                        {"title": h.title, "url": h.url, "snippet": h.content[:300]}
                        for h in web_hits
                    ],
                },
                model=final_model,
            )
            session.add(analysis)
            await audit.log_event(
                session,
                action="opposing_review_run",
                case_id=doc.case_id,
                document_id=doc.id,
                actor="ai",
                summary=f"{len(challenges)} challenges · {len(gaps)} gaps · {len(web_hits)} web sources",
                metadata={
                    "challenges": len(challenges),
                    "gaps": len(gaps),
                    "web_sources": len(web_hits),
                    "model": final_model,
                },
            )
            await session.commit()

            yield json.dumps({
                "type": "done",
                "challenges": len(challenges),
                "gaps": len(gaps),
            }) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@router.get(
    "/documents/{document_id}/opposing_review", response_model=OpposingReviewOut | None
)
async def get_latest_opposing_review(document_id: uuid.UUID, session: SessionDep):
    rows = (
        await session.execute(
            select(DocumentAnalysis)
            .where(
                DocumentAnalysis.document_id == document_id,
                DocumentAnalysis.kind == "opposing_review",
            )
            .order_by(DocumentAnalysis.created_at.desc())
            .limit(1)
        )
    ).scalars().all()
    if not rows:
        return None
    a = rows[0]
    return OpposingReviewOut(
        document_id=a.document_id,
        challenges=a.content.get("challenges", []),
        gaps=a.content.get("gaps", []),
        model=a.model,
    )
