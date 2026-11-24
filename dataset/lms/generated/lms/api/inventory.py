"""Inventory count endpoints (section 32.2)."""

from __future__ import annotations

from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Path, Query, Request, Response
from sqlalchemy.orm import Session

from lms.api.common import request_now
from lms.auth.deps import StaffOnly
from lms.catalog.schemas import CopyOut, copy_out
from lms.catalog.service import get_copy_or_404
from lms.core.db import SessionDep
from lms.core.pagination import Page, PageDep, PageParams, paginate
from lms.inventory import closing, counts, missing
from lms.inventory.schemas import (
    AddedScanOut,
    ApplyOut,
    CountDetailOut,
    CountIn,
    CountOut,
    CountStatus,
    FoundIn,
    LineOut,
    Outcome,
    ProcessOut,
    ScanOut,
    ScanResult,
    ScansAddedOut,
    ScansIn,
)

router = APIRouter(tags=["inventory"])

CountId = Annotated[int, Path(ge=1)]
ScanId = Annotated[int, Path(ge=1)]
CopyId = Annotated[int, Path(ge=1)]


@router.post("/inventory-counts", response_model=CountDetailOut, status_code=201)
def start_count(body: CountIn, request: Request, db: SessionDep, staff: StaffOnly) -> CountDetailOut:
    count = counts.start_count(
        db,
        request_now(request),
        staff.user,
        request.app.state.settings.holidays,
        branch_id=body.branch_id,
        name=body.name,
        shelf_prefix=body.shelf_prefix,
    )
    return counts.count_detail_out(db, count)


@router.get("/inventory-counts", response_model=Page[CountOut])
def list_counts(
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    branch_id: Annotated[int | None, Query()] = None,
    status: Annotated[CountStatus | None, Query()] = None,
) -> Page[CountOut]:
    return paginate(db, counts.list_stmt(branch_id=branch_id, status=status), page, lambda c: counts.count_out(db, c))


@router.get("/inventory-counts/{count_id}", response_model=CountDetailOut)
def get_count(count_id: CountId, db: SessionDep, _: StaffOnly) -> CountDetailOut:
    return counts.count_detail_out(db, counts.get_count_or_404(db, count_id))


@router.post("/inventory-counts/{count_id}/scans", response_model=ScansAddedOut, status_code=201)
def add_scans(count_id: CountId, body: ScansIn, request: Request, db: SessionDep, staff: StaffOnly) -> ScansAddedOut:
    count = counts.get_count_or_404(db, count_id)
    scans = counts.add_scans(db, request_now(request), staff.user, count, body.barcodes)
    return ScansAddedOut(
        scans=[AddedScanOut(id=s.id, barcode=s.barcode, copy_id=s.copy_id, result=s.result) for s in scans]
    )


@router.get("/inventory-counts/{count_id}/scans", response_model=Page[ScanOut])
def list_scans(
    count_id: CountId,
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    result: Annotated[ScanResult | None, Query()] = None,
) -> Page[ScanOut]:
    counts.get_count_or_404(db, count_id)
    return paginate(db, counts.scan_list_stmt(count_id, result), page, counts.scan_out)


@router.delete("/inventory-scans/{scan_id}", status_code=204)
def remove_scan(scan_id: ScanId, request: Request, db: SessionDep, staff: StaffOnly) -> Response:
    counts.remove_scan(db, request_now(request), staff.user, counts.get_scan_or_404(db, scan_id))
    return Response(status_code=204)


@router.post("/inventory-counts/{count_id}/close", response_model=CountDetailOut)
def close_count(count_id: CountId, request: Request, db: SessionDep, staff: StaffOnly) -> CountDetailOut:
    count = counts.get_count_or_404(db, count_id)
    closing.close_count(db, request_now(request), staff.user, count)
    return counts.count_detail_out(db, count)


@router.post("/inventory-counts/{count_id}/cancel", response_model=CountDetailOut)
def cancel_count(count_id: CountId, request: Request, db: SessionDep, staff: StaffOnly) -> CountDetailOut:
    count = counts.cancel_count(db, request_now(request), staff.user, counts.get_count_or_404(db, count_id))
    return counts.count_detail_out(db, count)


@router.post("/inventory-counts/{count_id}/apply", response_model=ApplyOut)
def apply_count(count_id: CountId, request: Request, db: SessionDep, staff: StaffOnly) -> ApplyOut:
    count = counts.get_count_or_404(db, count_id)
    marked, found, relocated = closing.apply_count(
        db, request_now(request), staff.user, request.app.state.settings.holidays, count
    )
    return ApplyOut(missing_marked=marked, found=found, relocated=relocated)


@router.get("/inventory-counts/{count_id}/lines", response_model=Page[LineOut])
def list_lines(
    count_id: CountId,
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    outcome: Annotated[Outcome | None, Query()] = None,
) -> Page[LineOut]:
    count = counts.get_count_or_404(db, count_id)
    if count.status not in ("closed", "applied"):
        raise counts.invalid_count_status(count, "reading the lines")
    return paginate_rows(db, closing.line_list_stmt(count_id, outcome), page)


def paginate_rows(db: Session, stmt: sa.Select[Any], page: PageParams) -> Page[LineOut]:
    """The line statement selects several columns, so it is paginated by row."""
    total = db.scalar(sa.select(sa.func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.execute(stmt.limit(page.page_size).offset(page.offset)).all()
    return Page[LineOut](
        items=[closing.line_out(row) for row in rows], page=page.page, page_size=page.page_size, total=total
    )


@router.post("/copies/{copy_id}/found", response_model=CopyOut)
def copy_found(copy_id: CopyId, body: FoundIn, request: Request, db: SessionDep, staff: StaffOnly) -> CopyOut:
    copy = get_copy_or_404(db, copy_id)
    copy = missing.found_copy(
        db, request_now(request), staff.user, request.app.state.settings.holidays, copy, body.branch_id
    )
    return copy_out(copy)


@router.post("/inventory/process", response_model=ProcessOut)
def process(request: Request, db: SessionDep, staff: StaffOnly) -> ProcessOut:
    expired, lost = missing.process(db, request_now(request), staff.user)
    return ProcessOut(expired_counts=expired, marked_lost=lost)
