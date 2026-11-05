"""Writing audit entries (LIB-AUD-01, LIB-AUD-02)."""

import datetime
import typing

from sqlalchemy.orm import Session

from lms.audit.models import AuditEntry


def record_event(
    session: Session,
    *,
    at: datetime.datetime,
    event: str,
    entity_type: str,
    entity_id: int | None,
    actor_user_id: int | None,
    details: typing.Mapping[str, typing.Any] | None = None,
) -> None:
    """Add an entry to the current transaction, so it is committed or rolled back with the change."""
    session.add(
        AuditEntry(
            at=at,
            actor_user_id=actor_user_id,
            event=event,
            entity_type=entity_type,
            entity_id=entity_id,
            details=dict(details or {}),
        )
    )
