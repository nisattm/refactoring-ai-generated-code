"""Module 11 endpoints for branches (section 17.2, LIB-BR-01 to LIB-BR-04)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query

from lms.api.branch_schemas import BranchOut, CreateBranchIn, UpdateBranchIn
from lms.api.deps import AdminDep, SessionDep, SettingsDep, get_authenticated
from lms.branches import service
from lms.core.pagination import page_body, paginate

router = APIRouter(prefix="/api/v1/branches", tags=["branches"])

BranchId = Annotated[int, Path(gt=0)]


@router.post("", status_code=201, response_model=BranchOut)
def create_branch(
    body: CreateBranchIn, admin: AdminDep, session: SessionDep, settings: SettingsDep
) -> BranchOut:
    branch = service.create_branch(
        session,
        actor=admin.user,
        now=settings.clock.now(),
        code=body.code,
        name=body.name,
        address=body.address,
    )
    return BranchOut.model_validate(branch)


@router.get("", dependencies=[Depends(get_authenticated)])
def list_branches(
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    is_active: Literal["true", "false"] | None = None,
) -> dict:
    statement = service.branch_list_statement(
        is_active=None if is_active is None else is_active == "true"
    )
    found, total = paginate(session, statement, page, page_size)
    items = [BranchOut.model_validate(branch).model_dump(mode="json") for branch in found]
    return page_body(items, page=page, page_size=page_size, total=total)


@router.get("/{branch_id}", response_model=BranchOut, dependencies=[Depends(get_authenticated)])
def get_branch(branch_id: BranchId, session: SessionDep) -> BranchOut:
    return BranchOut.model_validate(service.get_branch(session, branch_id))


@router.patch("/{branch_id}", response_model=BranchOut)
def update_branch(
    branch_id: BranchId,
    body: UpdateBranchIn,
    admin: AdminDep,
    session: SessionDep,
    settings: SettingsDep,
) -> BranchOut:
    branch = service.get_branch(session, branch_id)
    service.update_branch(
        session,
        actor=admin.user,
        now=settings.clock.now(),
        branch=branch,
        name=body.name,
        address=body.address,
        is_active=body.is_active,
    )
    return BranchOut.model_validate(branch)
