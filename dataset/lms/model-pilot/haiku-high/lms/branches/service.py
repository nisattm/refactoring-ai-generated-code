"""Branch rules (section 17.3, LIB-BR-01 to LIB-BR-04)."""

import datetime
import typing

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from lms.audit.service import record_event
from lms.auth.models import User
from lms.branches.models import Branch
from lms.core.errors import ApiError
from lms.members.models import Member


def get_branch(session: Session, branch_id: int) -> Branch:
    branch = session.get(Branch, branch_id)
    if branch is None:
        raise ApiError(404, "NOT_FOUND", "The branch does not exist.")
    return branch


def branch_reference(session: Session, branch_id: int, field: str) -> Branch:
    """LIB-COM-29: a branch id in a request body or query must refer to an existing branch."""
    branch = session.get(Branch, branch_id)
    if branch is None:
        raise ApiError(
            404,
            "NOT_FOUND",
            "The branch does not exist.",
            {"field": field, "id": branch_id},
        )
    return branch


def require_active(branch: Branch) -> None:
    """LIB-BR-04: an inactive branch cannot be used for a new reference."""
    if not branch.is_active:
        raise ApiError(409, "BRANCH_INACTIVE", "The branch is inactive.")


def branch_in_use(session: Session, branch: Branch) -> bool:
    """LIB-BR-03. Copies (module 4) and reservations (module 6) are added to this check with those modules."""
    return (
        session.scalar(select(Member.id).where(Member.home_branch_id == branch.id).limit(1))
        is not None
    )


def create_branch(
    session: Session,
    *,
    actor: User,
    now: datetime.datetime,
    code: str,
    name: str,
    address: str,
) -> Branch:
    """LIB-BR-01. The request schema has already checked the formats and upper-cased the code."""
    if session.scalar(select(Branch.id).where(Branch.code == code)) is not None:
        raise ApiError(
            409, "CONFLICT", "A branch with this code already exists.", {"field": "code"}
        )
    branch = Branch(code=code, name=name, address=address, is_active=True, created_at=now)
    session.add(branch)
    session.flush()
    record_event(
        session,
        at=now,
        event="branch_created",
        entity_type="branch",
        entity_id=branch.id,
        actor_user_id=actor.id,
        details={"code": code, "name": name, "address": address},
    )
    return branch


def branch_list_statement(*, is_active: bool | None) -> Select:
    """LIB-BR-02: branches ordered by code, optionally filtered by active state."""
    statement = select(Branch).order_by(Branch.code, Branch.id)
    if is_active is not None:
        statement = statement.where(Branch.is_active == is_active)
    return statement


def update_branch(
    session: Session,
    *,
    actor: User,
    now: datetime.datetime,
    branch: Branch,
    name: str | None,
    address: str | None,
    is_active: bool | None,
) -> Branch:
    """LIB-BR-03. Only the fields that are given are changed."""
    if is_active is False and branch.is_active and branch_in_use(session, branch):
        raise ApiError(
            409, "BRANCH_IN_USE", "The branch is still in use and cannot be deactivated."
        )

    changes: dict[str, dict[str, typing.Any]] = {}
    for field, new in (("name", name), ("address", address), ("is_active", is_active)):
        old = getattr(branch, field)
        if new is not None and old != new:
            changes[field] = {"old": old, "new": new}
            setattr(branch, field, new)
    if changes:
        record_event(
            session,
            at=now,
            event="branch_updated",
            entity_type="branch",
            entity_id=branch.id,
            actor_user_id=actor.id,
            details=changes,
        )
    return branch
