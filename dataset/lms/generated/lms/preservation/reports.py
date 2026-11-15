"""Suggestions and reports of module 23 (LIB-PRE-26, LIB-PRE-37, LIB-PRE-38)."""

from __future__ import annotations

import datetime
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.branches.models import Branch
from lms.catalog.models import Copy
from lms.core.clock import LOCAL_TZ
from lms.core.money import ZERO, format_amount
from lms.fines.models import Fee
from lms.loans.models import Loan
from lms.preservation import rules, usage
from lms.preservation.models import OPEN_STATUSES, Budget, RepairJob
from lms.preservation.schemas import (
    PreservationReportOut,
    RecoveryOut,
    RecoveryTotalsOut,
    SuggestionOut,
)


def suggestions(db: Session, branch_id: int) -> list[SuggestionOut]:
    """LIB-PRE-26."""
    open_jobs = sa.select(RepairJob.copy_id).where(RepairJob.status.in_(OPEN_STATUSES))
    loans = sa.select(sa.func.count()).select_from(Loan).where(Loan.copy_id == Copy.id).scalar_subquery()
    copies = db.execute(
        sa.select(Copy.id, Copy.barcode, Copy.status, Copy.condition, loans)
        .where(Copy.current_branch_id == branch_id, Copy.status.in_(("damaged", "available")), Copy.id.not_in(open_jobs))
        .order_by(Copy.id)
    )
    items: list[SuggestionOut] = []
    for copy_id, barcode, status, condition, loan_count in copies:
        if status == "damaged":
            reason = "damaged"
        elif condition == "fragile":
            reason = "fragile"
        elif condition == "worn" and loan_count >= rules.WORN_LOANS:
            reason = "worn_and_used"
        else:
            continue
        items.append(SuggestionOut(copy_id=copy_id, barcode=barcode, reason=reason))
    return items


def _average_days(jobs: list[RepairJob]) -> str | None:
    days = [(j.returned_at.date() - j.sent_at.date()).days for j in jobs if j.returned_at is not None and j.sent_at is not None]
    if not days:
        return None
    mean = (Decimal(sum(days)) / Decimal(len(days))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return format(mean, "f")


def preservation_report(db: Session, today: datetime.date, year: int) -> list[PreservationReportOut]:
    """LIB-PRE-37: one row per branch with a budget or a job approved in ``year``, ordered by branch code."""
    budgets = {b.branch_id: b for b in db.scalars(sa.select(Budget).where(Budget.year == year))}
    by_branch: dict[int, list[RepairJob]] = defaultdict(list)
    for job in usage.jobs_of_budget_year(db, None, year):
        by_branch[job.branch_id].append(job)
    branch_ids = set(budgets) | set(by_branch)
    if not branch_ids:
        return []
    codes = {
        branch_id: code for branch_id, code in db.execute(sa.select(Branch.id, Branch.code).where(Branch.id.in_(branch_ids)))
    }
    rows: list[PreservationReportOut] = []
    for branch_id in sorted(branch_ids, key=lambda b: (codes[b], b)):
        jobs = by_branch.get(branch_id, [])
        committed, spent = usage.committed_and_spent(jobs)
        returned = [j for j in jobs if j.status == "returned"]
        budget = budgets.get(branch_id)
        rows.append(
            PreservationReportOut(
                branch_id=branch_id,
                budget=format_amount(budget.amount) if budget is not None else None,
                committed=format_amount(committed),
                spent=format_amount(spent),
                jobs_returned=len(returned),
                repaired=sum(1 for j in returned if j.outcome == "repaired"),
                unrepairable=sum(1 for j in returned if j.outcome == "unrepairable"),
                lost=sum(1 for j in jobs if j.status == "lost"),
                average_days=_average_days(returned),
                overdue_now=sum(1 for j in jobs if j.is_overdue(today)),
            )
        )
    return rows


def damage_recovery(
    db: Session, first: datetime.date, last: datetime.date
) -> tuple[list[RecoveryOut], RecoveryTotalsOut]:
    """LIB-PRE-38: the returned jobs with a damage loan and ``returned_at`` in the range."""
    start = datetime.datetime.combine(first, datetime.time.min, LOCAL_TZ)
    end = datetime.datetime.combine(last + datetime.timedelta(days=1), datetime.time.min, LOCAL_TZ)
    rows = db.execute(
        sa.select(RepairJob, Loan.member_id)
        .join(Loan, Loan.id == RepairJob.loan_id)
        .where(
            RepairJob.status == "returned",
            RepairJob.returned_at >= start,
            RepairJob.returned_at < end,
        )
        .order_by(RepairJob.returned_at, RepairJob.id)
    ).all()
    items: list[RecoveryOut] = []
    fees_total = ZERO
    costs_total = ZERO
    for job, member_id in rows:
        damage_fee = sum(
            db.scalars(sa.select(Fee.amount).where(Fee.loan_id == job.loan_id, Fee.kind == "damage_fee")), ZERO
        )
        actual = job.actual_cost if job.actual_cost is not None else ZERO
        fees_total += damage_fee
        costs_total += actual
        items.append(
            RecoveryOut(
                job_id=job.id,
                copy_id=job.copy_id,
                loan_id=job.loan_id,
                member_id=member_id,
                damage_fee=format_amount(damage_fee),
                actual_cost=format_amount(actual),
                difference=format_amount(damage_fee - actual),
            )
        )
    totals = RecoveryTotalsOut(
        damage_fees=format_amount(fees_total),
        costs=format_amount(costs_total),
        difference=format_amount(fees_total - costs_total),
    )
    return items, totals
