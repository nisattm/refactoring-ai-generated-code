"""Recording audit entries (LIB-AUD-01, LIB-AUD-02)."""

from __future__ import annotations

import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.models import AuditEntry
from lms.core.clock import LOCAL_TZ


def record(
    session: Session,
    *,
    at: datetime.datetime,
    event: str,
    entity_type: str,
    entity_id: int | None,
    actor_user_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> AuditEntry:
    """Add an audit entry to the caller's transaction. ``details`` must not contain secrets."""
    entry = AuditEntry(
        at=at,
        actor_user_id=actor_user_id,
        event=event,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details or {},
    )
    session.add(entry)
    return entry


def changes(old: dict[str, Any], new: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """``{"field": {"old": ..., "new": ...}}`` for the fields whose value differs (LIB-AUD-02)."""
    return {k: {"old": old[k], "new": new[k]} for k in new if old.get(k) != new[k]}


def audit_list_stmt(
    *,
    event: str | None = None,
    actor_user_id: int | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    date_from: datetime.date | None = None,
    date_to: datetime.date | None = None,
) -> sa.Select[tuple[AuditEntry]]:
    """LIB-AUD-03: newest first; ``date_from`` and ``date_to`` are inclusive local dates of ``at``."""
    stmt = sa.select(AuditEntry).order_by(AuditEntry.id.desc())
    if event is not None:
        stmt = stmt.where(AuditEntry.event == event)
    if actor_user_id is not None:
        stmt = stmt.where(AuditEntry.actor_user_id == actor_user_id)
    if entity_type is not None:
        stmt = stmt.where(AuditEntry.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(AuditEntry.entity_id == entity_id)
    if date_from is not None:
        stmt = stmt.where(AuditEntry.at >= datetime.datetime.combine(date_from, datetime.time.min, LOCAL_TZ))
    if date_to is not None and date_to < datetime.date.max:
        end = datetime.datetime.combine(date_to + datetime.timedelta(days=1), datetime.time.min, LOCAL_TZ)
        stmt = stmt.where(AuditEntry.at < end)
    return stmt
