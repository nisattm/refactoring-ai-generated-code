"""Business logic of module 11, branches (LIB-BR-01 to LIB-BR-05).

Of the transfers only their start exists so far; relocation, arrival and listing are added later.
"""

from __future__ import annotations

import datetime
from collections.abc import Container

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import changes, record
from lms.auth.models import User
from lms.branches.models import Branch, Transfer
from lms.catalog.models import Copy
from lms.catalog.status import set_status
from lms.core.calendar import add_working_days
from lms.core.errors import Conflict, NotFound, reference_not_found
from lms.members.models import Member


def create_branch(db: Session, now: datetime.datetime, actor: User, code: str, name: str, address: str) -> Branch:
    """LIB-BR-01. ``code`` is already upper case and valid."""
    if db.scalar(sa.select(Branch.id).where(Branch.code == code)) is not None:
        raise Conflict("A branch with this code already exists", details={"field": "code"})
    branch = Branch(code=code, name=name, address=address, is_active=True, created_at=now)
    db.add(branch)
    db.flush()
    record(
        db,
        at=now,
        event="branch_created",
        actor_user_id=actor.id,
        entity_type="branch",
        entity_id=branch.id,
        details={"code": code, "name": name, "address": address},
    )
    return branch


def get_branch_or_404(db: Session, branch_id: int) -> Branch:
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise NotFound(f"Branch {branch_id} does not exist", details={"resource": "branch", "id": branch_id})
    return branch


def require_active_branch(db: Session, field: str, branch_id: int) -> Branch:
    """A branch referenced from a request: ``404 NOT_FOUND`` if missing (LIB-COM-29),
    ``409 BRANCH_INACTIVE`` if inactive (LIB-BR-04)."""
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise reference_not_found(field, branch_id)
    if not branch.is_active:
        raise Conflict(
            f"Branch {branch.code} is inactive", code="BRANCH_INACTIVE", details={"field": field, "id": branch_id}
        )
    return branch


def is_branch_in_use(db: Session, branch_id: int) -> bool:
    """LIB-BR-03. Active reservations are checked here once module 6 is added."""
    if db.scalar(sa.select(Member.id).where(Member.home_branch_id == branch_id).limit(1)) is not None:
        return True
    in_branch = sa.or_(Copy.home_branch_id == branch_id, Copy.current_branch_id == branch_id)
    return db.scalar(sa.select(Copy.id).where(Copy.status != "withdrawn", in_branch).limit(1)) is not None


def update_branch(db: Session, now: datetime.datetime, actor: User, branch: Branch, fields: dict[str, object]) -> Branch:
    """LIB-BR-03. ``fields`` holds only the fields present in the request."""
    if fields.get("is_active") is False and branch.is_active and is_branch_in_use(db, branch.id):
        raise Conflict(
            "The branch is still used by copies, members or reservations",
            code="BRANCH_IN_USE",
            details={"id": branch.id},
        )
    diff = changes({k: getattr(branch, k) for k in fields}, fields)
    for name, value in fields.items():
        setattr(branch, name, value)
    if diff:
        record(
            db,
            at=now,
            event="branch_updated",
            actor_user_id=actor.id,
            entity_type="branch",
            entity_id=branch.id,
            details=diff,
        )
    return branch


def start_transfer(
    db: Session,
    now: datetime.datetime,
    actor_user_id: int | None,
    copy: Copy,
    to_branch_id: int,
    reason: str,
    holidays: Container[datetime.date],
    reservation_id: int | None = None,
) -> Transfer:
    """LIB-BR-05: the copy becomes ``in_transfer`` and has no current branch until it arrives."""
    assert copy.current_branch_id is not None
    started_on = now.date()
    transfer = Transfer(
        copy_id=copy.id,
        from_branch_id=copy.current_branch_id,
        to_branch_id=to_branch_id,
        reason=reason,
        reservation_id=reservation_id,
        started_on=started_on,
        expected_on=add_working_days(started_on, 2, holidays),
        status="in_transit",
    )
    set_status(copy, "in_transfer")
    copy.current_branch_id = None
    db.add(transfer)
    db.flush()
    record(
        db,
        at=now,
        event="transfer_started",
        actor_user_id=actor_user_id,
        entity_type="transfer",
        entity_id=transfer.id,
        details={
            "copy_id": copy.id,
            "from_branch_id": transfer.from_branch_id,
            "to_branch_id": to_branch_id,
            "reason": reason,
            "reservation_id": reservation_id,
            "expected_on": transfer.expected_on.isoformat(),
        },
    )
    return transfer
