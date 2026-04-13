import hashlib
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from llm_lawyer.db.models import Case, Chunk, Document, Email
from llm_lawyer.db.session import SessionDep
from llm_lawyer.rag import chunker as chunker_mod
from llm_lawyer.rag import embeddings as embed_mod

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cases/{case_id}/emails", tags=["emails"])


class EmailIn(BaseModel):
    from_addr: str | None = None
    to_addrs: str | None = None
    subject: str | None = None
    body: str | None = None
    timestamp: datetime | None = None
    production_type: str = "own"


class AttachmentOut(BaseModel):
    id: uuid.UUID
    title: str
    source_type: str


class EmailOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    from_addr: str | None
    to_addrs: str | None
    subject: str | None
    body: str | None
    timestamp: datetime | None
    production_type: str = "own"
    created_at: datetime
    attachments: list[AttachmentOut] = []


@router.post("", response_model=EmailOut)
async def create_email(
    case_id: uuid.UUID, body: EmailIn, session: SessionDep
) -> EmailOut:
    c = await session.get(Case, case_id)
    if c is None:
        raise HTTPException(404, "Case not found")
    pt = body.production_type if body.production_type in {"own", "opposing"} else "own"
    e = Email(
        case_id=case_id,
        from_addr=body.from_addr,
        to_addrs=body.to_addrs,
        subject=body.subject,
        body=body.body,
        timestamp=body.timestamp,
        production_type=pt,
    )
    session.add(e)
    await session.flush()
    # Also materialize as a Document so this email flows into Pipeline 1+2.
    try:
        await _materialize_email_as_document(session, e)
    except Exception as ex:
        logger.warning("auto-materialize failed for new email %s: %s", e.id, ex)
    await session.commit()
    return EmailOut(
        id=e.id,
        case_id=e.case_id,
        from_addr=e.from_addr,
        to_addrs=e.to_addrs,
        subject=e.subject,
        body=e.body,
        timestamp=e.timestamp,
        production_type=e.production_type,
        created_at=e.created_at,
    )


@router.get("", response_model=list[EmailOut])
async def list_emails(
    case_id: uuid.UUID,
    session: SessionDep,
    production_type: str | None = None,
) -> list[EmailOut]:
    stmt = (
        select(Email)
        .where(Email.case_id == case_id)
        .order_by(Email.timestamp.desc().nulls_last(), Email.created_at.desc())
    )
    if production_type in {"own", "opposing"}:
        stmt = stmt.where(Email.production_type == production_type)
    rows = (await session.execute(stmt)).scalars().all()
    if not rows:
        return []

    # Single follow-up query groups attachments by email_id — replaces the
    # N+1 loop that was blowing page-load latency to several seconds.
    email_ids = [e.id for e in rows]
    atts_rows = (
        await session.execute(
            select(Document).where(Document.email_id.in_(email_ids))
        )
    ).scalars().all()
    atts_by_email: dict[uuid.UUID, list[Document]] = {}
    for a in atts_rows:
        atts_by_email.setdefault(a.email_id, []).append(a)

    return [
        EmailOut(
            id=e.id,
            case_id=e.case_id,
            from_addr=e.from_addr,
            to_addrs=e.to_addrs,
            subject=e.subject,
            body=e.body,
            timestamp=e.timestamp,
            production_type=e.production_type,
            created_at=e.created_at,
            attachments=[
                AttachmentOut(id=a.id, title=a.title, source_type=a.source_type)
                for a in atts_by_email.get(e.id, [])
            ],
        )
        for e in rows
    ]


def _email_to_text(e: Email) -> str:
    """Flatten an email into a text blob that can be chunked+embedded."""
    parts = [
        f"From: {e.from_addr or '(unknown)'}",
        f"To: {e.to_addrs or '(unknown)'}",
        f"Subject: {e.subject or '(no subject)'}",
        f"Date: {e.timestamp.isoformat() if e.timestamp else '(unknown)'}",
        "",
        (e.body or "(no body)").strip(),
    ]
    return "\n".join(parts)


async def _materialize_email_as_document(session, email: Email) -> Document | None:
    """Create a Document row backed by an email so emails flow through the
    Pipeline 1 (redaction) + Pipeline 2 (Q&A) infrastructure. Idempotent —
    if a Document already exists for this email, returns it unchanged."""
    existing = (
        await session.execute(
            select(Document).where(Document.email_id == email.id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    text = _email_to_text(email)
    if not text.strip():
        return None

    blocks = [chunker_mod.ParsedBlock(page=0, text=text, bbox=None)]
    chunks = chunker_mod.chunk_blocks(blocks)
    if not chunks:
        return None

    try:
        embeddings = await embed_mod.embed_documents([c.text for c in chunks])
    except Exception as ex:
        logger.warning("embed failed for email %s: %s", email.id, ex)
        return None

    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    title = (email.subject or "(no subject)")[:140] + f" · {email.from_addr or 'unknown'}"
    doc = Document(
        case_id=email.case_id,
        email_id=email.id,
        title=title[:512],
        source_type="email",
        production_type=email.production_type,
        storage_path=f"email/{email.id}",  # virtual path; nothing stored in blob
        mime="text/plain",
        page_count=1,
        sha256=sha,
    )
    session.add(doc)
    await session.flush()
    for c, emb in zip(chunks, embeddings):
        session.add(
            Chunk(
                document_id=doc.id,
                page=c.page,
                ordinal=c.ordinal,
                text=c.text,
                bbox=c.bbox,
                embedding=emb,
                token_count=c.token_count,
            )
        )
    return doc


@router.post("/{email_id}/materialize")
async def materialize_email(
    case_id: uuid.UUID, email_id: uuid.UUID, session: SessionDep
) -> dict:
    e = await session.get(Email, email_id)
    if e is None or e.case_id != case_id:
        raise HTTPException(404, "Email not found")
    doc = await _materialize_email_as_document(session, e)
    if doc is None:
        raise HTTPException(422, "Could not materialize — empty body")
    await session.commit()
    return {"email_id": str(email_id), "document_id": str(doc.id)}


@router.post("/materialize_all")
async def materialize_all_emails(
    case_id: uuid.UUID,
    session: SessionDep,
    production_type: str | None = None,
    limit: int = 50,
) -> dict:
    """Backfill: for every email in the case (optionally filtered by side),
    create a Document if one doesn't already exist. Returns counts.
    `limit` caps the number processed in one call to stay polite with Voyage."""
    stmt = select(Email).where(Email.case_id == case_id)
    if production_type in {"own", "opposing"}:
        stmt = stmt.where(Email.production_type == production_type)
    rows = (await session.execute(stmt.limit(limit))).scalars().all()
    created = 0
    skipped = 0
    for e in rows:
        doc = await _materialize_email_as_document(session, e)
        if doc is None:
            skipped += 1
        else:
            created += 1
    await session.commit()
    return {"processed": len(rows), "created_or_existing": created, "skipped": skipped}


@router.delete("/{email_id}")
async def delete_email(
    case_id: uuid.UUID, email_id: uuid.UUID, session: SessionDep
) -> dict:
    e = await session.get(Email, email_id)
    if e is None or e.case_id != case_id:
        raise HTTPException(404, "Email not found")
    await session.delete(e)
    await session.commit()
    return {"ok": True}
