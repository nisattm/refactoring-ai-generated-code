"""Budgets, inspections and their effects (LIB-PRE-01 to LIB-PRE-07, LIB-PRE-31)."""

from __future__ import annotations

import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.branches.service import require_active_branch
from lms.catalog.models import Copy
from lms.core.errors import Conflict
from lms.core.money import format_amount
from lms.core.timeutil import format_datetime
from lms.preservation import usage
from lms.preservation.models import Budget, Inspection
from lms.preservation.schemas import BudgetOut, InspectionOut


def budget_out(db: Session, budget: Budget) -> BudgetOut:
    """LIB-PRE-02."""
    committed, spent = usage.budget_totals(db, budget.branch_id, budget.year)
    return BudgetOut(
        branch_id=budget.branch_id,
        year=budget.year,
        amount=format_amount(budget.amount),
        committed=format_amount(committed),
        spent=format_amount(spent),
        available=format_amount(budget.amount - committed - spent),
    )


def set_budget(
    db: Session, now: datetime.datetime, actor: User, branch_id: int, year: int, amount: Decimal
) -> Budget:
    """LIB-PRE-01, LIB-PRE-03, LIB-PRE-31."""
    require_active_branch(db, "branch_id", branch_id)
    committed, spent = usage.budget_totals(db, branch_id, year)
    if amount < committed + spent:
        raise Conflict(
            "The budget cannot be lower than the amount already used",
            code="BUDGET_BELOW_USED",
            details={"used": format_amount(committed + spent)},
        )
    budget = usage.budget_of(db, branch_id, year)
    old = format_amount(budget.amount) if budget is not None else None
    if budget is None:
        budget = Budget(branch_id=branch_id, year=year, amount=amount)
        db.add(budget)
    else:
        budget.amount = amount
    db.flush()
    record(
        db,
        at=now,
        event="preservation_budget_set",
        actor_user_id=actor.id,
        entity_type="preservation_budget",
        entity_id=budget.id,
        details={"branch_id": branch_id, "year": year, "amount": format_amount(amount), "old_amount": old},
    )
    return budget


def inspection_out(inspection: Inspection) -> InspectionOut:
    return InspectionOut(
        id=inspection.id,
        copy_id=inspection.copy_id,
        condition=inspection.condition,
        note=inspection.note,
        inspected_by=inspection.inspected_by,
        inspected_at=format_datetime(inspection.inspected_at),
    )


def inspect_copy(
    db: Session, now: datetime.datetime, actor: User, copy: Copy, condition: str, note: str
) -> Inspection:
    """LIB-PRE-04."""
    if copy.status in ("lost", "withdrawn"):
        raise Conflict(
            f"Copy {copy.id} has status {copy.status}: inspection is not allowed",
            code="INVALID_COPY_STATUS",
            details={"id": copy.id, "status": copy.status},
        )
    inspection = Inspection(
        copy_id=copy.id, condition=condition, note=note, inspected_by=actor.id, inspected_at=now
    )
    db.add(inspection)
    old = copy.condition
    copy.condition = condition
    db.flush()
    record(
        db,
        at=now,
        event="copy_inspected",
        actor_user_id=actor.id,
        entity_type="copy",
        entity_id=copy.id,
        details={"inspection_id": inspection.id, "condition": {"old": old, "new": condition}, "note": note},
    )
    return inspection


def inspections_stmt(copy_id: int) -> sa.Select[tuple[Inspection]]:
    """LIB-PRE-05."""
    return (
        sa.select(Inspection)
        .where(Inspection.copy_id == copy_id)
        .order_by(Inspection.inspected_at.desc(), Inspection.id.desc())
    )


