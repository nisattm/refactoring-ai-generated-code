"""Light-weight lookups of module 23 used by other modules (catalog, reservations, purchasing) and by module 23
itself.

Imports only models and rules, so that the other modules can use it without import cycles."""

from __future__ import annotations

import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.catalog.models import Copy
from lms.core.clock import LOCAL_TZ
from lms.core.errors import Conflict
from lms.core.money import ZERO
from lms.preservation.models import OPEN_STATUSES, Budget, RepairJob


# --- budgets (LIB-PRE-02) ------------------------------------------------------------------


def budget_of(db: Session, branch_id: int, year: int) -> Budget | None:
    return db.scalar(sa.select(Budget).where(Budget.branch_id == branch_id, Budget.year == year))


def jobs_of_budget_year(db: Session, branch_id: int | None, year: int) -> list[RepairJob]:
    """The jobs (of the branch, or of all branches) whose budget year (the year of ``approved_at``) is ``year``."""
    first = datetime.datetime(year, 1, 1, tzinfo=LOCAL_TZ)
    after = datetime.datetime(year + 1, 1, 1, tzinfo=LOCAL_TZ)
    stmt = sa.select(RepairJob).where(RepairJob.approved_at >= first, RepairJob.approved_at < after)
    if branch_id is not None:
        stmt = stmt.where(RepairJob.branch_id == branch_id)
    return list(db.scalars(stmt.order_by(RepairJob.id)))


def committed_and_spent(jobs: list[RepairJob]) -> tuple[Decimal, Decimal]:
    """``committed`` and ``spent`` of LIB-PRE-02 over the jobs of one branch and budget year."""
    committed = ZERO
    spent = ZERO
    for job in jobs:
        if job.status in ("approved", "sent"):
            committed += job.estimated_cost
        elif job.status == "returned":
            spent += job.actual_cost if job.actual_cost is not None else ZERO
        elif job.status == "lost":
            spent += job.estimated_cost
    return committed, spent


def budget_totals(db: Session, branch_id: int, year: int) -> tuple[Decimal, Decimal]:
    return committed_and_spent(jobs_of_budget_year(db, branch_id, year))


# --- effects on other modules ---------------------------------------------------------------


def open_job_id(db: Session, copy_id: int) -> int | None:
    """LIB-PRE-29: the open job of the copy."""
    stmt = sa.select(RepairJob.id).where(RepairJob.copy_id == copy_id, RepairJob.status.in_(OPEN_STATUSES))
    return db.scalar(stmt.order_by(RepairJob.id.desc()).limit(1))


def require_no_open_job(db: Session, copy_id: int) -> None:
    """LIB-PRE-28: a copy with an open job cannot be repaired or withdrawn directly."""
    job_id = open_job_id(db, copy_id)
    if job_id is not None:
        raise Conflict(
            f"Copy {copy_id} has an open repair job", code="COPY_HAS_REPAIR_JOB", details={"job_id": job_id}
        )


def open_job_ids_of_supplier(db: Session, supplier_id: int) -> list[int]:
    """LIB-PRE-32."""
    stmt = sa.select(RepairJob.id).where(RepairJob.supplier_id == supplier_id, RepairJob.status.in_(OPEN_STATUSES))
    return list(db.scalars(stmt.order_by(RepairJob.id)))


def expected_back(db: Session, book_id: int, branch_id: int) -> datetime.date | None:
    """LIB-PRE-33: the latest ``due_back`` of the book's ``sent`` jobs at the branch."""
    stmt = (
        sa.select(sa.func.max(RepairJob.due_back))
        .join(Copy, Copy.id == RepairJob.copy_id)
        .where(Copy.book_id == book_id, RepairJob.branch_id == branch_id, RepairJob.status == "sent")
    )
    return db.scalar(stmt)
