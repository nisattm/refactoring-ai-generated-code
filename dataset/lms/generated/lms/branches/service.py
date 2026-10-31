"""Business logic of module 11, branches (LIB-BR-01 to LIB-BR-04)."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import changes, record
from lms.auth.models import User
from lms.branches.models import Branch
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
    """LIB-BR-03. Copies and active reservations are checked here as their modules are added."""
    return db.scalar(sa.select(Member.id).where(Member.home_branch_id == branch_id).limit(1)) is not None


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
