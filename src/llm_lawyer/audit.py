"""Audit trail helper (PRD §4.8). Every decision point in the app calls
``log_event(...)`` so the attorney can defend their process in court.

The helper is intentionally fire-and-forget tolerant — audit logging should
never block or fail the primary operation.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from llm_lawyer.db.models import AuditEvent

logger = logging.getLogger(__name__)


async def log_event(
    session: AsyncSession,
    *,
    action: str,
    case_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
    actor: str = "lawyer",
    target_type: str | None = None,
    target_id: str | None = None,
    summary: str | None = None,
    metadata: dict | None = None,
) -> None:
    try:
        session.add(
            AuditEvent(
                case_id=case_id,
                document_id=document_id,
                actor=actor,
                action=action,
                target_type=target_type,
                target_id=str(target_id) if target_id is not None else None,
                summary=summary,
                event_metadata=metadata or {},
            )
        )
        await session.flush()
    except Exception as e:
        logger.warning("audit log_event(%s) failed: %s", action, e)
