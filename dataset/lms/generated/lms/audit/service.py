"""Recording audit entries (LIB-AUD-01, LIB-AUD-02)."""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy.orm import Session

from lms.audit.models import AuditEntry


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
