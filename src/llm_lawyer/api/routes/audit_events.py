import csv
import io
import uuid
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from llm_lawyer.db.models import AuditEvent
from llm_lawyer.db.session import SessionDep

router = APIRouter(tags=["audit"])


class AuditOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID | None
    document_id: uuid.UUID | None
    actor: str
    action: str
    target_type: str | None
    target_id: str | None
    summary: str | None
    metadata: dict
    created_at: datetime


@router.get("/cases/{case_id}/audit", response_model=list[AuditOut])
async def list_audit(case_id: uuid.UUID, session: SessionDep) -> list[AuditOut]:
    rows = (
        await session.execute(
            select(AuditEvent)
            .where(AuditEvent.case_id == case_id)
            .order_by(AuditEvent.created_at.desc())
            .limit(500)
        )
    ).scalars().all()
    return [
        AuditOut(
            id=r.id,
            case_id=r.case_id,
            document_id=r.document_id,
            actor=r.actor,
            action=r.action,
            target_type=r.target_type,
            target_id=r.target_id,
            summary=r.summary,
            metadata=r.event_metadata,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/cases/{case_id}/audit.csv")
async def export_audit_csv(case_id: uuid.UUID, session: SessionDep):
    rows = (
        await session.execute(
            select(AuditEvent)
            .where(AuditEvent.case_id == case_id)
            .order_by(AuditEvent.created_at.asc())
        )
    ).scalars().all()

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["timestamp", "actor", "action", "target_type", "target_id", "document_id", "summary"])
    for r in rows:
        w.writerow([
            r.created_at.isoformat(),
            r.actor,
            r.action,
            r.target_type or "",
            r.target_id or "",
            str(r.document_id) if r.document_id else "",
            (r.summary or "").replace("\n", " "),
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.read()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="audit-{case_id}.csv"'},
    )
