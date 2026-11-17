"""Print jobs: send, cancel, release, fail, expire (LIB-PRT-07 to LIB-PRT-26, LIB-PRT-31, LIB-PRT-40)."""

from __future__ import annotations

import datetime
from collections.abc import Container
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.access.cards import get_card_or_404
from lms.access.gate import branch_open_now
from lms.access.usage import open_visit_of_member
from lms.audit.service import record
from lms.auth.models import User
from lms.core.errors import Conflict, NotFound
from lms.core.money import ZERO, format_amount
from lms.fines.models import Fee
from lms.fines.service import accrued_late_fees, create_fee, outstanding_fees
from lms.members.models import Member
from lms.notifications.service import notify_printing
from lms.printing import quota
from lms.printing.models import Printer, PrintJob, PrintJobPackUse, PrintPack
from lms.printing.rules import (
    DAILY_PAGE_LIMIT,
    DEBT_BLOCK,
    FAIL_WINDOW,
    FAILED_WAIVE_REASON,
    QUEUE_EXPIRY,
    QUEUE_LIMIT,
    sheets_of,
)
from lms.printing.schemas import ProcessOut, RefusedOut, ReleaseByCardOut
from lms.printing.usage import cancel_job


def get_job_or_404(db: Session, job_id: int) -> PrintJob:
    job = db.get(PrintJob, job_id)
    if job is None:
        raise NotFound(f"Print job {job_id} does not exist", details={"resource": "print_job", "id": job_id})
    return job


def job_amount(db: Session, job: PrintJob) -> Decimal:
    """``amount`` of LIB-PRT-11: the amount of the job's fee, or ``0.00``."""
    if job.fee_id is None:
        return ZERO
    fee = db.get(Fee, job.fee_id)
    return fee.amount if fee is not None else ZERO


def job_list_stmt(
    *,
    member_id: int | None = None,
    status: str | None = None,
    printer_id: int | None = None,
    branch_id: int | None = None,
    first: datetime.date | None = None,
    last: datetime.date | None = None,
) -> sa.Select[tuple[PrintJob]]:
    """LIB-PRT-11: newest first; ``first`` and ``last`` are inclusive local dates of ``submitted_at``."""
    stmt = sa.select(PrintJob).order_by(PrintJob.submitted_at.desc(), PrintJob.id.desc())
    if member_id is not None:
        stmt = stmt.where(PrintJob.member_id == member_id)
    if status is not None:
        stmt = stmt.where(PrintJob.status == status)
    if printer_id is not None:
        stmt = stmt.where(PrintJob.printer_id == printer_id)
    if branch_id is not None:
        stmt = stmt.where(PrintJob.printer_id.in_(sa.select(Printer.id).where(Printer.branch_id == branch_id)))
    if first is not None:
        stmt = stmt.where(PrintJob.submitted_at >= quota.day_bounds(first)[0])
    if last is not None and last < datetime.date.max:
        stmt = stmt.where(PrintJob.submitted_at < quota.day_bounds(last)[1])
    return stmt


# --- send and cancel -----------------------------------------------------------------------


def send_job(
    db: Session,
    now: datetime.datetime,
    actor: User,
    member: Member,
    printer: Printer,
    *,
    title: str,
    pages: int,
    copies: int,
    color: bool,
    duplex: bool,
) -> PrintJob:
    """LIB-PRT-07 to LIB-PRT-10."""
    today = now.date()
    if member.status == "passive":
        raise Conflict("The member is passive", code="MEMBER_PASSIVE")
    if today > member.valid_until:
        raise Conflict("The membership has expired", code="MEMBERSHIP_EXPIRED")
    if printer.status != "active":
        raise Conflict("The printer is not available", code="PRINTER_UNAVAILABLE", details={"status": printer.status})
    if color and not printer.color:
        raise Conflict("The printer cannot print in color", code="PRINTER_NO_COLOR")
    if duplex and not printer.duplex:
        raise Conflict("The printer cannot print on both sides", code="PRINTER_NO_DUPLEX")
    if quota.queued_count(db, member.id) >= QUEUE_LIMIT:
        raise Conflict("The member already has the most queued jobs allowed", code="PRINT_QUEUE_FULL", details={"limit": QUEUE_LIMIT})
    start, end = quota.day_bounds(today)
    used = quota.pages_printed(db, member.id, start, end) + quota.queued_pages(db, member.id)
    if used + pages * copies > DAILY_PAGE_LIMIT:
        raise Conflict(
            "The daily page limit would be exceeded",
            code="DAILY_PAGE_LIMIT",
            details={"remaining": max(0, DAILY_PAGE_LIMIT - used)},
        )
    job = PrintJob(
        member_id=member.id,
        printer_id=printer.id,
        title=title,
        pages=pages,
        copies=copies,
        color=color,
        duplex=duplex,
        status="queued",
        submitted_at=now,
        sheets=sheets_of(pages, copies, duplex),
    )
    db.add(job)
    db.flush()
    record(
        db,
        at=now,
        event="print_job_submitted",
        actor_user_id=actor.id,
        entity_type="print_job",
        entity_id=job.id,
        details={
            "member_id": member.id,
            "printer_id": printer.id,
            "title": title,
            "pages": pages,
            "copies": copies,
            "color": color,
            "duplex": duplex,
            "sheets": job.sheets,
        },
    )
    return job


def cancel(db: Session, now: datetime.datetime, actor: User, job: PrintJob) -> PrintJob:
    """LIB-PRT-12."""
    if job.status != "queued":
        raise Conflict("The print job is not queued", code="PRINT_JOB_NOT_QUEUED", details={"status": job.status})
    cancel_job(db, now, actor.id, job, None)
    return job


# --- release -------------------------------------------------------------------------------


def release_job(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    job: PrintJob,
    *,
    check_inside: bool,
) -> PrintJob:
    """LIB-PRT-13 to LIB-PRT-18. Every check runs before the first change, so a refused job is left untouched."""
    if job.status != "queued":
        raise Conflict("The print job is not queued", code="PRINT_JOB_NOT_QUEUED", details={"status": job.status})
    member = db.get(Member, job.member_id)
    printer = db.get(Printer, job.printer_id)
    assert member is not None and printer is not None
    if member.status == "passive":
        raise Conflict("The member is passive", code="MEMBER_PASSIVE")
    if printer.status != "active":
        raise Conflict("The printer is not available", code="PRINTER_UNAVAILABLE", details={"status": printer.status})
    if not branch_open_now(db, now, holidays, printer.branch_id):
        raise Conflict("The branch is not open now", code="BRANCH_NOT_OPEN", details={"branch_id": printer.branch_id})
    if check_inside:
        visit = open_visit_of_member(db, member.id)
        if visit is None or visit.branch_id != printer.branch_id:
            raise Conflict(
                "The member is not inside the branch of the printer",
                code="NOT_IN_BRANCH",
                details={"branch_id": printer.branch_id},
            )
    if job.sheets > printer.paper_left:
        raise Conflict("The printer is out of paper", code="OUT_OF_PAPER", details={"paper_left": printer.paper_left})
    first = now.date().replace(day=1)
    payment = quota.plan_payment(db, member.id, member.membership_type, first, job.pages, job.copies, job.color)
    if payment.amount > ZERO:  # a job paid entirely from free pages or packs is printed with any debt
        debt = outstanding_fees(db, member.id) + accrued_late_fees(db, member.id, now, holidays)
        if debt + payment.amount >= DEBT_BLOCK:
            raise Conflict(
                "The member's debt would reach the limit",
                code="MEMBER_BLOCKED_BY_DEBT",
                details={"amount": format_amount(payment.amount)},
            )

    printer.paper_left -= job.sheets
    job.status = "printed"
    job.released_at = now
    job.free_pages = payment.free_pages
    job.pack_pages = payment.pack_pages
    job.charged_pages = payment.charged_pages
    for pack_id, pages in payment.packs:
        pack = db.get(PrintPack, pack_id)
        assert pack is not None
        pack.pages_left -= pages
        db.add(PrintJobPackUse(job_id=job.id, pack_id=pack_id, pages=pages))
    if payment.charged_pages > 0:
        fee = create_fee(
            db,
            now,
            actor,
            member_id=member.id,
            loan_id=None,
            kind="printing",
            amount=payment.amount,
            print_job_id=job.id,
        )
        job.fee_id = fee.id
    record(
        db,
        at=now,
        event="print_job_released",
        actor_user_id=actor.id,
        entity_type="print_job",
        entity_id=job.id,
        details={
            "member_id": member.id,
            "printer_id": printer.id,
            "sheets": job.sheets,
            "free_pages": job.free_pages,
            "pack_pages": job.pack_pages,
            "charged_pages": job.charged_pages,
            "fee_id": job.fee_id,
            "amount": format_amount(payment.amount),
        },
    )
    return job


def release_by_card(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    printer: Printer,
    card_no: str,
) -> ReleaseByCardOut:
    """LIB-PRT-40, LIB-PRT-41."""
    card = get_card_or_404(db, card_no)
    if card.status != "active":
        raise Conflict("The card is not active", code="CARD_NOT_ACTIVE", details={"status": card.status})
    stmt = (
        sa.select(PrintJob)
        .where(PrintJob.member_id == card.member_id, PrintJob.printer_id == printer.id, PrintJob.status == "queued")
        .order_by(PrintJob.submitted_at, PrintJob.id)
    )
    released: list[int] = []
    refused: list[RefusedOut] = []
    for job in list(db.scalars(stmt)):
        try:
            release_job(db, now, actor, holidays, job, check_inside=True)
        except Conflict as error:
            refused.append(RefusedOut(job_id=job.id, code=error.code))
        else:
            released.append(job.id)
    return ReleaseByCardOut(released=released, refused=refused)


# --- failed prints -------------------------------------------------------------------------


def fail_job(db: Session, now: datetime.datetime, actor: User, job: PrintJob, reason: str) -> PrintJob:
    """LIB-PRT-23 to LIB-PRT-26."""
    if job.status != "printed":
        raise Conflict("The print job is not printed", code="PRINT_JOB_NOT_PRINTED", details={"status": job.status})
    assert job.released_at is not None
    if now > job.released_at + FAIL_WINDOW:
        raise Conflict("The 24 hours for reporting a failed print have passed", code="FAIL_WINDOW_CLOSED")
    job.status = "failed"
    job.failed_reason = reason
    fee_result = "none"
    refund_pending = ZERO
    fee = db.get(Fee, job.fee_id) if job.fee_id is not None else None
    if fee is not None:
        if fee.status == "open" and fee.paid_amount == ZERO:
            fee.status = "waived"
            fee.waived_by = actor.id
            fee.waived_at = now
            fee.waive_reason = FAILED_WAIVE_REASON
            fee_result = "waived"
        else:
            refund_pending = fee.paid_amount
            fee_result = "kept"
    # the free pages return to their month because only printed jobs count; the pack pages go back to their packs
    uses = db.scalars(sa.select(PrintJobPackUse).where(PrintJobPackUse.job_id == job.id))
    for use in list(uses):
        pack = db.get(PrintPack, use.pack_id)
        assert pack is not None
        pack.pages_left += use.pages
    record(
        db,
        at=now,
        event="print_job_failed",
        actor_user_id=actor.id,
        entity_type="print_job",
        entity_id=job.id,
        details={
            "member_id": job.member_id,
            "reason": reason,
            "fee_id": job.fee_id,
            "fee": fee_result,
            "refund_pending": format_amount(refund_pending),
            "free_pages": job.free_pages,
            "pack_pages": job.pack_pages,
        },
    )
    notify_printing(
        db,
        now,
        job.member_id,
        "print_job_failed",
        f'Your print job "{job.title}" failed and was refunded.',
        print_job_id=job.id,
    )
    return job


# --- processing ----------------------------------------------------------------------------


def process(db: Session, now: datetime.datetime, actor: User) -> ProcessOut:
    """LIB-PRT-31, LIB-PRT-32."""
    stmt = (
        sa.select(PrintJob)
        .where(PrintJob.status == "queued", PrintJob.submitted_at <= now - QUEUE_EXPIRY)
        .order_by(PrintJob.id)
    )
    jobs = list(db.scalars(stmt))
    for job in jobs:
        job.status = "expired"
        notify_printing(
            db,
            now,
            job.member_id,
            "print_job_expired",
            f'Your print job "{job.title}" expired because it was not released within 24 hours.',
            print_job_id=job.id,
        )
    record(
        db,
        at=now,
        event="printing_processed",
        actor_user_id=actor.id,
        entity_type="printing",
        entity_id=None,
        details={"jobs_expired": len(jobs)},
    )
    return ProcessOut(jobs_expired=len(jobs))
