"""Response schema of the audit log (section 19.1)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from lms.audit.models import AuditEntry
from lms.core.timeutil import format_datetime


class AuditEntryOut(BaseModel):
    id: int
    at: str
    actor_user_id: int | None
    event: str
    entity_type: str
    entity_id: int | None
    details: dict[str, Any]


def audit_entry_out(entry: AuditEntry) -> AuditEntryOut:
    return AuditEntryOut(
        id=entry.id,
        at=format_datetime(entry.at),
        actor_user_id=entry.actor_user_id,
        event=entry.event,
        entity_type=entry.entity_type,
        entity_id=entry.entity_id,
        details=entry.details,
    )
