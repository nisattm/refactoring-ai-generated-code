"""Writing audit entries (LIB-AUD-01, LIB-AUD-02). The entry joins the caller's transaction."""

from typing import Any

from sqlalchemy import orm

from lms.audit.models import AuditEntry
from lms.core.clock import Clock


def record_event(
    db: orm.Session,
    clock: Clock,
    event: str,
    *,
    entity_type: str,
    entity_id: int | None,
    actor_user_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditEntry(
            at=clock.now(),
            actor_user_id=actor_user_id,
            event=event,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details or {},
        )
    )
