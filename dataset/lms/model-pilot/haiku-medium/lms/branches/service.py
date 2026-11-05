"""Checks on branches that other modules use (LIB-BR-03, LIB-BR-04)."""

from sqlalchemy import orm, select

from lms.api.errors import ApiError
from lms.branches.models import Branch
from lms.members.models import Member


def reference_branch(db: orm.Session, field: str, branch_id: int) -> Branch:
    """A branch named by a body or query field; a missing one is 404 (LIB-COM-29)."""
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise ApiError(404, "NOT_FOUND", "The branch does not exist.", {"field": field, "id": branch_id})
    return branch


def ensure_active(branch: Branch) -> None:
    """An inactive branch cannot be used for new references (LIB-BR-04)."""
    if not branch.is_active:
        raise ApiError(409, "BRANCH_INACTIVE", "The branch is inactive.", {"branch_id": branch.id})


def branch_in_use(db: orm.Session, branch_id: int) -> bool:
    """Whether the branch is still referred to (LIB-BR-03).

    Copies (module 4) and active reservations (module 6) are not stored yet; they join this check with their modules.
    """
    return db.scalar(select(Member.id).where(Member.home_branch_id == branch_id).limit(1)) is not None
