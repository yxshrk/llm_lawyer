"""Redaction suggestion pipeline.

For each document:
  1. Load chunks + case memory.
  2. Batch chunks (small groups) and ask the LLM to return structured JSON:
     [{chunk_ordinal, span, label, confidence, reasoning}, ...]
  3. Persist as `redactions` rows with status='pending'.
  4. Attorney reviews via PATCH /redactions/{id}.
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete, select

from llm_lawyer import audit
from llm_lawyer.db.models import Chunk, Document, Redaction
from llm_lawyer.db.session import SessionLocal, SessionDep
from llm_lawyer.llm import client as llm_client
from llm_lawyer.llm import prompts as PROMPTS
from llm_lawyer.llm.structured import extract_json

logger = logging.getLogger(__name__)

router = APIRouter(tags=["redactions"])


class RunResponse(BaseModel):
    document_id: uuid.UUID
    created: int
    provider: str | None = None
    model: str | None = None


class RedactionOut(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    chunk_id: uuid.UUID | None
    page: int | None
    bbox: list[float] | None
    text_span: str
    label: str
    confidence: float | None
    reasoning: str | None
    status: str


class ReviewIn(BaseModel):
    status: str  # accepted | rejected | modified
    modified_span: str | None = None


def _redaction_to_dict(r: Redaction) -> dict:
    return {
        "id": str(r.id),
        "document_id": str(r.document_id),
        "chunk_id": str(r.chunk_id) if r.chunk_id else None,
        "page": r.page,
        "bbox": r.bbox,
        "text_span": r.text_span,
        "label": r.label,
        "confidence": r.confidence,
        "reasoning": r.reasoning,
        "status": r.status,
    }


def _format_batch(chunks: list[Chunk]) -> str:
    lines = ["<excerpts>"]
    for c in chunks:
        page = f" page={c.page}" if c.page is not None else ""
        lines.append(f"[chunk_ordinal={c.ordinal}{page}]")
        lines.append(c.text)
        lines.append("")
    lines.append("</excerpts>")
    return "\n".join(lines)


@router.post("/documents/{document_id}/redactions/run", response_model=RunResponse)
async def run_redactions(
    document_id: uuid.UUID,
    session: SessionDep,
    batch_size: Annotated[int, Query(ge=1, le=20)] = 5,
    replace: bool = True,
) -> RunResponse:
    doc = await session.get(Document, document_id)
    if doc is None:
        raise HTTPException(404, "Document not found")

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
        raise HTTPException(422, "Document has no chunks")

    if replace:
        await session.execute(
            delete(Redaction).where(
                Redaction.document_id == document_id,
                Redaction.status == "pending",
            )
        )

    memory_ctx = await PROMPTS.load_memory_context(session, doc.case_id)
    system_rendered = PROMPTS.render(PROMPTS.REDACTION_SYSTEM, memory_ctx)
    by_ordinal = {c.ordinal: c for c in chunks}

    created = 0
    last_provider: str | None = None
    last_model: str | None = None

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        messages: list[dict] = [
            {"role": "system", "content": system_rendered},
            {"role": "user", "content": _format_batch(batch)},
        ]

        try:
            result = await llm_client.chat_completion(messages)
        except Exception as e:
            logger.warning("redaction batch failed: %s", e)
            continue
        last_provider = result.provider
        last_model = result.model

        data = extract_json(result.text) or []
        if not isinstance(data, list):
            data = [data] if isinstance(data, dict) else []

        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                ordinal = int(item.get("chunk_ordinal"))
                span = str(item.get("span", "")).strip()
                label = str(item.get("label", "OTHER")).strip()[:64] or "OTHER"
                confidence = item.get("confidence")
                reasoning = item.get("reasoning")
            except Exception:
                continue
            if not span:
                continue
            chunk = by_ordinal.get(ordinal)
            if chunk is None:
                continue
            session.add(
                Redaction(
                    document_id=document_id,
                    chunk_id=chunk.id,
                    page=chunk.page,
                    bbox=chunk.bbox,
                    text_span=span,
                    label=label,
                    confidence=(
                        float(confidence) if isinstance(confidence, (int, float)) else None
                    ),
                    reasoning=str(reasoning) if reasoning is not None else None,
                )
            )
            created += 1

    await session.commit()
    return RunResponse(
        document_id=document_id, created=created, provider=last_provider, model=last_model
    )


@router.get("/documents/{document_id}/redactions", response_model=list[RedactionOut])
async def list_redactions(
    document_id: uuid.UUID, session: SessionDep
) -> list[RedactionOut]:
    rows = (
        await session.execute(
            select(Redaction)
            .where(Redaction.document_id == document_id)
            .order_by(Redaction.page.asc().nulls_last(), Redaction.created_at.asc())
        )
    ).scalars().all()
    return [
        RedactionOut(
            id=r.id,
            document_id=r.document_id,
            chunk_id=r.chunk_id,
            page=r.page,
            bbox=r.bbox,
            text_span=r.text_span,
            label=r.label,
            confidence=r.confidence,
            reasoning=r.reasoning,
            status=r.status,
        )
        for r in rows
    ]


@router.post("/documents/{document_id}/redactions/stream")
async def stream_redactions(
    document_id: uuid.UUID,
    batch_size: Annotated[int, Query(ge=1, le=20)] = 5,
    replace: bool = True,
):
    """NDJSON stream of redaction progress. Each line is a JSON event:
      {"type": "started", "total_batches": int, "chunk_count": int}
      {"type": "batch_start", "batch": int, "total_batches": int}
      {"type": "batch_done", "batch": int, "created": int, "provider": str}
      {"type": "redaction", "redaction": {...}}
      {"type": "done", "total": int}
      {"type": "error", "message": str}
    """

    async def gen():
        # Use a dedicated session so we can stream across awaits.
        async with SessionLocal() as session:
            doc = await session.get(Document, document_id)
            if doc is None:
                yield json.dumps({"type": "error", "message": "Document not found"}) + "\n"
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

            if replace:
                await session.execute(
                    delete(Redaction).where(
                        Redaction.document_id == document_id,
                        Redaction.status == "pending",
                    )
                )
                await session.commit()

            memory_ctx = await PROMPTS.load_memory_context(session, doc.case_id)
            system_rendered = PROMPTS.render(PROMPTS.REDACTION_SYSTEM, memory_ctx)
            by_ordinal = {c.ordinal: c for c in chunks}

            total_batches = (len(chunks) + batch_size - 1) // batch_size
            yield json.dumps({
                "type": "started",
                "total_batches": total_batches,
                "chunk_count": len(chunks),
            }) + "\n"

            total_created = 0
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
                            {"role": "system", "content": system_rendered},
                            {"role": "user", "content": _format_batch(batch)},
                        ],
                        task="structured",
                    )
                except Exception as e:
                    logger.warning("batch %d failed: %s", batch_idx, e)
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
                    try:
                        ordinal = int(item.get("chunk_ordinal"))
                        span = str(item.get("span", "")).strip()
                        label = str(item.get("label", "OTHER")).strip()[:64] or "OTHER"
                        confidence = item.get("confidence")
                        reasoning = item.get("reasoning")
                    except Exception:
                        continue
                    if not span:
                        continue
                    chunk = by_ordinal.get(ordinal)
                    if chunk is None:
                        continue
                    # Span verification — reject hallucinated spans that
                    # don't appear in the chunk text. Try exact and
                    # whitespace-normalised match.
                    chunk_text = chunk.text
                    norm_chunk = " ".join(chunk_text.split())
                    norm_span = " ".join(span.split())
                    if span not in chunk_text and norm_span not in norm_chunk:
                        logger.warning(
                            "span verification failed: %r not in chunk %s",
                            span[:80], chunk.id,
                        )
                        continue
                    red = Redaction(
                        document_id=document_id,
                        chunk_id=chunk.id,
                        page=chunk.page,
                        bbox=chunk.bbox,
                        text_span=span,
                        label=label,
                        confidence=(
                            float(confidence) if isinstance(confidence, (int, float)) else None
                        ),
                        reasoning=str(reasoning) if reasoning is not None else None,
                    )
                    session.add(red)
                    await session.flush()  # assign id
                    yield json.dumps({
                        "type": "redaction",
                        "redaction": _redaction_to_dict(red),
                    }) + "\n"
                    batch_created += 1
                    total_created += 1

                await session.commit()
                yield json.dumps({
                    "type": "batch_done",
                    "batch": batch_idx,
                    "created": batch_created,
                    "provider": result.provider,
                    "model": result.model,
                }) + "\n"

            yield json.dumps({"type": "done", "total": total_created}) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@router.patch("/redactions/{redaction_id}", response_model=RedactionOut)
async def review_redaction(
    redaction_id: uuid.UUID, body: ReviewIn, session: SessionDep
) -> RedactionOut:
    r = await session.get(Redaction, redaction_id)
    if r is None:
        raise HTTPException(404, "Redaction not found")
    if body.status not in {"pending", "accepted", "rejected", "modified"}:
        raise HTTPException(400, f"Invalid status: {body.status}")
    r.status = body.status
    if body.modified_span is not None:
        r.modified_span = body.modified_span
    r.reviewed_at = datetime.now(timezone.utc)
    # Fetch document for case_id
    doc = await session.get(Document, r.document_id)
    await audit.log_event(
        session,
        action=f"redaction_{body.status}",
        case_id=doc.case_id if doc else None,
        document_id=r.document_id,
        actor="lawyer",
        target_type="redaction",
        target_id=str(r.id),
        summary=f"[{r.label}] {r.text_span[:80]}",
        metadata={"confidence": r.confidence, "label": r.label},
    )
    await session.commit()
    return RedactionOut(
        id=r.id,
        document_id=r.document_id,
        chunk_id=r.chunk_id,
        page=r.page,
        bbox=r.bbox,
        text_span=r.text_span,
        label=r.label,
        confidence=r.confidence,
        reasoning=r.reasoning,
        status=r.status,
    )
