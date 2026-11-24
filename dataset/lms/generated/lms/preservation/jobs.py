"""Repair jobs (LIB-PRE-08 to LIB-PRE-18, LIB-PRE-21 to LIB-PRE-25)."""

from __future__ import annotations

import datetime
from collections.abc import Container
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import changes, record
from lms.auth.models import User
from lms.branches.models import Branch
from lms.catalog.models import Book, Copy
from lms.catalog.release import release_copy
from lms.catalog.status import invalid_status, set_status
from lms.core.db import get_or_404
from lms.core.errors import Conflict, Forbidden, ValidationFailed
from lms.core.money import format_amount
from lms.core.timeutil import format_datetime
from lms.loans.models import Loan
from lms.preservation import rules, usage
from lms.preservation.models import RepairJob
from lms.preservation.schemas import JobOut, check_supplier_rule
from lms.purchasing.models import Supplier

SENDABLE_COPY_STATUSES = ("damaged", "available")


def get_job_or_404(db: Session, job_id: int) -> RepairJob:
    return get_or_404(db, RepairJob, job_id, "Repair job", "repair_job")


def invalid_job_status(job: RepairJob, action: str) -> Conflict:
    return Conflict(
        f"Repair job {job.id} has status {job.status}: {action} is not allowed",
        code="INVALID_JOB_STATUS",
        details={"id": job.id, "status": job.status},
    )


def _date(value: datetime.date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _datetime(value: datetime.datetime | None) -> str | None:
    return format_datetime(value) if value is not None else None


def job_out(db: Session, job: RepairJob, today: datetime.date) -> JobOut:
    copy = db.get(Copy, job.copy_id)
    assert copy is not None
    title = db.scalar(sa.select(Book.title).where(Book.id == copy.book_id)) or ""
    claim = format_amount(copy.price) if job.status == "lost" and job.provider == "supplier" else None
    return JobOut(
        id=job.id,
        copy_id=job.copy_id,
        barcode=copy.barcode,
        book_title=title,
        branch_id=job.branch_id,
        kind=job.kind,
        provider=job.provider,
        supplier_id=job.supplier_id,
        priority=job.priority,
        estimated_cost=format_amount(job.estimated_cost),
        actual_cost=format_amount(job.actual_cost) if job.actual_cost is not None else None,
        status=job.status,
        outcome=job.outcome,
        loan_id=job.loan_id,
        shipment_id=job.shipment_id,
        note=job.note,
        cost_note=job.cost_note,
        cost_overrun=job.cost_overrun,
        requested_at=format_datetime(job.requested_at),
        approved_at=_datetime(job.approved_at),
        sent_at=_datetime(job.sent_at),
        returned_at=_datetime(job.returned_at),
        due_back=_date(job.due_back),
        cancel_reason=job.cancel_reason,
        overdue_marked_at=_datetime(job.overdue_marked_at),
        is_overdue=job.is_overdue(today),
        claim_amount=claim,
    )


def _unknown(field: str, what: str, value: int) -> ValidationFailed:
    return ValidationFailed.single(field, f"{what} {value} does not exist")


def _require_supplier(db: Session, supplier_id: int | None) -> Supplier | None:
    if supplier_id is None:
        return None
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise _unknown("supplier_id", "supplier", supplier_id)
    return supplier


def _check_supplier_active(supplier: Supplier | None) -> None:
    if supplier is not None and not supplier.is_active:
        raise Conflict(
            f"Supplier {supplier.id} is inactive",
            code="SUPPLIER_INACTIVE",
            details={"field": "supplier_id", "id": supplier.id},
        )


def _damage_loan_id(db: Session, copy: Copy) -> int | None:
    """LIB-PRE-11."""
    if copy.status != "damaged":
        return None
    loan = db.scalars(sa.select(Loan).where(Loan.copy_id == copy.id).order_by(Loan.id.desc()).limit(1)).first()
    if loan is not None and loan.status == "returned" and loan.condition_on_return == "damaged":
        return loan.id
    return None


def _details(job: RepairJob) -> dict[str, Any]:
    return {
        "copy_id": job.copy_id,
        "branch_id": job.branch_id,
        "kind": job.kind,
        "provider": job.provider,
        "supplier_id": job.supplier_id,
        "priority": job.priority,
        "estimated_cost": format_amount(job.estimated_cost),
    }


def _emit(
    db: Session, now: datetime.datetime, actor: User, event: str, job: RepairJob, **extra: Any
) -> None:
    record(
        db,
        at=now,
        event=event,
        actor_user_id=actor.id,
        entity_type="repair_job",
        entity_id=job.id,
        details={**_details(job), **extra},
    )


def create_job(
    db: Session,
    now: datetime.datetime,
    actor: User,
    *,
    copy_id: int,
    kind: str,
    provider: str,
    supplier_id: int | None,
    priority: str,
    estimated_cost: Decimal,
    note: str,
) -> RepairJob:
    """LIB-PRE-08, LIB-PRE-09, LIB-PRE-11."""
    problems: list[dict[str, str]] = []
    copy = db.get(Copy, copy_id)
    if copy is None:
        problems.append({"field": "copy_id", "problem": f"copy {copy_id} does not exist"})
    supplier = db.get(Supplier, supplier_id) if supplier_id is not None else None
    if supplier_id is not None and supplier is None:
        problems.append({"field": "supplier_id", "problem": f"supplier {supplier_id} does not exist"})
    if problems:
        raise ValidationFailed(problems)
    assert copy is not None

    if copy.status not in SENDABLE_COPY_STATUSES:
        raise invalid_status(copy, "a repair job")
    job_id = usage.open_job_id(db, copy.id)
    if job_id is not None:
        raise Conflict(
            f"Copy {copy.id} has an open repair job", code="COPY_HAS_REPAIR_JOB", details={"job_id": job_id}
        )
    _check_supplier_active(supplier)
    assert copy.current_branch_id is not None
    branch = db.get(Branch, copy.current_branch_id)
    assert branch is not None
    if not branch.is_active:
        raise Conflict(
            f"Branch {branch.code} is inactive",
            code="BRANCH_INACTIVE",
            details={"field": "copy_id", "id": branch.id},
        )

    job = RepairJob(
        copy_id=copy.id,
        branch_id=copy.current_branch_id,
        kind=kind,
        provider=provider,
        supplier_id=supplier_id,
        priority=priority,
        estimated_cost=estimated_cost,
        status="requested",
        loan_id=_damage_loan_id(db, copy),
        note=note,
        requested_at=now,
    )
    db.add(job)
    db.flush()
    _emit(db, now, actor, "repair_job_created", job, loan_id=job.loan_id)
    return job


def update_job(db: Session, now: datetime.datetime, actor: User, job: RepairJob, fields: dict[str, Any]) -> RepairJob:
    """LIB-PRE-10."""
    provider = fields.get("provider", job.provider)
    supplier_id = fields["supplier_id"] if "supplier_id" in fields else job.supplier_id
    try:
        check_supplier_rule(provider, supplier_id)
    except ValueError as exc:
        raise ValidationFailed.single("supplier_id", str(exc)) from None
    supplier = _require_supplier(db, supplier_id)
    if job.status != "requested":
        raise invalid_job_status(job, "change")
    _check_supplier_active(supplier)

    values = dict(fields)
    old = {k: getattr(job, k) for k in values}
    diff = changes(old, values)
    for name, value in values.items():
        setattr(job, name, value)
    shown = {
        k: {f: (format_amount(v) if k == "estimated_cost" else v) for f, v in d.items()} for k, d in diff.items()
    }
    _emit(db, now, actor, "repair_job_updated", job, changes=shown)
    return job


def approve_job(db: Session, now: datetime.datetime, actor: User, job: RepairJob) -> RepairJob:
    """LIB-PRE-12, LIB-PRE-13."""
    if job.estimated_cost > rules.APPROVAL_LIMIT and actor.role != "admin":
        raise Forbidden("Only an admin approves a job above 500.00")
    if job.status != "requested":
        raise invalid_job_status(job, "approval")
    year = now.year
    budget = usage.budget_of(db, job.branch_id, year)
    if budget is None:
        raise Conflict(
            "The branch has no preservation budget for this year",
            code="NO_PRESERVATION_BUDGET",
            details={"branch_id": job.branch_id, "year": year},
        )
    committed, spent = usage.budget_totals(db, job.branch_id, year)
    available = budget.amount - committed - spent
    limit = available + (budget.amount * rules.URGENT_MARGIN if job.priority == "urgent" else 0)
    if job.estimated_cost > limit:
        raise Conflict(
            "The estimated cost exceeds the available budget",
            code="BUDGET_EXCEEDED",
            details={"available": format_amount(available)},
        )
    job.status = "approved"
    job.approved_at = now
    _emit(db, now, actor, "repair_job_approved", job, budget_year=year)
    return job


def cancel_job(db: Session, now: datetime.datetime, actor: User, job: RepairJob) -> RepairJob:
    """LIB-PRE-15."""
    if job.status not in ("requested", "approved"):
        raise invalid_job_status(job, "cancellation")
    job.status = "cancelled"
    job.cancel_reason = "staff_request"
    _emit(db, now, actor, "repair_job_cancelled", job, cancel_reason="staff_request")
    return job


def start_repair(db: Session, now: datetime.datetime, job: RepairJob, shipment_id: int | None = None) -> None:
    """The effects of LIB-PRE-16 on an ``approved`` job: it is sent and its copy goes to repair."""
    copy = db.get(Copy, job.copy_id)
    assert copy is not None
    if copy.status not in SENDABLE_COPY_STATUSES:
        raise invalid_status(copy, "repair")
    set_status(copy, "in_repair")
    job.status = "sent"
    job.sent_at = now
    job.shipment_id = shipment_id
    job.due_back = rules.due_back_for(now.date(), job.kind, job.provider, job.priority)


def send_job(db: Session, now: datetime.datetime, actor: User, job: RepairJob) -> RepairJob:
    """LIB-PRE-16."""
    if job.status != "approved":
        raise invalid_job_status(job, "sending")
    if job.provider == "supplier":
        raise Conflict(
            "A supplier job is sent in a shipment", code="SHIPMENT_REQUIRED", details={"id": job.id}
        )
    start_repair(db, now, job)
    _emit(db, now, actor, "repair_job_sent", job, due_back=_date(job.due_back))
    return job


def return_job(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    job: RepairJob,
    *,
    outcome: str,
    actual_cost: Decimal,
    cost_note: str,
) -> RepairJob:
    """LIB-PRE-21, LIB-PRE-22."""
    overrun = actual_cost > job.estimated_cost * rules.OVERRUN_FACTOR
    if overrun and not cost_note:
        raise ValidationFailed.single("cost_note", "cost_note is required when the actual cost is over 120 % of the estimate")
    if job.status != "sent":
        raise invalid_job_status(job, "return")
    copy = db.get(Copy, job.copy_id)
    assert copy is not None
    job.status = "returned"
    job.returned_at = now
    job.outcome = outcome
    job.actual_cost = actual_cost
    job.cost_note = cost_note
    job.cost_overrun = overrun
    _emit(
        db,
        now,
        actor,
        "repair_job_returned",
        job,
        outcome=outcome,
        actual_cost=format_amount(actual_cost),
        cost_overrun=overrun,
    )
    if outcome == "repaired":
        copy.condition = "good"
        release_copy(db, copy, now, holidays, actor.id)
    else:
        set_status(copy, "damaged")
    return job


def lose_job(db: Session, now: datetime.datetime, actor: User, job: RepairJob) -> RepairJob:
    """LIB-PRE-23."""
    if job.status != "sent":
        raise invalid_job_status(job, "loss")
    copy = db.get(Copy, job.copy_id)
    assert copy is not None
    job.status = "lost"
    set_status(copy, "lost")
    copy.current_branch_id = None
    _emit(
        db,
        now,
        actor,
        "repair_job_lost",
        job,
        claim_amount=format_amount(copy.price) if job.provider == "supplier" else None,
    )
    return job


def job_list_stmt(
    today: datetime.date,
    *,
    status: str | None = None,
    branch_id: int | None = None,
    provider: str | None = None,
    supplier_id: int | None = None,
    kind: str | None = None,
    overdue: bool | None = None,
    copy_id: int | None = None,
) -> sa.Select[tuple[RepairJob]]:
    """LIB-PRE-24."""
    stmt = sa.select(RepairJob).order_by(RepairJob.id.desc())
    for column, value in (
        (RepairJob.status, status),
        (RepairJob.branch_id, branch_id),
        (RepairJob.provider, provider),
        (RepairJob.supplier_id, supplier_id),
        (RepairJob.kind, kind),
        (RepairJob.copy_id, copy_id),
    ):
        if value is not None:
            stmt = stmt.where(column == value)
    if overdue is not None:
        is_overdue = sa.and_(RepairJob.status == "sent", RepairJob.due_back < today)
        stmt = stmt.where(is_overdue if overdue else sa.not_(is_overdue))
    return stmt


def process(db: Session, now: datetime.datetime, actor: User) -> tuple[int, int, int]:
    """LIB-PRE-25: ``(overdue, newly_overdue, expired_requests)``."""
    today = now.date()
    overdue = db.scalars(
        sa.select(RepairJob).where(RepairJob.status == "sent", RepairJob.due_back < today).order_by(RepairJob.id)
    ).all()
    newly = [job for job in overdue if job.overdue_marked_at is None]
    for job in newly:
        job.overdue_marked_at = now
    cutoff = now - datetime.timedelta(days=rules.REQUEST_EXPIRY_DAYS)
    stale = db.scalars(
        sa.select(RepairJob)
        .where(RepairJob.status == "requested", RepairJob.requested_at < cutoff)
        .order_by(RepairJob.id)
    ).all()
    for job in stale:
        job.status = "cancelled"
        job.cancel_reason = "expired"
    record(
        db,
        at=now,
        event="preservation_processed",
        actor_user_id=actor.id,
        entity_type="repair_job",
        entity_id=None,
        details={
            "overdue": len(overdue),
            "newly_overdue": len(newly),
            "expired_requests": len(stale),
            "newly_overdue_job_ids": [j.id for j in newly],
            "expired_job_ids": [j.id for j in stale],
        },
    )
    return len(overdue), len(newly), len(stale)


