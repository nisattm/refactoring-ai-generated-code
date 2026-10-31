"""Branch endpoints (section 17.2)."""

from __future__ import annotations

from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Path, Query, Request

from lms.auth.deps import AdminOnly, AnyUser
from lms.branches import service
from lms.branches.models import Branch
from lms.branches.schemas import BranchCreateIn, BranchOut, BranchPatchIn, branch_out
from lms.core.clock import local_now
from lms.core.db import SessionDep
from lms.core.pagination import Page, PageDep, paginate

router = APIRouter(prefix="/branches", tags=["branches"])

BranchId = Annotated[int, Path(ge=1)]


@router.post("", response_model=BranchOut, status_code=201)
def create_branch(body: BranchCreateIn, request: Request, db: SessionDep, admin: AdminOnly) -> BranchOut:
    now = local_now(request.app.state.settings.clock)
    return branch_out(service.create_branch(db, now, admin.user, body.code, body.name, body.address))


@router.get("", response_model=Page[BranchOut])
def list_branches(
    db: SessionDep,
    _: AnyUser,
    page: PageDep,
    is_active: Annotated[bool | None, Query()] = None,
) -> Page[BranchOut]:
    stmt = sa.select(Branch).order_by(Branch.code, Branch.id)
    if is_active is not None:
        stmt = stmt.where(Branch.is_active == is_active)
    return paginate(db, stmt, page, branch_out)


@router.get("/{branch_id}", response_model=BranchOut)
def get_branch(branch_id: BranchId, db: SessionDep, _: AnyUser) -> BranchOut:
    return branch_out(service.get_branch_or_404(db, branch_id))


@router.patch("/{branch_id}", response_model=BranchOut)
def update_branch(
    branch_id: BranchId, body: BranchPatchIn, request: Request, db: SessionDep, admin: AdminOnly
) -> BranchOut:
    now = local_now(request.app.state.settings.clock)
    branch = service.get_branch_or_404(db, branch_id)
    fields = {name: getattr(body, name) for name in body.model_fields_set}
    return branch_out(service.update_branch(db, now, admin.user, branch, fields))
