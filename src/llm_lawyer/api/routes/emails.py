import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from llm_lawyer.db.models import Case, Document, Email
from llm_lawyer.db.session import SessionDep

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
