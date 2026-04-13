"""Pipeline 2 — Q&A Challenge Set (PRD §6).

The attorney has finished approving redactions; now we stress-test every
accepted one with an adversarial question ("judge or opposing counsel").
Also runs a consistency check — embeds all accepted spans and flags pairs
that are semantically similar but treated differently, as a priority
challenge at the top of the set.

Iterative: re-running replaces the PRIOR run_id's rows. Lawyer status
decisions on prior rows survive in the audit trail only; the frontend
surfaces the newest run_id.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from llm_lawyer import audit
from llm_lawyer.db.models import Case, Redaction, RedactionChallenge
from llm_lawyer.db.session import SessionDep, SessionLocal
from llm_lawyer.llm import client as llm_client
from llm_lawyer.llm import prompts as PROMPTS
from llm_lawyer.llm.structured import extract_json
from llm_lawyer.rag.embeddings import embed_documents

logger = logging.getLogger(__name__)
router = APIRouter(tags=["qa"])


class ChallengeOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    redaction_id: uuid.UUID
    run_id: uuid.UUID
    challenge_question: str
    suggested_answer: str | None
    legal_basis: str | None
    risk_flag: str | None
    difficulty: str
    inconsistency_peer_id: uuid.UUID | None
    lawyer_status: str
    lawyer_notes: str | None
    # Embed a lightweight redaction view so the frontend can render the card
    redaction: dict | None = None


class ReviewIn(BaseModel):
    lawyer_status: str  # prepared | needs_work | will_revise | pending
    lawyer_notes: str | None = None


def _confidence_band(c: float | None) -> str:
    if c is None:
        return "Medium"
    if c >= 0.85:
        return "High"
    if c >= 0.6:
        return "Medium"
    return "Low"


def _difficulty_note(difficulty: str) -> str:
    if difficulty == "priority_inconsistency":
        return (
            "PRIORITY — this redaction conflicts with another similar redaction "
            "in the set. The adversary's first line of attack will be: "
            "'You redacted this but not that — why?'"
        )
    if difficulty == "hard_low_confidence":
        return (
            "HARD MODE — the AI flagged this redaction at LOW confidence. "
            "Ask the most aggressive, most destabilising question you can. "
            "Assume opposing counsel smells blood."
        )
    return "Standard — challenge this as any competent judge would."


def _format_redaction_block(r: Redaction, confidence_band: str, peer: Redaction | None) -> str:
    lines = [
        f"<redaction>",
        f"redaction_id: {r.id}",
        f"category_label: {r.label}",
        f"confidence: {confidence_band}" + (f" ({r.confidence:.2f})" if r.confidence is not None else ""),
        f"page: {(r.page + 1) if r.page is not None else 'n/a'}",
        f"redacted_passage: {r.text_span!r}",
        f"original_reasoning: {r.reasoning or '(not provided)'}",
    ]
    if peer is not None:
        lines.append(
            f"inconsistency_note: A semantically similar passage "
            f"({peer.text_span!r}, status={peer.status}, label={peer.label}) "
            f"exists in the production. Explain the differential treatment."
        )
    lines.append("</redaction>")
    return "\n".join(lines)


def _cosine(a: list[float], b: list[float]) -> float:
    # Quick pure-Python cosine; list length is small.
    import math
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


async def _detect_inconsistencies(
    accepted: list[Redaction],
) -> dict[uuid.UUID, uuid.UUID]:
    """Embed all accepted redaction spans and flag pairs with high similarity
    but differential treatment (different labels, or one accepted and a
    similar one rejected). Returns {redaction_id: peer_id}."""
    if len(accepted) < 2:
        return {}
    spans = [r.text_span[:500] for r in accepted]
    try:
        vectors = await embed_documents(spans)
    except Exception as e:
        logger.warning("inconsistency embedding failed: %s", e)
        return {}
    out: dict[uuid.UUID, uuid.UUID] = {}
    for i, ri in enumerate(accepted):
        for j, rj in enumerate(accepted):
            if i >= j:
                continue
            sim = _cosine(vectors[i], vectors[j])
            # High similarity but different labels = priority inconsistency
            if sim >= 0.88 and ri.label != rj.label:
                out.setdefault(ri.id, rj.id)
                out.setdefault(rj.id, ri.id)
    return out


@router.post("/cases/{case_id}/qa/run")
async def run_qa(case_id: uuid.UUID):
    """Stream NDJSON Q&A events per PRD §6.

    Events:
      {"type": "started", "total": N}
      {"type": "inconsistency_scan", "pairs": K}
      {"type": "challenge", "challenge": {...}}
      {"type": "done", "total": N, "run_id": uuid}
      {"type": "error", "message": str}
    """

    async def gen():
        async with SessionLocal() as session:
            case = await session.get(Case, case_id)
            if case is None:
                yield json.dumps({"type": "error", "message": "Case not found"}) + "\n"
                return

            # Only challenge our-side redactions; opposing-counsel docs have
            # their own pipeline and must never be Q&A'd as ours.
            from llm_lawyer.db.models import Document
            stmt = (
                select(Redaction)
                .join(Document, Document.id == Redaction.document_id)
                .where(
                    Document.case_id == case_id,
                    Document.production_type == "own",
                    Redaction.status.in_(["accepted", "modified"]),
                )
                .order_by(Redaction.confidence.asc().nulls_last())
            )
            accepted = list((await session.execute(stmt)).scalars().all())

            if not accepted:
                yield json.dumps({
                    "type": "error",
                    "message": "No finalised redactions found. Please complete your redaction review before generating challenge questions.",
                }) + "\n"
                return

            yield json.dumps({"type": "started", "total": len(accepted)}) + "\n"

            # Consistency scan
            yield json.dumps({"type": "stage", "stage": "inconsistency_scan"}) + "\n"
            peers = await _detect_inconsistencies(accepted)
            peer_lookup = {r.id: r for r in accepted}
            yield json.dumps({
                "type": "inconsistency_scan",
                "pairs": sum(1 for _ in peers) // 2,
            }) + "\n"

            # Generate into a fresh run_id WITHOUT deleting the prior run.
            # If the LLM fails for every redaction, the lawyer's previous
            # work (including lawyer_status decisions) is preserved. The
            # list endpoint already returns only the latest run_id, and we
            # prune the old run at the end of a successful generation.
            run_id = uuid.uuid4()
            memory_ctx = await PROMPTS.load_memory_context(session, case_id)

            yield json.dumps({"type": "stage", "stage": "generate_challenges"}) + "\n"

            # Sort: priority inconsistencies first, then low-confidence, then the rest
            def _prio(r: Redaction) -> tuple[int, float]:
                if r.id in peers:
                    return (0, r.confidence or 0.0)
                if (r.confidence or 1.0) < 0.6:
                    return (1, r.confidence or 0.0)
                return (2, r.confidence or 0.0)

            accepted.sort(key=_prio)

            created = 0
            for r in accepted:
                peer = peer_lookup.get(peers.get(r.id)) if r.id in peers else None
                if r.id in peers:
                    difficulty = "priority_inconsistency"
                elif (r.confidence or 1.0) < 0.6:
                    difficulty = "hard_low_confidence"
                else:
                    difficulty = "standard"

                ctx = dict(memory_ctx)
                ctx["difficulty_note"] = _difficulty_note(difficulty)
                system = PROMPTS.render(PROMPTS.QA_CHALLENGE_SYSTEM, ctx)
                user_body = _format_redaction_block(
                    r, _confidence_band(r.confidence), peer
                )
                try:
                    result = await llm_client.chat_completion(
                        [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user_body},
                        ],
                        task="structured",
                        json_mode=True,
                    )
                except Exception as e:
                    logger.warning("qa generation failed for %s: %s", r.id, e)
                    yield json.dumps({
                        "type": "error",
                        "message": f"Challenge gen failed for redaction {r.id}: {type(e).__name__}",
                    }) + "\n"
                    continue

                data = extract_json(result.text)
                if not isinstance(data, dict):
                    continue
                # Strip backslash-escapes the LLM sometimes emits
                def _clean(s: str | None) -> str | None:
                    if s is None:
                        return None
                    return str(s).replace("\\*", "*").replace("\\_", "_").strip() or None

                question = _clean(data.get("challenge_question"))
                if not question:
                    continue

                challenge = RedactionChallenge(
                    case_id=case_id,
                    redaction_id=r.id,
                    run_id=run_id,
                    challenge_question=question,
                    suggested_answer=_clean(data.get("suggested_answer")),
                    legal_basis=_clean(data.get("legal_basis")),
                    risk_flag=_clean(data.get("risk_flag")),
                    difficulty=difficulty,
                    inconsistency_peer_id=peers.get(r.id),
                )
                session.add(challenge)
                await session.flush()
                await session.commit()
                created += 1

                yield json.dumps({
                    "type": "challenge",
                    "challenge": {
                        "id": str(challenge.id),
                        "redaction_id": str(r.id),
                        "run_id": str(run_id),
                        "challenge_question": challenge.challenge_question,
                        "suggested_answer": challenge.suggested_answer,
                        "legal_basis": challenge.legal_basis,
                        "risk_flag": challenge.risk_flag,
                        "difficulty": difficulty,
                        "inconsistency_peer_id": str(peers[r.id]) if r.id in peers else None,
                        "lawyer_status": "pending",
                        "redaction": {
                            "id": str(r.id),
                            "label": r.label,
                            "confidence": r.confidence,
                            "confidence_band": _confidence_band(r.confidence),
                            "text_span": r.text_span,
                            "page": r.page,
                            "document_id": str(r.document_id),
                        },
                    },
                }) + "\n"

            # Prune older runs only after the new run produced at least one
            # challenge — preserves prior lawyer decisions on LLM outage.
            if created > 0:
                from sqlalchemy import delete as _delete
                await session.execute(
                    _delete(RedactionChallenge).where(
                        RedactionChallenge.case_id == case_id,
                        RedactionChallenge.run_id != run_id,
                    )
                )

            # Audit log
            await audit.log_event(
                session,
                action="qa_run",
                case_id=case_id,
                actor="ai",
                summary=f"Generated {created} challenges across {len(accepted)} accepted redactions",
                metadata={"run_id": str(run_id), "challenges": created, "inconsistencies": sum(1 for _ in peers) // 2},
            )
            await session.commit()

            yield json.dumps({
                "type": "done",
                "total": created,
                "run_id": str(run_id),
            }) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@router.get("/cases/{case_id}/qa", response_model=list[ChallengeOut])
async def list_challenges(case_id: uuid.UUID, session: SessionDep) -> list[ChallengeOut]:
    # Latest run only
    latest_run = (
        await session.execute(
            select(RedactionChallenge.run_id)
            .where(RedactionChallenge.case_id == case_id)
            .order_by(RedactionChallenge.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest_run is None:
        return []
    rows = list((await session.execute(
        select(RedactionChallenge)
        .where(
            RedactionChallenge.case_id == case_id,
            RedactionChallenge.run_id == latest_run,
        )
        .order_by(RedactionChallenge.created_at.asc())
    )).scalars().all())

    # Eager-load the underlying redactions in one query
    red_ids = [c.redaction_id for c in rows]
    reds = {
        r.id: r
        for r in (
            await session.execute(select(Redaction).where(Redaction.id.in_(red_ids)))
        ).scalars().all()
    }
    out: list[ChallengeOut] = []
    for c in rows:
        r = reds.get(c.redaction_id)
        out.append(
            ChallengeOut(
                id=c.id,
                case_id=c.case_id,
                redaction_id=c.redaction_id,
                run_id=c.run_id,
                challenge_question=c.challenge_question,
                suggested_answer=c.suggested_answer,
                legal_basis=c.legal_basis,
                risk_flag=c.risk_flag,
                difficulty=c.difficulty,
                inconsistency_peer_id=c.inconsistency_peer_id,
                lawyer_status=c.lawyer_status,
                lawyer_notes=c.lawyer_notes,
                redaction={
                    "id": str(r.id),
                    "label": r.label,
                    "confidence": r.confidence,
                    "confidence_band": _confidence_band(r.confidence),
                    "text_span": r.text_span,
                    "page": r.page,
                    "document_id": str(r.document_id),
                } if r else None,
            )
        )
    return out


@router.patch("/redaction_challenges/{challenge_id}", response_model=ChallengeOut)
async def review_challenge(
    challenge_id: uuid.UUID,
    body: ReviewIn,
    session: SessionDep,
) -> ChallengeOut:
    c = await session.get(RedactionChallenge, challenge_id)
    if c is None:
        raise HTTPException(404, "Challenge not found")
    if body.lawyer_status not in {"pending", "prepared", "needs_work", "will_revise"}:
        raise HTTPException(400, f"Invalid status: {body.lawyer_status}")
    c.lawyer_status = body.lawyer_status
    if body.lawyer_notes is not None:
        c.lawyer_notes = body.lawyer_notes
    c.reviewed_at = datetime.now(timezone.utc)
    await audit.log_event(
        session,
        action=f"qa_{body.lawyer_status}",
        case_id=c.case_id,
        actor="lawyer",
        target_type="redaction_challenge",
        target_id=str(c.id),
        summary=f"{c.lawyer_status}: {c.challenge_question[:80]}",
    )
    await session.commit()

    r = await session.get(Redaction, c.redaction_id)
    return ChallengeOut(
        id=c.id,
        case_id=c.case_id,
        redaction_id=c.redaction_id,
        run_id=c.run_id,
        challenge_question=c.challenge_question,
        suggested_answer=c.suggested_answer,
        legal_basis=c.legal_basis,
        risk_flag=c.risk_flag,
        difficulty=c.difficulty,
        inconsistency_peer_id=c.inconsistency_peer_id,
        lawyer_status=c.lawyer_status,
        lawyer_notes=c.lawyer_notes,
        redaction={
            "id": str(r.id),
            "label": r.label,
            "confidence": r.confidence,
            "confidence_band": _confidence_band(r.confidence),
            "text_span": r.text_span,
            "page": r.page,
            "document_id": str(r.document_id),
        } if r else None,
    )
