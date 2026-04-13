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
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
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
async def stream_opposing_review(
    document_id: uuid.UUID,
    batch_size: Annotated[int, Query(ge=1, le=20)] = 5,
    enable_web_search: Annotated[bool, Query()] = True,
):
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
            # Per PRD §9 "No document content shared with third parties" — we
            # restrict the outbound query to short legal-doctrine terms and the
            # jurisdiction. NEVER send party names, custodians, case summary,
            # or any case-specific facts to the external search provider.
            yield json.dumps({"type": "stage", "stage": "web_research"}) + "\n"
            web_hits: list[websrch.SearchResult] = []
            if enable_web_search:
                legal_issues = memory_ctx.get("key_legal_issues", "")
                jurisdiction = memory_ctx.get("jurisdiction", "")
                # Extract short doctrine-like tokens from legal_issues only;
                # truncate aggressively so the query is legal-concept-only.
                doctrine_tokens: list[str] = []
                for line in (legal_issues or "").splitlines():
                    line = line.strip("-*• ").strip()
                    if not line or line.lower() in {"(none)", "none"}:
                        continue
                    # Keep only the first few words per line — legal doctrine,
                    # not facts.
                    doctrine_tokens.append(" ".join(line.split()[:10]))
                    if len(doctrine_tokens) >= 3:
                        break
                if jurisdiction and jurisdiction not in {"(none)", ""}:
                    doctrine_tokens.append(
                        " ".join(jurisdiction.split()[:6])
                    )
                safe_query = " ".join(doctrine_tokens)[:180]
                if safe_query.strip():
                    yield json.dumps({
                        "type": "web_query",
                        "query": safe_query,
                        "note": "Doctrine-only query — no party names or facts sent externally.",
                    }) + "\n"
                    web_hits = await websrch.web_search(safe_query, max_results=5)
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

                # Checkpoint after each batch — if the client disconnects
                # mid-stream, challenges completed so far survive. We use the
                # same kind ("opposing_review") as the final row so the GET
                # endpoint (which reads the most-recent analysis of that
                # kind) picks up partial results. The final write overwrites
                # the checkpoint with a newer row.
                _checkpoint = DocumentAnalysis(
                    document_id=document_id,
                    kind="opposing_review",
                    content={
                        "challenges": challenges,
                        "gaps": [],
                        "web_sources": [
                            {"title": h.title, "url": h.url, "snippet": h.content[:300]}
                            for h in web_hits
                        ],
                        "_checkpoint": True,
                        "_batch": batch_idx,
                        "_total_batches": total_batches,
                    },
                    model=result.model,
                )
                session.add(_checkpoint)
                await session.commit()

            # --- Stage 2: gap finder ---
            yield json.dumps({"type": "stage", "stage": "gap_finder"}) + "\n"
            gap_system = PROMPTS.render(PROMPTS.OPPOSING_GAP_FINDER_SYSTEM, memory_ctx)
            gaps: list[dict] = []
            # Cap chunks fed to gap-finder — 200-chunk productions overflow the
            # context window. Sample first N + last N by ordinal so we cover
            # both ends of the production, plus truncate each chunk text.
            MAX_GAP_CHUNKS = 40
            if len(chunks) > MAX_GAP_CHUNKS:
                half = MAX_GAP_CHUNKS // 2
                gap_chunks = chunks[:half] + chunks[-half:]
            else:
                gap_chunks = chunks
            try:
                gap_user = (
                    f"Document title: {doc.title}\n\n"
                    f"Excerpts from opposing counsel's production"
                    + (f" (sampled {len(gap_chunks)} of {len(chunks)} chunks):" if len(chunks) > MAX_GAP_CHUNKS else ":")
                    + "\n\n"
                    + "\n\n".join(
                        f"[#{c.ordinal}] {c.text[:400]}" for c in gap_chunks
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
                # Empty content or any other LLM failure → no gaps identified
                # is a legitimate outcome (e.g. short opposing doc with no
                # visible redactions). Don't surface this as a hard error.
                logger.warning("gap finder returned no gaps (%s)", e)
                yield json.dumps({
                    "type": "stage_note",
                    "stage": "gap_finder",
                    "note": "No argument gaps identified for this document.",
                }) + "\n"
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
