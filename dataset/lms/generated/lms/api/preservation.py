"""Preservation endpoints (section 31.2)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query, Request

from lms.api.common import patch_fields
from lms.auth.deps import AdminOnly, StaffOnly
from lms.branches.models import Branch
from lms.catalog.service import get_copy_or_404
from lms.core.clock import local_now
from lms.core.db import SessionDep
from lms.core.errors import NotFound, reference_not_found
from lms.core.pagination import Page, PageDep, paginate
from lms.preservation import budgets, jobs, shipments
from lms.preservation import reports as preservation_reports
from lms.preservation import usage
from lms.preservation.schemas import (
    MAX_YEAR,
    MIN_YEAR,
    BudgetIn,
    BudgetOut,
    InspectionIn,
    InspectionOut,
    JobCreateIn,
    JobKind,
    JobOut,
    JobPatchIn,
    JobStatus,
    ProcessOut,
    Provider,
    ReturnIn,
    ShipmentIn,
    ShipmentOut,
    SuggestionsOut,
)

router = APIRouter(tags=["preservation"])

BranchId = Annotated[int, Path(ge=1)]
Year = Annotated[int, Path(ge=MIN_YEAR, le=MAX_YEAR)]
CopyId = Annotated[int, Path(ge=1)]
JobId = Annotated[int, Path(ge=1)]
ShipmentId = Annotated[int, Path(ge=1)]


def _now(request: Request):  # noqa: ANN202
    return local_now(request.app.state.settings.clock)


# --- budgets --------------------------------------------------------------------------------


@router.put("/preservation-budgets/{branch_id}/{year}", response_model=BudgetOut)
def set_budget(
    branch_id: BranchId, year: Year, body: BudgetIn, request: Request, db: SessionDep, admin: AdminOnly
) -> BudgetOut:
    budget = budgets.set_budget(db, _now(request), admin.user, branch_id, year, body.amount)
    return budgets.budget_out(db, budget)


@router.get("/preservation-budgets/{branch_id}/{year}", response_model=BudgetOut)
def get_budget(branch_id: BranchId, year: Year, db: SessionDep, _: StaffOnly) -> BudgetOut:
    budget = usage.budget_of(db, branch_id, year)
    if budget is None:
        raise NotFound(
            f"Branch {branch_id} has no preservation budget for {year}",
            details={"resource": "preservation_budget", "branch_id": branch_id, "year": year},
        )
    return budgets.budget_out(db, budget)


# --- inspections ------------------------------------------------------------------------------


@router.post("/copies/{copy_id}/inspections", response_model=InspectionOut, status_code=201)
def inspect_copy(copy_id: CopyId, body: InspectionIn, request: Request, db: SessionDep, staff: StaffOnly) -> InspectionOut:
    copy = get_copy_or_404(db, copy_id)
    return budgets.inspection_out(budgets.inspect_copy(db, _now(request), staff.user, copy, body.condition, body.note))


@router.get("/copies/{copy_id}/inspections", response_model=Page[InspectionOut])
def list_inspections(copy_id: CopyId, db: SessionDep, _: StaffOnly, page: PageDep) -> Page[InspectionOut]:
    get_copy_or_404(db, copy_id)
    return paginate(db, budgets.inspections_stmt(copy_id), page, budgets.inspection_out)


# --- jobs -------------------------------------------------------------------------------------


@router.post("/repair-jobs", response_model=JobOut, status_code=201)
def create_job(body: JobCreateIn, request: Request, db: SessionDep, staff: StaffOnly) -> JobOut:
    now = _now(request)
    job = jobs.create_job(db, now, staff.user, **body.model_dump())
    return jobs.job_out(db, job, now.date())


@router.get("/repair-jobs", response_model=Page[JobOut])
def list_jobs(
    request: Request,
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    status: Annotated[JobStatus | None, Query()] = None,
    branch_id: Annotated[int | None, Query()] = None,
    provider: Annotated[Provider | None, Query()] = None,
    supplier_id: Annotated[int | None, Query()] = None,
    kind: Annotated[JobKind | None, Query()] = None,
    overdue: Annotated[bool | None, Query()] = None,
    copy_id: Annotated[int | None, Query()] = None,
) -> Page[JobOut]:
    today = _now(request).date()
    stmt = jobs.job_list_stmt(
        today,
        status=status,
        branch_id=branch_id,
        provider=provider,
        supplier_id=supplier_id,
        kind=kind,
        overdue=overdue,
        copy_id=copy_id,
    )
    return paginate(db, stmt, page, lambda job: jobs.job_out(db, job, today))


@router.get("/repair-jobs/{job_id}", response_model=JobOut)
def get_job(job_id: JobId, request: Request, db: SessionDep, _: StaffOnly) -> JobOut:
    return jobs.job_out(db, jobs.get_job_or_404(db, job_id), _now(request).date())


@router.patch("/repair-jobs/{job_id}", response_model=JobOut)
def update_job(job_id: JobId, body: JobPatchIn, request: Request, db: SessionDep, staff: StaffOnly) -> JobOut:
    now = _now(request)
    fields = patch_fields(body)
    job = jobs.update_job(db, now, staff.user, jobs.get_job_or_404(db, job_id), fields)
    return jobs.job_out(db, job, now.date())


@router.post("/repair-jobs/{job_id}/approve", response_model=JobOut)
def approve_job(job_id: JobId, request: Request, db: SessionDep, staff: StaffOnly) -> JobOut:
    now = _now(request)
    job = jobs.approve_job(db, now, staff.user, jobs.get_job_or_404(db, job_id))
    return jobs.job_out(db, job, now.date())


@router.post("/repair-jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: JobId, request: Request, db: SessionDep, staff: StaffOnly) -> JobOut:
    now = _now(request)
    job = jobs.cancel_job(db, now, staff.user, jobs.get_job_or_404(db, job_id))
    return jobs.job_out(db, job, now.date())


@router.post("/repair-jobs/{job_id}/send", response_model=JobOut)
def send_job(job_id: JobId, request: Request, db: SessionDep, staff: StaffOnly) -> JobOut:
    now = _now(request)
    job = jobs.send_job(db, now, staff.user, jobs.get_job_or_404(db, job_id))
    return jobs.job_out(db, job, now.date())


@router.post("/repair-jobs/{job_id}/return", response_model=JobOut)
def return_job(job_id: JobId, body: ReturnIn, request: Request, db: SessionDep, staff: StaffOnly) -> JobOut:
    now = _now(request)
    job = jobs.return_job(
        db,
        now,
        staff.user,
        request.app.state.settings.holidays,
        jobs.get_job_or_404(db, job_id),
        outcome=body.outcome,
        actual_cost=body.actual_cost,
        cost_note=body.cost_note,
    )
    return jobs.job_out(db, job, now.date())


@router.post("/repair-jobs/{job_id}/lost", response_model=JobOut)
def lose_job(job_id: JobId, request: Request, db: SessionDep, staff: StaffOnly) -> JobOut:
    now = _now(request)
    job = jobs.lose_job(db, now, staff.user, jobs.get_job_or_404(db, job_id))
    return jobs.job_out(db, job, now.date())


# --- shipments ----------------------------------------------------------------------------------


@router.post("/repair-shipments", response_model=ShipmentOut, status_code=201)
def create_shipment(body: ShipmentIn, request: Request, db: SessionDep, staff: StaffOnly) -> ShipmentOut:
    shipment = shipments.create_shipment(
        db, _now(request), staff.user, supplier_id=body.supplier_id, job_ids=body.job_ids
    )
    return shipments.shipment_out(db, shipment)


@router.get("/repair-shipments", response_model=Page[ShipmentOut])
def list_shipments(
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    supplier_id: Annotated[int | None, Query()] = None,
    branch_id: Annotated[int | None, Query()] = None,
) -> Page[ShipmentOut]:
    stmt = shipments.shipment_list_stmt(supplier_id, branch_id)
    return paginate(db, stmt, page, lambda shipment: shipments.shipment_out(db, shipment))


@router.get("/repair-shipments/{shipment_id}", response_model=ShipmentOut)
def get_shipment(shipment_id: ShipmentId, db: SessionDep, _: StaffOnly) -> ShipmentOut:
    return shipments.shipment_out(db, shipments.get_shipment_or_404(db, shipment_id))


# --- suggestions and processing -------------------------------------------------------------------


@router.get("/preservation/suggestions", response_model=SuggestionsOut)
def suggestions(branch_id: Annotated[int, Query()], db: SessionDep, _: StaffOnly) -> SuggestionsOut:
    if db.get(Branch, branch_id) is None:
        raise reference_not_found("branch_id", branch_id)
    return SuggestionsOut(items=preservation_reports.suggestions(db, branch_id))


@router.post("/preservation/process", response_model=ProcessOut)
def process(request: Request, db: SessionDep, staff: StaffOnly) -> ProcessOut:
    overdue, newly, expired = jobs.process(db, _now(request), staff.user)
    return ProcessOut(overdue=overdue, newly_overdue=newly, expired_requests=expired)
