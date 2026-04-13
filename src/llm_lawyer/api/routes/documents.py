import hashlib
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import select

from llm_lawyer import audit
from llm_lawyer.db.models import Chunk, Document, Email
from llm_lawyer.db.session import SessionDep
from llm_lawyer.documents import docx as docx_mod
from llm_lawyer.documents import pdf as pdf_mod
from llm_lawyer.documents import storage
from llm_lawyer.rag import chunker as chunker_mod
from llm_lawyer.rag import contextualizer as ctx_mod
from llm_lawyer.rag import embeddings as embed_mod

router = APIRouter(prefix="/documents", tags=["documents"])


class EmailPreview(BaseModel):
    """Email body inlined on the Document response when source_type='email'.
    Frontend renders this instead of a PDF viewer for virtual email docs."""
    from_addr: str | None = None
    to_addrs: str | None = None
    subject: str | None = None
    body: str | None = None
    timestamp: str | None = None


class DocumentOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID | None = None
    email_id: uuid.UUID | None = None
    title: str
    author: str | None = None
    source_type: str
    production_type: str = "own"
    storage_path: str
    mime: str | None
    page_count: int | None
    sha256: str | None
    chunk_count: int
    signed_url: str | None = None
    email: EmailPreview | None = None
    created_at: str | None = None
    last_opened_at: str | None = None


class DocumentListOut(BaseModel):
    items: list[DocumentOut]
    limit: int
    offset: int


MIME_TO_TYPE = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}


def _to_chunker_blocks(blocks) -> list[chunker_mod.ParsedBlock]:
    out = []
    for b in blocks:
        out.append(
            chunker_mod.ParsedBlock(
                page=b.page, text=b.text, bbox=getattr(b, "bbox", None)
            )
        )
    return out


@router.post("", response_model=DocumentOut)
async def upload_document(
    session: SessionDep,
    file: Annotated[UploadFile, File(...)],
    case_id: Annotated[uuid.UUID | None, Form()] = None,
    production_type: Annotated[str, Form()] = "own",
) -> DocumentOut:
    if production_type not in {"own", "opposing"}:
        production_type = "own"
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")

    mime = file.content_type or "application/octet-stream"
    source_type = MIME_TO_TYPE.get(mime)
    if source_type is None:
        # Fall back to extension sniff
        name = (file.filename or "").lower()
        if name.endswith(".pdf"):
            source_type, mime = "pdf", "application/pdf"
        elif name.endswith(".docx"):
            source_type, mime = "docx", (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
        else:
            raise HTTPException(415, f"Unsupported content-type: {mime}")

    sha = hashlib.sha256(data).hexdigest()
    doc_id = uuid.uuid4()
    filename = file.filename or f"{doc_id}.{source_type}"
    storage_path = f"{doc_id}/{filename}"

    # 1. Parse
    if source_type == "pdf":
        parsed = pdf_mod.parse_pdf(data)
        page_count = parsed.page_count
        blocks = parsed.blocks
        author = parsed.author
    else:
        parsed_docx = docx_mod.parse_docx(data)
        page_count = None
        blocks = parsed_docx.blocks
        author = parsed_docx.author

    if not blocks:
        raise HTTPException(422, "No extractable text in document")

    # 2. Chunk
    chunks = chunker_mod.chunk_blocks(_to_chunker_blocks(blocks))
    if not chunks:
        raise HTTPException(422, "Chunker produced no chunks")

    # 2b. Contextual Retrieval — one LLM call per doc generates a 1-2
    # sentence situating context per chunk. Prepended before embedding so
    # short chunks (e.g. "The package is ready") inherit the document-level
    # context (who sent it, when, why it matters). Graceful no-op on LLM
    # failure — we still embed the raw chunks and fall back to the
    # pre-contextual behaviour.
    full_doc_text = "\n\n".join(b.text for b in blocks)
    contexts = await ctx_mod.generate_contexts(
        document_title=filename,
        document_text=full_doc_text,
        chunks=[(c.ordinal, c.text) for c in chunks],
    )
    embed_inputs = ctx_mod.apply_contexts([c.text for c in chunks], contexts)

    # 3. Embed (batch) — runs in a thread so we don't block the loop.
    try:
        embeddings = await embed_mod.embed_documents(embed_inputs)
    except Exception as e:
        raise HTTPException(
            503, f"Embedding service failed: {type(e).__name__}"
        ) from e

    # 4. Upload to storage (async wrappers; ensure bucket exists first).
    await storage.ensure_bucket()
    try:
        await storage.upload_bytes(storage_path, data, mime)
    except Exception as e:
        raise HTTPException(
            503, f"Storage upload failed: {type(e).__name__}"
        ) from e

    # 5. Persist. If commit fails, roll back the storage object so we never
    # leave an orphaned blob with no DB row.
    doc = Document(
        id=doc_id,
        case_id=case_id,
        title=filename,
        author=author,
        source_type=source_type,
        production_type=production_type,
        storage_path=storage_path,
        mime=mime,
        page_count=page_count,
        sha256=sha,
    )
    session.add(doc)
    for c, emb in zip(chunks, embeddings):
        session.add(
            Chunk(
                document_id=doc_id,
                page=c.page,
                ordinal=c.ordinal,
                text=c.text,
                context=contexts.get(c.ordinal),
                bbox=c.bbox,
                embedding=emb,
                token_count=c.token_count,
            )
        )
    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        await storage.delete_object(storage_path)
        raise HTTPException(
            503, f"Database commit failed; storage rolled back: {type(e).__name__}"
        ) from e

    # Populate the BM25 tsvector column for new chunks (Postgres computes it).
    # Done after commit so the rows exist.
    from sqlalchemy import text as _sql_text
    await session.execute(
        _sql_text(
            "UPDATE chunks SET ts = "
            "setweight(to_tsvector('english', coalesce(context, '')), 'A') || "
            "setweight(to_tsvector('english', coalesce(text, '')), 'B') "
            "WHERE document_id = :did"
        ),
        {"did": str(doc_id)},
    )
    await session.commit()

    # Audit log in a separate commit — the document is now visible to the FK.
    try:
        await audit.log_event(
            session,
            action="document_uploaded",
            case_id=case_id,
            document_id=doc_id,
            summary=f"{filename} · {len(chunks)} chunks · {production_type}",
            metadata={"source_type": source_type, "sha256": sha, "production_type": production_type},
        )
        await session.commit()
    except Exception:
        await session.rollback()
        # audit is best-effort; never block an otherwise successful upload.

    return DocumentOut(
        id=doc.id,
        case_id=doc.case_id,
        email_id=doc.email_id,
        title=doc.title,
        author=doc.author,
        source_type=doc.source_type,
        production_type=doc.production_type,
        storage_path=doc.storage_path,
        mime=doc.mime,
        page_count=doc.page_count,
        sha256=doc.sha256,
        chunk_count=len(chunks),
        signed_url=storage.signed_url(storage_path),
        created_at=doc.created_at.isoformat() if doc.created_at else None,
        last_opened_at=doc.last_opened_at.isoformat() if doc.last_opened_at else None,
    )


@router.get("", response_model=DocumentListOut)
async def list_documents(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentListOut:
    stmt = (
        select(Document)
        .order_by(Document.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    docs = (await session.execute(stmt)).scalars().all()
    items: list[DocumentOut] = []
    for d in docs:
        # count chunks
        cnt = (
            await session.execute(
                select(Chunk.id).where(Chunk.document_id == d.id)
            )
        ).all()
        items.append(
            DocumentOut(
                id=d.id,
                case_id=d.case_id,
                email_id=d.email_id,
                title=d.title,
                author=d.author,
                source_type=d.source_type,
                production_type=d.production_type,
                storage_path=d.storage_path,
                mime=d.mime,
                page_count=d.page_count,
                sha256=d.sha256,
                chunk_count=len(cnt),
                created_at=d.created_at.isoformat() if d.created_at else None,
                last_opened_at=d.last_opened_at.isoformat() if d.last_opened_at else None,
            )
        )
    return DocumentListOut(items=items, limit=limit, offset=offset)


@router.delete("/{document_id}")
async def delete_document(session: SessionDep, document_id: uuid.UUID) -> dict:
    doc = await session.get(Document, document_id)
    if doc is None:
        raise HTTPException(404, "Not found")
    storage_path = doc.storage_path
    case_id = doc.case_id
    title = doc.title
    await session.delete(doc)  # cascades to chunks, memos, redactions
    await session.commit()
    # Best-effort blob cleanup — skip virtual email/ paths.
    if storage_path and not storage_path.startswith("email/"):
        try:
            await storage.delete_object(storage_path)
        except Exception:
            pass
    try:
        await audit.log_event(
            session,
            action="document_deleted",
            case_id=case_id,
            actor="lawyer",
            summary=f"deleted: {title}",
        )
        await session.commit()
    except Exception:
        await session.rollback()
    return {"ok": True, "id": str(document_id)}


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(session: SessionDep, document_id: uuid.UUID) -> DocumentOut:
    doc = await session.get(Document, document_id)
    if doc is None:
        raise HTTPException(404, "Not found")
    cnt = (
        await session.execute(
            select(Chunk.id).where(Chunk.document_id == doc.id)
        )
    ).all()
    # Update last_opened timestamp on read
    doc.last_opened_at = datetime.now(timezone.utc)
    await session.commit()

    # Email-sourced docs have a virtual storage_path with no blob. Skip
    # signed_url generation (it would fail) and attach the email body so
    # the frontend can render text directly.
    is_email = doc.source_type == "email" or (
        doc.storage_path or ""
    ).startswith("email/")
    signed = None if is_email else storage.signed_url(doc.storage_path)
    email_preview = None
    if is_email and doc.email_id:
        e = await session.get(Email, doc.email_id)
        if e is not None:
            email_preview = EmailPreview(
                from_addr=e.from_addr,
                to_addrs=e.to_addrs,
                subject=e.subject,
                body=e.body,
                timestamp=e.timestamp.isoformat() if e.timestamp else None,
            )

    return DocumentOut(
        id=doc.id,
        case_id=doc.case_id,
        email_id=doc.email_id,
        title=doc.title,
        author=doc.author,
        source_type=doc.source_type,
        production_type=doc.production_type,
        storage_path=doc.storage_path,
        mime=doc.mime,
        page_count=doc.page_count,
        sha256=doc.sha256,
        chunk_count=len(cnt),
        signed_url=signed,
        email=email_preview,
        created_at=doc.created_at.isoformat() if doc.created_at else None,
        last_opened_at=doc.last_opened_at.isoformat() if doc.last_opened_at else None,
    )
