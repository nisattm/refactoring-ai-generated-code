"""Module 13: Audit log (entry model and recording; endpoints come in a later step)."""
import datetime
from typing import Any

from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..core.db import Base, UtcDateTime


class AuditEntry(Base):
    __tablename__ = "audit_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime.datetime] = mapped_column(UtcDateTime)
    actor_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event: Mapped[str] = mapped_column(String)
    entity_type: Mapped[str] = mapped_column(String)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)


def record(
    session: Session,
    now: datetime.datetime,
    event: str,
    actor_user_id: int | None,
    entity_type: str,
    entity_id: int | None,
    details: dict[str, Any] | None = None,
) -> AuditEntry:
    """Add an audit entry to the caller's transaction (LIB-AUD-01)."""
    entry = AuditEntry(
        at=now,
        actor_user_id=actor_user_id,
        event=event,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details or {},
    )
    session.add(entry)
    return entry
