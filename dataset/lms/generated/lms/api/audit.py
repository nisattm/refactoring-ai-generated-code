"""Audit log endpoint (section 19.1)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from lms.api.common import optional_date
from lms.audit.schemas import AuditEntryOut, audit_entry_out
from lms.audit.service import audit_list_stmt
from lms.auth.deps import AdminOnly
from lms.core.db import SessionDep
from lms.core.pagination import Page, PageDep, paginate

router = APIRouter(tags=["audit"])


@router.get("/audit-log", response_model=Page[AuditEntryOut])
def list_audit_log(
    db: SessionDep,
    _: AdminOnly,
    page: PageDep,
    event: Annotated[str | None, Query()] = None,
    actor_user_id: Annotated[int | None, Query()] = None,
    entity_type: Annotated[str | None, Query()] = None,
    entity_id: Annotated[int | None, Query()] = None,
    date_from: Annotated[str | None, Query(alias="from")] = None,
    date_to: Annotated[str | None, Query(alias="to")] = None,
) -> Page[AuditEntryOut]:
    stmt = audit_list_stmt(
        event=event,
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        date_from=optional_date("from", date_from),
        date_to=optional_date("to", date_to),
    )
    return paginate(db, stmt, page, audit_entry_out)
