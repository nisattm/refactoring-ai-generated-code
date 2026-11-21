"""Transfer endpoints (section 17.2)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request

from lms.api.common import IdPath, now_of, settings_of
from lms.auth.deps import StaffOnly
from lms.branches import transfers as service
from lms.branches.schemas import ReceivedOut, TransferCreateIn, TransferOut, transfer_out
from lms.core.db import SessionDep
from lms.core.pagination import Page, PageDep, paginate

router = APIRouter(prefix="/transfers", tags=["transfers"])


@router.post("", response_model=TransferOut, status_code=201)
def create_transfer(body: TransferCreateIn, request: Request, db: SessionDep, staff: StaffOnly) -> TransferOut:
    transfer = service.relocate(
        db,
        now_of(request),
        staff.user,
        settings_of(request).holidays,
        copy_id=body.copy_id,
        to_branch_id=body.to_branch_id,
    )
    return transfer_out(transfer)


@router.post("/process-arrivals", response_model=ReceivedOut)
def process_arrivals(request: Request, db: SessionDep, staff: StaffOnly) -> ReceivedOut:
    return ReceivedOut(received=service.process_arrivals(db, now_of(request), staff.user, settings_of(request).holidays))


@router.get("", response_model=Page[TransferOut])
def list_transfers(
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    status: Annotated[Literal["in_transit", "received"] | None, Query()] = None,
    copy_id: Annotated[int | None, Query()] = None,
    from_branch_id: Annotated[int | None, Query()] = None,
    to_branch_id: Annotated[int | None, Query()] = None,
    reason: Annotated[Literal["return_home", "reservation", "relocation"] | None, Query()] = None,
) -> Page[TransferOut]:
    stmt = service.transfer_list_stmt(
        status=status, copy_id=copy_id, from_branch_id=from_branch_id, to_branch_id=to_branch_id, reason=reason
    )
    return paginate(db, stmt, page, transfer_out)


@router.get("/{transfer_id}", response_model=TransferOut)
def get_transfer(transfer_id: IdPath, db: SessionDep, _: StaffOnly) -> TransferOut:
    return transfer_out(service.get_transfer_or_404(db, transfer_id))
