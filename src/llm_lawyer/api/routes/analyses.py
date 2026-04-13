"""Memo + strengths/weaknesses generation.

Token-efficient map-reduce:
  - For each chunk, request a one-sentence summary (cheap).
  - Synthesise the per-chunk summaries into the final artifact in one call.
  - Case memory is injected in the synthesis step only (chunks don't need it).
"""
import json
import logging
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from llm_lawyer.db.models import Chunk, Document, DocumentAnalysis, Memo
from llm_lawyer.db.session import SessionDep, SessionLocal
from llm_lawyer.llm import client as llm_client
from llm_lawyer.llm import prompts as PROMPTS
from llm_lawyer.llm.structured import extract_json

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analyses"])


class MemoOut(BaseModel):
    document_id: uuid.UUID
    content: str
    model: str | None


class SWOut(BaseModel):
    document_id: uuid.UUID
    content: dict
    model: str | None


async def _chunk_summaries(chunks: list[Chunk]) -> list[str]:
    """One LLM call that returns a short summary per chunk. Much cheaper than
    N calls. Uses the centralised CHUNK_SUMMARISER prompt.
    """
    if not chunks:
        return []
    excerpts = "\n\n".join(f"[#{c.ordinal}] {c.text}" for c in chunks)
    result = await llm_client.chat_completion(
        [
            {"role": "system", "content": PROMPTS.CHUNK_SUMMARISER_SYSTEM},
            {
                "role": "user",
                "content": PROMPTS.render(
                    PROMPTS.CHUNK_SUMMARISER_USER, {"excerpts": excerpts}
                ),
            },
        ]
    )
    data = extract_json(result.text)
    if isinstance(data, list):
        return [str(s) for s in data]
    return [line for line in result.text.splitlines() if line.strip()][: len(chunks)]


def _bulleted(chunks: list[Chunk], summaries: list[str]) -> str:
    lines: list[str] = []
    for c, s in zip(chunks, summaries):
        page = f" p{c.page + 1}" if c.page is not None else ""
        lines.append(f"[#{c.ordinal}]{page}: {s}")
    return "\n".join(lines)


def _normalize_sw(raw) -> dict:
    """Coerce anything the LLM returns into the frontend's expected shape:
        {strengths: [{point, detail, citations, confidence}], weaknesses: [...]}
    Missing/malformed items are dropped rather than crashing the UI."""
    if not isinstance(raw, dict):
        raw = {}
    out = {"strengths": [], "weaknesses": []}
    for key in ("strengths", "weaknesses"):
        items = raw.get(key, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, str):
                out[key].append(
                    {"point": item[:120], "detail": item, "citations": [], "confidence": 0.5}
                )
                continue
            if not isinstance(item, dict):
                continue
            citations = item.get("citations", [])
            if not isinstance(citations, list):
                citations = []
            try:
                citations = [int(c) for c in citations if isinstance(c, (int, str)) and str(c).strip().isdigit()]
            except Exception:
                citations = []
            confidence = item.get("confidence")
            try:
                confidence = float(confidence) if confidence is not None else 0.5
            except Exception:
                confidence = 0.5
            out[key].append(
                {
                    "point": str(item.get("point", "")).strip() or "Untitled",
                    "detail": str(item.get("detail", "")).strip(),
                    "citations": citations,
                    "confidence": max(0.0, min(1.0, confidence)),
                }
            )
    return out


@router.post("/documents/{document_id}/memo", response_model=MemoOut)
async def generate_memo(document_id: uuid.UUID, session: SessionDep) -> MemoOut:
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

    summaries = await _chunk_summaries(chunks)
    memory_ctx = await PROMPTS.load_memory_context(session, doc.case_id)
    system_rendered = PROMPTS.render(PROMPTS.MEMO_SYSTEM, memory_ctx)

    messages: list[dict] = [
        {"role": "system", "content": system_rendered},
        {
            "role": "user",
            "content": (
                f"Document title: {doc.title}\n\n"
                f"Per-chunk summaries:\n{_bulleted(chunks, summaries)}"
            ),
        },
    ]
    try:
        result = await llm_client.chat_completion(messages)
    except Exception as e:
        raise HTTPException(
            503,
            f"Something went wrong — please try again. Your documents are safe. ({type(e).__name__})",
        ) from e

    memo = Memo(document_id=document_id, content=result.text, model=result.model)
    session.add(memo)
    await session.commit()
    return MemoOut(document_id=document_id, content=result.text, model=result.model)


@router.get("/documents/{document_id}/memo", response_model=MemoOut | None)
async def get_latest_memo(document_id: uuid.UUID, session: SessionDep):
    rows = (
        await session.execute(
            select(Memo)
            .where(Memo.document_id == document_id)
            .order_by(Memo.created_at.desc())
            .limit(1)
        )
    ).scalars().all()
    if not rows:
        return None
    m = rows[0]
    return MemoOut(document_id=m.document_id, content=m.content, model=m.model)


@router.post("/documents/{document_id}/strengths_weaknesses", response_model=SWOut)
async def generate_sw(document_id: uuid.UUID, session: SessionDep) -> SWOut:
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

    summaries = await _chunk_summaries(chunks)
    memory_ctx = await PROMPTS.load_memory_context(session, doc.case_id)
    system_rendered = PROMPTS.render(PROMPTS.STRENGTHS_WEAKNESSES_SYSTEM, memory_ctx)

    messages: list[dict] = [
        {"role": "system", "content": system_rendered},
        {
            "role": "user",
            "content": (
                f"Document title: {doc.title}\n\nPer-chunk summaries:\n"
                f"{_bulleted(chunks, summaries)}"
            ),
        },
    ]
    try:
        result = await llm_client.chat_completion(messages)
    except Exception as e:
        raise HTTPException(
            503,
            f"Something went wrong — please try again. Your documents are safe. ({type(e).__name__})",
        ) from e
    data = _normalize_sw(extract_json(result.text))

    analysis = DocumentAnalysis(
        document_id=document_id,
        kind="strengths_weaknesses",
        content=data,
        model=result.model,
    )
    session.add(analysis)
    await session.commit()
    return SWOut(document_id=document_id, content=data, model=result.model)


@router.post("/documents/{document_id}/memo/stream")
async def stream_memo(document_id: uuid.UUID):
    """NDJSON stream for memo generation. Events:
      {"type": "started", "chunk_count": int}
      {"type": "stage", "stage": "summarise_chunks" | "synthesise"}
      {"type": "chunk_summarised", "ordinal": int, "summary": str}
      {"type": "memo", "content": str, "model": str}
      {"type": "done"}
      {"type": "error", "message": str}
    """

    async def gen():
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

            yield json.dumps({"type": "started", "chunk_count": len(chunks)}) + "\n"
            yield json.dumps({"type": "stage", "stage": "summarise_chunks"}) + "\n"

            try:
                summaries = await _chunk_summaries(chunks)
            except Exception as e:
                logger.warning("chunk summarisation failed: %s", e)
                yield json.dumps({"type": "error", "message": str(e)}) + "\n"
                return

            for c, s in zip(chunks, summaries):
                yield json.dumps({
                    "type": "chunk_summarised",
                    "ordinal": c.ordinal,
                    "page": (c.page + 1) if c.page is not None else None,
                    "summary": s,
                }) + "\n"

            yield json.dumps({"type": "stage", "stage": "synthesise"}) + "\n"

            memory_ctx = await PROMPTS.load_memory_context(session, doc.case_id)
            system_rendered = PROMPTS.render(PROMPTS.MEMO_SYSTEM, memory_ctx)

            messages: list[dict] = [
                {"role": "system", "content": system_rendered},
                {
                    "role": "user",
                    "content": (
                        f"Document title: {doc.title}\n\n"
                        f"Per-chunk summaries:\n{_bulleted(chunks, summaries)}"
                    ),
                },
            ]
            try:
                result = await llm_client.chat_completion(messages)
            except Exception as e:
                logger.warning("memo synthesis failed: %s", e)
                yield json.dumps({"type": "error", "message": str(e)}) + "\n"
                return

            memo = Memo(document_id=document_id, content=result.text, model=result.model)
            session.add(memo)
            await session.commit()

            yield json.dumps({
                "type": "memo",
                "content": result.text,
                "model": result.model,
                "provider": result.provider,
            }) + "\n"
            yield json.dumps({"type": "done"}) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@router.get(
    "/documents/{document_id}/strengths_weaknesses", response_model=SWOut | None
)
async def get_latest_sw(document_id: uuid.UUID, session: SessionDep):
    rows = (
        await session.execute(
            select(DocumentAnalysis)
            .where(
                DocumentAnalysis.document_id == document_id,
                DocumentAnalysis.kind == "strengths_weaknesses",
            )
            .order_by(DocumentAnalysis.created_at.desc())
            .limit(1)
        )
    ).scalars().all()
    if not rows:
        return None
    a = rows[0]
    return SWOut(document_id=a.document_id, content=a.content, model=a.model)
