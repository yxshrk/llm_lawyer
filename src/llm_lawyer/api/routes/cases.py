import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from llm_lawyer.db.models import Case, Document, Memory
from llm_lawyer.db.session import SessionDep

router = APIRouter(prefix="/cases", tags=["cases"])


class CaseIn(BaseModel):
    name: str
    client_name: str | None = None
    matter_type: str | None = None
    description: str | None = None


class CaseOut(BaseModel):
    id: uuid.UUID
    name: str
    client_name: str | None
    matter_type: str | None
    description: str | None
    document_count: int = 0
    memory_count: int = 0


class MemoryIn(BaseModel):
    kind: str
    content: str


class MemoryOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    kind: str
    content: str


@router.post("", response_model=CaseOut)
async def create_case(body: CaseIn, session: SessionDep) -> CaseOut:
    case = Case(
        name=body.name,
        client_name=body.client_name,
        matter_type=body.matter_type,
        description=body.description,
    )
    session.add(case)
    await session.commit()
    return CaseOut(
        id=case.id,
        name=case.name,
        client_name=case.client_name,
        matter_type=case.matter_type,
        description=case.description,
    )


@router.get("", response_model=list[CaseOut])
async def list_cases(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[CaseOut]:
    rows = (
        await session.execute(
            select(Case).order_by(Case.created_at.desc()).limit(limit)
        )
    ).scalars().all()
    out: list[CaseOut] = []
    for c in rows:
        doc_count = (
            await session.execute(select(Document.id).where(Document.case_id == c.id))
        ).all()
        mem_count = (
            await session.execute(select(Memory.id).where(Memory.case_id == c.id))
        ).all()
        out.append(
            CaseOut(
                id=c.id,
                name=c.name,
                client_name=c.client_name,
                matter_type=c.matter_type,
                description=c.description,
                document_count=len(doc_count),
                memory_count=len(mem_count),
            )
        )
    return out


@router.get("/{case_id}", response_model=CaseOut)
async def get_case(case_id: uuid.UUID, session: SessionDep) -> CaseOut:
    c = await session.get(Case, case_id)
    if c is None:
        raise HTTPException(404, "Case not found")
    doc_count = (
        await session.execute(select(Document.id).where(Document.case_id == c.id))
    ).all()
    mem_count = (
        await session.execute(select(Memory.id).where(Memory.case_id == c.id))
    ).all()
    return CaseOut(
        id=c.id,
        name=c.name,
        client_name=c.client_name,
        matter_type=c.matter_type,
        description=c.description,
        document_count=len(doc_count),
        memory_count=len(mem_count),
    )


@router.get("/{case_id}/memories", response_model=list[MemoryOut])
async def list_memories(case_id: uuid.UUID, session: SessionDep) -> list[MemoryOut]:
    rows = (
        await session.execute(
            select(Memory)
            .where(Memory.case_id == case_id)
            .order_by(Memory.kind, Memory.created_at)
        )
    ).scalars().all()
    return [
        MemoryOut(id=m.id, case_id=m.case_id, kind=m.kind, content=m.content)
        for m in rows
    ]


@router.post("/{case_id}/memories", response_model=MemoryOut)
async def create_memory(
    case_id: uuid.UUID, body: MemoryIn, session: SessionDep
) -> MemoryOut:
    c = await session.get(Case, case_id)
    if c is None:
        raise HTTPException(404, "Case not found")
    m = Memory(case_id=case_id, kind=body.kind, content=body.content)
    session.add(m)
    await session.commit()
    return MemoryOut(id=m.id, case_id=m.case_id, kind=m.kind, content=m.content)


@router.put("/{case_id}/memories/{memory_id}", response_model=MemoryOut)
async def update_memory(
    case_id: uuid.UUID,
    memory_id: uuid.UUID,
    body: MemoryIn,
    session: SessionDep,
) -> MemoryOut:
    m = await session.get(Memory, memory_id)
    if m is None or m.case_id != case_id:
        raise HTTPException(404, "Memory not found")
    m.kind = body.kind
    m.content = body.content
    await session.commit()
    return MemoryOut(id=m.id, case_id=m.case_id, kind=m.kind, content=m.content)


@router.delete("/{case_id}/memories/{memory_id}")
async def delete_memory(
    case_id: uuid.UUID, memory_id: uuid.UUID, session: SessionDep
) -> dict:
    m = await session.get(Memory, memory_id)
    if m is None or m.case_id != case_id:
        raise HTTPException(404, "Memory not found")
    await session.delete(m)
    await session.commit()
    return {"ok": True}


@router.get("/{case_id}/documents")
async def list_case_documents(
    case_id: uuid.UUID,
    session: SessionDep,
    production_type: Annotated[str | None, Query()] = None,
) -> list[dict]:
    stmt = (
        select(Document)
        .where(Document.case_id == case_id)
        .order_by(Document.created_at.desc())
    )
    if production_type in {"own", "opposing"}:
        stmt = stmt.where(Document.production_type == production_type)
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": str(d.id),
            "title": d.title,
            "author": d.author,
            "source_type": d.source_type,
            "production_type": d.production_type,
            "page_count": d.page_count,
            "email_id": str(d.email_id) if d.email_id else None,
            "relevancy_label": d.relevancy_label,
            "relevancy_score": d.relevancy_score,
            "relevancy_reasoning": d.relevancy_reasoning,
            "relevancy_classified_at": (
                d.relevancy_classified_at.isoformat() if d.relevancy_classified_at else None
            ),
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "last_opened_at": d.last_opened_at.isoformat() if d.last_opened_at else None,
        }
        for d in rows
    ]
