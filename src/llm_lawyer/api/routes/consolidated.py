"""Consolidated Case Brief (PRD §4 finalised package).

The closing step of the matter: a single LLM-synthesised strategic brief that
rolls up everything the attorney produced —

  * our accepted/modified redactions as a privilege log,
  * the Q&A rehearsal preparedness per redaction (our live exposure),
  * strengths/weaknesses on our own documents,
  * challenges + gap analysis against opposing counsel's production,

and reasons over it ("simulates the case") to give an overall posture and a
ranked action list. Streams NDJSON like the other pipelines so the frontend
can show the deterministic roll-up immediately, then the synthesised brief.

Events:
  {"type": "started", "case_name": str}
  {"type": "stage", "stage": "aggregating" | "synthesising"}
  {"type": "aggregate", "aggregate": {...}}   # deterministic roll-up
  {"type": "brief", "content": markdown, "model": str, "provider": str}
  {"type": "done"}
  {"type": "error", "message": str}
"""
from __future__ import annotations

import io
import json
import logging
import uuid

import pymupdf
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from llm_lawyer import audit
from llm_lawyer.db.models import (
    Case,
    CaseAnalysis,
    Document,
    DocumentAnalysis,
    Redaction,
    RedactionChallenge,
)
from llm_lawyer.db.session import SessionDep, SessionLocal
from llm_lawyer.llm import client as llm_client
from llm_lawyer.llm import prompts as PROMPTS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cases", tags=["consolidated"])

_KIND = "consolidated_brief"
_ACCEPTED = ("accepted", "modified")


class ConsolidatedOut(BaseModel):
    case_id: uuid.UUID
    brief: str
    aggregate: dict
    model: str | None
    created_at: str | None


async def _build_aggregate(session, case_id: uuid.UUID) -> dict:
    """Deterministic roll-up of every artefact in the matter. This is the
    factual spine the LLM synthesises — and is also returned to the UI so the
    privilege log etc. render even before/independent of the narrative."""
    own_docs = list(
        (
            await session.execute(
                select(Document).where(
                    Document.case_id == case_id,
                    Document.production_type == "own",
                )
            )
        ).scalars().all()
    )
    opposing_docs = list(
        (
            await session.execute(
                select(Document).where(
                    Document.case_id == case_id,
                    Document.production_type == "opposing",
                )
            )
        ).scalars().all()
    )
    doc_title = {d.id: d.title for d in own_docs + opposing_docs}

    # --- Privilege log: accepted/modified redactions on our own docs ---
    own_ids = [d.id for d in own_docs]
    redactions: list[Redaction] = []
    if own_ids:
        redactions = list(
            (
                await session.execute(
                    select(Redaction).where(
                        Redaction.document_id.in_(own_ids),
                        Redaction.status.in_(_ACCEPTED),
                    )
                )
            ).scalars().all()
        )

    # --- Q&A rehearsal: newest run's challenges, keyed by redaction ---
    qa_rows = list(
        (
            await session.execute(
                select(RedactionChallenge)
                .where(RedactionChallenge.case_id == case_id)
                .order_by(RedactionChallenge.created_at.desc())
            )
        ).scalars().all()
    )
    latest_run = qa_rows[0].run_id if qa_rows else None
    qa_by_redaction = {
        c.redaction_id: c for c in qa_rows if c.run_id == latest_run
    }

    privilege_log = []
    for r in redactions:
        ch = qa_by_redaction.get(r.id)
        privilege_log.append(
            {
                "document": doc_title.get(r.document_id, "(unknown)"),
                "span": (r.modified_span or r.text_span or "").strip()[:300],
                "basis": r.label,
                "confidence": r.confidence,
                "status": r.status,
                "qa_status": ch.lawyer_status if ch else None,
                "qa_question": ch.challenge_question if ch else None,
                "qa_risk_flag": ch.risk_flag if ch else None,
            }
        )

    # --- Strengths / weaknesses on our own docs (latest per doc) ---
    strengths_weaknesses = []
    for d in own_docs:
        row = (
            await session.execute(
                select(DocumentAnalysis)
                .where(
                    DocumentAnalysis.document_id == d.id,
                    DocumentAnalysis.kind == "strengths_weaknesses",
                )
                .order_by(DocumentAnalysis.created_at.desc())
                .limit(1)
            )
        ).scalars().first()
        if row:
            strengths_weaknesses.append(
                {"document": d.title, "content": row.content}
            )

    # --- Opposing counsel leverage (latest opposing_review per doc) ---
    opposing_leverage = []
    for d in opposing_docs:
        row = (
            await session.execute(
                select(DocumentAnalysis)
                .where(
                    DocumentAnalysis.document_id == d.id,
                    DocumentAnalysis.kind == "opposing_review",
                )
                .order_by(DocumentAnalysis.created_at.desc())
                .limit(1)
            )
        ).scalars().first()
        if row:
            opposing_leverage.append(
                {
                    "document": d.title,
                    "challenges": row.content.get("challenges", []),
                    "gaps": row.content.get("gaps", []),
                }
            )

    unprepared = [
        p
        for p in privilege_log
        if p["qa_status"] in (None, "pending", "needs_work", "will_revise")
    ]
    return {
        "counts": {
            "own_documents": len(own_docs),
            "opposing_documents": len(opposing_docs),
            "accepted_redactions": len(privilege_log),
            "redactions_unprepared": len(unprepared),
            "opposing_challenges": sum(
                len(o["challenges"]) for o in opposing_leverage
            ),
            "opposing_gaps": sum(len(o["gaps"]) for o in opposing_leverage),
            "qa_run": str(latest_run) if latest_run else None,
        },
        "privilege_log": privilege_log,
        "strengths_weaknesses": strengths_weaknesses,
        "opposing_leverage": opposing_leverage,
    }


def _format_for_prompt(agg: dict) -> str:
    lines: list[str] = []
    c = agg["counts"]
    lines.append(
        f"Roll-up: {c['own_documents']} own docs, "
        f"{c['accepted_redactions']} accepted redactions "
        f"({c['redactions_unprepared']} not yet prepared in Q&A), "
        f"{c['opposing_documents']} opposing docs, "
        f"{c['opposing_challenges']} challenges, {c['opposing_gaps']} gaps."
    )

    lines.append("\n=== OUR PRIVILEGE LOG (with Q&A rehearsal status) ===")
    if not agg["privilege_log"]:
        lines.append("(no accepted redactions)")
    for i, p in enumerate(agg["privilege_log"], 1):
        conf = f"{p['confidence']:.2f}" if p["confidence"] is not None else "n/a"
        lines.append(
            f"[{i}] {p['document']} — basis={p['basis']} conf={conf} "
            f"status={p['status']} | Q&A={p['qa_status'] or 'not rehearsed'}"
        )
        lines.append(f'    span: "{p["span"]}"')
        if p["qa_question"]:
            lines.append(f"    adversarial Q: {p['qa_question']}")
        if p["qa_risk_flag"]:
            lines.append(f"    risk: {p['qa_risk_flag']}")

    lines.append("\n=== OUR DOCUMENT STRENGTHS / WEAKNESSES ===")
    if not agg["strengths_weaknesses"]:
        lines.append("(none generated)")
    for sw in agg["strengths_weaknesses"]:
        lines.append(f"-- {sw['document']} --")
        for k in ("strengths", "weaknesses"):
            for item in (sw["content"] or {}).get(k, []):
                if isinstance(item, dict):
                    lines.append(
                        f"  {k[:-1]}: {item.get('point', '')} — "
                        f"{item.get('detail', '')}"
                    )

    lines.append("\n=== OPPOSING COUNSEL LEVERAGE ===")
    if not agg["opposing_leverage"]:
        lines.append("(no opposing counsel production reviewed)")
    for o in agg["opposing_leverage"]:
        lines.append(f"-- {o['document']} --")
        for ch in o["challenges"]:
            lines.append(
                f"  challenge [{ch.get('strength', '?')}]: "
                f"{ch.get('challenge', '')} (basis: {ch.get('legal_basis', '')})"
            )
        for g in o["gaps"]:
            lines.append(
                f"  gap: {g.get('gap_description', '')} "
                f"(significance: {g.get('significance', '')})"
            )
    return "\n".join(lines)


@router.post("/{case_id}/consolidated/stream")
async def stream_consolidated(case_id: uuid.UUID):
    async def gen():
        async with SessionLocal() as session:
            case = await session.get(Case, case_id)
            if case is None:
                yield json.dumps(
                    {"type": "error", "message": "Case not found"}
                ) + "\n"
                return

            yield json.dumps(
                {"type": "started", "case_name": case.name}
            ) + "\n"
            yield json.dumps(
                {"type": "stage", "stage": "aggregating"}
            ) + "\n"

            agg = await _build_aggregate(session, case_id)
            yield json.dumps({"type": "aggregate", "aggregate": agg}) + "\n"

            if (
                agg["counts"]["accepted_redactions"] == 0
                and not agg["opposing_leverage"]
            ):
                yield json.dumps(
                    {
                        "type": "error",
                        "message": (
                            "Nothing to consolidate yet — accept some "
                            "redactions or run an opposing counsel review "
                            "first."
                        ),
                    }
                ) + "\n"
                return

            yield json.dumps(
                {"type": "stage", "stage": "synthesising"}
            ) + "\n"

            memory_ctx = await PROMPTS.load_memory_context(session, case_id)
            system = PROMPTS.render(
                PROMPTS.CONSOLIDATED_BRIEF_SYSTEM, memory_ctx
            )
            try:
                result = await llm_client.chat_completion(
                    [
                        {"role": "system", "content": system},
                        {
                            "role": "user",
                            "content": (
                                f"Matter: {case.name}\n\n"
                                + _format_for_prompt(agg)
                            ),
                        },
                    ],
                    task="narrative",
                )
            except Exception as e:
                logger.warning("consolidated synthesis failed: %s", e)
                yield json.dumps(
                    {"type": "error", "message": str(e)}
                ) + "\n"
                return

            session.add(
                CaseAnalysis(
                    case_id=case_id,
                    kind=_KIND,
                    content={"brief": result.text, "aggregate": agg},
                    model=result.model,
                )
            )
            await audit.log_event(
                session,
                action="consolidated_brief_run",
                case_id=case_id,
                actor="ai",
                summary=(
                    f"{agg['counts']['accepted_redactions']} redactions · "
                    f"{agg['counts']['redactions_unprepared']} unprepared · "
                    f"{agg['counts']['opposing_challenges']} challenges"
                ),
                metadata=agg["counts"],
            )
            await session.commit()

            yield json.dumps(
                {
                    "type": "brief",
                    "content": result.text,
                    "model": result.model,
                    "provider": result.provider,
                }
            ) + "\n"
            yield json.dumps({"type": "done"}) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@router.get("/{case_id}/consolidated", response_model=ConsolidatedOut | None)
async def get_consolidated(case_id: uuid.UUID, session: SessionDep):
    row = (
        await session.execute(
            select(CaseAnalysis)
            .where(
                CaseAnalysis.case_id == case_id,
                CaseAnalysis.kind == _KIND,
            )
            .order_by(CaseAnalysis.created_at.desc())
            .limit(1)
        )
    ).scalars().first()
    if not row:
        return None
    return ConsolidatedOut(
        case_id=row.case_id,
        brief=row.content.get("brief", ""),
        aggregate=row.content.get("aggregate", {}),
        model=row.model,
        created_at=row.created_at.isoformat() if row.created_at else None,
    )


def _markdown_to_html(md: str) -> str:
    """Minimal Markdown → HTML for PDF rendering. Handles the subset the
    brief prompt emits: ##/### headings, **bold**, -/numbered lists,
    paragraphs. Anything fancier degrades to plain text."""
    import html as _html
    import re

    out: list[str] = []
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for raw in md.splitlines():
        line = raw.rstrip()
        if not line.strip():
            close_list()
            continue
        esc = _html.escape(line.strip())
        esc = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc)
        if line.startswith("### "):
            close_list()
            out.append(f"<h3>{esc[4:]}</h3>")
        elif line.startswith("## "):
            close_list()
            out.append(f"<h2>{esc[3:]}</h2>")
        elif line.startswith("# "):
            close_list()
            out.append(f"<h1>{esc[2:]}</h1>")
        elif re.match(r"^[-*]\s+", line.strip()):
            if not in_list:
                out.append("<ul>")
                in_list = True
            item = re.sub(r"^[-*]\s+", "", esc)
            out.append(f"<li>{item}</li>")
        elif re.match(r"^\d+\.\s+", line.strip()):
            if not in_list:
                out.append("<ul>")
                in_list = True
            item = re.sub(r"^\d+\.\s+", "", esc)
            out.append(f"<li>{item}</li>")
        else:
            close_list()
            out.append(f"<p>{esc}</p>")
    close_list()
    body = "\n".join(out)
    return (
        "<html><head><style>"
        "body{font-family:sans-serif;font-size:11px;line-height:1.5;}"
        "h1{font-size:20px;} h2{font-size:15px;margin-top:14px;}"
        "h3{font-size:12px;} li{margin-bottom:3px;}"
        "</style></head><body>" + body + "</body></html>"
    )


@router.get("/{case_id}/consolidated.pdf")
async def export_consolidated_pdf(case_id: uuid.UUID, session: SessionDep):
    case = await session.get(Case, case_id)
    if case is None:
        raise HTTPException(404, "Case not found")
    row = (
        await session.execute(
            select(CaseAnalysis)
            .where(
                CaseAnalysis.case_id == case_id,
                CaseAnalysis.kind == _KIND,
            )
            .order_by(CaseAnalysis.created_at.desc())
            .limit(1)
        )
    ).scalars().first()
    if not row:
        raise HTTPException(
            404, "No consolidated brief generated yet for this case"
        )

    header = (
        f"# Consolidated Case Brief — {case.name}\n\n"
        f"_Generated {row.created_at:%Y-%m-%d %H:%M UTC} · "
        f"model: {row.model or 'n/a'}_\n\n"
    )
    html = _markdown_to_html(header + row.content.get("brief", ""))

    buf = io.BytesIO()
    writer = pymupdf.DocumentWriter(buf)
    story = pymupdf.Story(html=html)
    media = pymupdf.paper_rect("letter")
    area = media + (54, 54, -54, -54)  # 0.75" margins
    more = True
    while more:
        dev = writer.begin_page(media)
        more, _ = story.place(area)
        story.draw(dev)
        writer.end_page()
    writer.close()
    pdf_bytes = buf.getvalue()

    safe = "".join(
        ch if ch.isalnum() or ch in "-_" else "_" for ch in case.name
    )[:60]
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="case_brief_{safe}.pdf"'
            )
        },
    )
