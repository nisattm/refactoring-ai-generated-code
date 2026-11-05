"""Module 11 endpoints: branches (section 17.2, LIB-BR-01 to LIB-BR-03)."""

from typing import Literal

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import orm, select

from lms.api.deps import get_db, get_settings
from lms.api.errors import ApiError
from lms.audit.log import record_event
from lms.auth.deps import current_user, require_admin
from lms.auth.models import User
from lms.branches.models import Branch
from lms.branches.schemas import BranchCreate, BranchOut, BranchUpdate
from lms.branches.service import branch_in_use
from lms.core.pagination import Page, PageParams, paginate
from lms.core.settings import Settings

router = APIRouter(prefix="/api/v1/branches", tags=["branches"])


def _not_found() -> ApiError:
    return ApiError(404, "NOT_FOUND", "The branch does not exist.")


@router.post("", status_code=201, response_model=BranchOut)
def create_branch(
    body: BranchCreate,
    admin: User = Depends(require_admin),
    db: orm.Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Branch:
    if db.scalar(select(Branch.id).where(Branch.code == body.code)) is not None:
        raise ApiError(409, "CONFLICT", "A branch with this code already exists.", {"field": "code"})

    branch = Branch(
        code=body.code,
        name=body.name,
        address=body.address,
        is_active=True,
        created_at=settings.clock.now(),
    )
    db.add(branch)
    db.flush()
    record_event(
        db, settings.clock, "branch_created",
        actor_user_id=admin.id, entity_type="branch", entity_id=branch.id,
        details={"code": branch.code, "name": branch.name, "address": branch.address},
    )
    db.commit()
    return branch


@router.get("", response_model=Page[BranchOut])
def list_branches(
    is_active: Literal["true", "false"] | None = Query(default=None),
    params: PageParams = Depends(),
    _user: User = Depends(current_user),
    db: orm.Session = Depends(get_db),
) -> Page[BranchOut]:
    statement = select(Branch).order_by(Branch.code, Branch.id)
    if is_active is not None:
        statement = statement.where(Branch.is_active.is_(is_active == "true"))
    return paginate(list(db.scalars(statement)), params, BranchOut.model_validate)


@router.get("/{branch_id}", response_model=BranchOut)
def get_branch(
    branch_id: int = Path(gt=0),
    _user: User = Depends(current_user),
    db: orm.Session = Depends(get_db),
) -> Branch:
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise _not_found()
    return branch


@router.patch("/{branch_id}", response_model=BranchOut)
def update_branch(
    body: BranchUpdate,
    branch_id: int = Path(gt=0),
    admin: User = Depends(require_admin),
    db: orm.Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Branch:
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise _not_found()

    fields = body.model_fields_set
    deactivating = "is_active" in fields and body.is_active is False and branch.is_active
    if deactivating and branch_in_use(db, branch.id):
        raise ApiError(409, "BRANCH_IN_USE", "The branch is still used by copies, members or reservations.")

    changes: dict[str, dict] = {}
    if "name" in fields and body.name != branch.name:
        changes["name"] = {"old": branch.name, "new": body.name}
        branch.name = body.name
    if "address" in fields and body.address != branch.address:
        changes["address"] = {"old": branch.address, "new": body.address}
        branch.address = body.address
    if "is_active" in fields and body.is_active != branch.is_active:
        changes["is_active"] = {"old": branch.is_active, "new": body.is_active}
        branch.is_active = body.is_active

    if changes:
        record_event(
            db, settings.clock, "branch_updated",
            actor_user_id=admin.id, entity_type="branch", entity_id=branch.id, details=changes,
        )
    db.commit()
    return branch
