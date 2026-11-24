"""Printing and copying endpoints (section 37.3)."""

from __future__ import annotations

import datetime
import re
from typing import Annotated

from fastapi import APIRouter, Path, Query, Request
from sqlalchemy.orm import Session

from lms.api.common import (
    acting_member_id,
    ensure_own_or_staff,
    optional_date,
    patch_fields,
    report_range,
    request_now,
)
from lms.auth.deps import AdminOnly, CurrentPrincipal, Principal, StaffOnly
from lms.core.db import SessionDep, get_reference
from lms.core.errors import ValidationFailed
from lms.core.money import format_amount
from lms.core.pagination import Page, PageDep, paginate, paginate_sequence
from lms.members.models import Member
from lms.members.service import get_member_or_404
from lms.printing import jobs, packs, printers, quota
from lms.printing import reports as printing_reports
from lms.printing.models import Printer, PrintJob
from lms.printing.rules import FREE_PAGES, MAX_REPORT_DAYS
from lms.printing.schemas import (
    FailIn,
    JobStatus,
    PackOut,
    PrinterCreateIn,
    PrinterOut,
    PrinterPatchIn,
    PrinterStatus,
    PrintingReportOut,
    PrintJobIn,
    PrintJobOut,
    ProcessOut,
    QuotaOut,
    RefillIn,
    ReleaseByCardIn,
    ReleaseByCardOut,
    job_out,
    pack_out,
    printer_out,
)

router = APIRouter(tags=["printing"])

PrinterId = Annotated[int, Path(ge=1)]
JobId = Annotated[int, Path(ge=1)]
MemberId = Annotated[int, Path(ge=1)]

_MONTH = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def _own_or_staff(principal: Principal, member_id: int) -> None:
    ensure_own_or_staff(principal, member_id, "print jobs and packs")


def _job_out(db: Session, job: PrintJob) -> PrintJobOut:
    printer = db.get(Printer, job.printer_id)
    assert printer is not None
    return job_out(job, printer, jobs.job_amount(db, job))


# --- printers ------------------------------------------------------------------------------


@router.post("/printers", response_model=PrinterOut, status_code=201)
def create_printer(body: PrinterCreateIn, request: Request, db: SessionDep, admin: AdminOnly) -> PrinterOut:
    printer = printers.create_printer(db, request_now(request), admin.user, **body.model_dump())
    return printer_out(printer)


@router.get("/printers", response_model=Page[PrinterOut])
def list_printers(
    db: SessionDep,
    _: CurrentPrincipal,
    page: PageDep,
    branch_id: Annotated[int | None, Query()] = None,
    status: Annotated[PrinterStatus | None, Query()] = None,
    color: Annotated[bool | None, Query()] = None,
    low_paper: Annotated[bool | None, Query()] = None,
) -> Page[PrinterOut]:
    stmt = printers.printer_list_stmt(branch_id=branch_id, status=status, color=color, low_paper=low_paper)
    return paginate(db, stmt, page, printer_out)


@router.get("/printers/{printer_id}", response_model=PrinterOut)
def get_printer(printer_id: PrinterId, db: SessionDep, _: CurrentPrincipal) -> PrinterOut:
    return printer_out(printers.get_printer_or_404(db, printer_id))


@router.patch("/printers/{printer_id}", response_model=PrinterOut)
def update_printer(
    printer_id: PrinterId, body: PrinterPatchIn, request: Request, db: SessionDep, admin: AdminOnly
) -> PrinterOut:
    printer = printers.get_printer_or_404(db, printer_id)
    fields = patch_fields(body)
    return printer_out(printers.update_printer(db, request_now(request), admin.user, printer, fields))


@router.post("/printers/{printer_id}/refill", response_model=PrinterOut)
def refill_printer(printer_id: PrinterId, body: RefillIn, request: Request, db: SessionDep, staff: StaffOnly) -> PrinterOut:
    printer = printers.get_printer_or_404(db, printer_id)
    return printer_out(printers.refill(db, request_now(request), staff.user, printer, body.sheets))


# --- print jobs ----------------------------------------------------------------------------


@router.post("/print-jobs", response_model=PrintJobOut, status_code=201)
def send_job(body: PrintJobIn, request: Request, db: SessionDep, principal: CurrentPrincipal) -> PrintJobOut:
    member_id = acting_member_id(principal, body.member_id, "print for themselves")
    printer = get_reference(db, Printer, "printer_id", body.printer_id)
    member = get_reference(db, Member, "member_id", member_id)
    job = jobs.send_job(
        db,
        request_now(request),
        principal.user,
        member,
        printer,
        title=body.title,
        pages=body.pages,
        copies=body.copies,
        color=body.color,
        duplex=body.duplex,
    )
    return _job_out(db, job)


@router.get("/print-jobs", response_model=Page[PrintJobOut])
def list_jobs(
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    status: Annotated[JobStatus | None, Query()] = None,
    printer_id: Annotated[int | None, Query()] = None,
    first: Annotated[str | None, Query(alias="from")] = None,
    to: Annotated[str | None, Query()] = None,
    member_id: Annotated[int | None, Query()] = None,
    branch_id: Annotated[int | None, Query()] = None,
) -> Page[PrintJobOut]:
    stmt = jobs.job_list_stmt(
        member_id=member_id,
        status=status,
        printer_id=printer_id,
        branch_id=branch_id,
        first=optional_date("from", first),
        last=optional_date("to", to),
    )
    return paginate(db, stmt, page, lambda j: _job_out(db, j))


@router.get("/print-jobs/{job_id}", response_model=PrintJobOut)
def get_job(job_id: JobId, db: SessionDep, principal: CurrentPrincipal) -> PrintJobOut:
    job = jobs.get_job_or_404(db, job_id)
    _own_or_staff(principal, job.member_id)
    return _job_out(db, job)


@router.get("/members/{member_id}/print-jobs", response_model=Page[PrintJobOut])
def list_member_jobs(
    member_id: MemberId,
    db: SessionDep,
    principal: CurrentPrincipal,
    page: PageDep,
    status: Annotated[JobStatus | None, Query()] = None,
    printer_id: Annotated[int | None, Query()] = None,
    first: Annotated[str | None, Query(alias="from")] = None,
    to: Annotated[str | None, Query()] = None,
) -> Page[PrintJobOut]:
    start = optional_date("from", first)
    end = optional_date("to", to)
    member = get_member_or_404(db, member_id)
    _own_or_staff(principal, member.id)
    stmt = jobs.job_list_stmt(member_id=member.id, status=status, printer_id=printer_id, first=start, last=end)
    return paginate(db, stmt, page, lambda j: _job_out(db, j))


@router.post("/print-jobs/release-by-card", response_model=ReleaseByCardOut)
def release_by_card(body: ReleaseByCardIn, request: Request, db: SessionDep, staff: StaffOnly) -> ReleaseByCardOut:
    printer = get_reference(db, Printer, "printer_id", body.printer_id)
    return jobs.release_by_card(
        db, request_now(request), staff.user, request.app.state.settings.holidays, printer, body.card_no
    )


@router.post("/print-jobs/{job_id}/release", response_model=PrintJobOut)
def release_job(job_id: JobId, request: Request, db: SessionDep, principal: CurrentPrincipal) -> PrintJobOut:
    job = jobs.get_job_or_404(db, job_id)
    _own_or_staff(principal, job.member_id)
    own = principal.user.role == "member"  # LIB-PRT-15: check (5) does not apply to staff
    released = jobs.release_job(
        db, request_now(request), principal.user, request.app.state.settings.holidays, job, check_inside=own
    )
    return _job_out(db, released)


@router.post("/print-jobs/{job_id}/cancel", response_model=PrintJobOut)
def cancel_job(job_id: JobId, request: Request, db: SessionDep, principal: CurrentPrincipal) -> PrintJobOut:
    job = jobs.get_job_or_404(db, job_id)
    _own_or_staff(principal, job.member_id)
    return _job_out(db, jobs.cancel(db, request_now(request), principal.user, job))


@router.post("/print-jobs/{job_id}/fail", response_model=PrintJobOut)
def fail_job(job_id: JobId, body: FailIn, request: Request, db: SessionDep, staff: StaffOnly) -> PrintJobOut:
    job = jobs.get_job_or_404(db, job_id)
    return _job_out(db, jobs.fail_job(db, request_now(request), staff.user, job, body.reason))


@router.post("/printing/process", response_model=ProcessOut)
def process(request: Request, db: SessionDep, staff: StaffOnly) -> ProcessOut:
    return jobs.process(db, request_now(request), staff.user)


# --- quota and packs -----------------------------------------------------------------------


@router.get("/members/{member_id}/print-quota", response_model=QuotaOut)
def get_quota(
    member_id: MemberId,
    request: Request,
    db: SessionDep,
    principal: CurrentPrincipal,
    month: Annotated[str | None, Query()] = None,
) -> QuotaOut:
    today = request_now(request).date()
    first = today.replace(day=1)
    if month is not None:
        match = _MONTH.match(month.strip())
        if match is None:
            raise ValidationFailed.single("month", "expected a month in the form YYYY-MM")
        first = datetime.date(int(match.group(1)), int(match.group(2)), 1)
        if first > today:
            raise ValidationFailed.single("month", "the month must not be after the current month")
    member = get_member_or_404(db, member_id)
    _own_or_staff(principal, member.id)
    start, end = quota.month_bounds(first)
    total = FREE_PAGES[member.membership_type]
    used = quota.free_pages_used(db, member.id, first)
    return QuotaOut(
        month=first.strftime("%Y-%m"),
        membership_type=member.membership_type,
        free_pages=total,
        free_pages_used=used,
        free_pages_left=max(0, total - used),
        pack_pages_left=quota.pack_pages_left(db, member.id),
        pages_printed=quota.pages_printed(db, member.id, start, end),
        amount_charged=format_amount(quota.amount_charged(db, member.id, first)),
    )


@router.post("/members/{member_id}/print-packs", response_model=PackOut, status_code=201)
def buy_pack(member_id: MemberId, request: Request, db: SessionDep, staff: StaffOnly) -> PackOut:
    member = get_member_or_404(db, member_id)
    return pack_out(packs.buy_pack(db, request_now(request), staff.user, member))


@router.get("/members/{member_id}/print-packs", response_model=Page[PackOut])
def list_packs(
    member_id: MemberId,
    db: SessionDep,
    principal: CurrentPrincipal,
    page: PageDep,
    with_pages_left: Annotated[bool | None, Query()] = None,
) -> Page[PackOut]:
    member = get_member_or_404(db, member_id)
    _own_or_staff(principal, member.id)
    return paginate(db, packs.pack_list_stmt(member.id, with_pages_left), page, pack_out)


# --- report --------------------------------------------------------------------------------


@router.get("/reports/printing", response_model=Page[PrintingReportOut])
def printing_report(
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    first: Annotated[str | None, Query(alias="from")] = None,
    to: Annotated[str | None, Query()] = None,
    branch_id: Annotated[int | None, Query()] = None,
) -> Page[PrintingReportOut]:
    start, end = report_range(first, to, MAX_REPORT_DAYS)
    return paginate_sequence(printing_reports.printing_report(db, start, end, branch_id), page)
