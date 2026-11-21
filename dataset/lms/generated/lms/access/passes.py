"""Day passes (LIB-ACC-25 to LIB-ACC-28)."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.access.models import DayPass
from lms.access.occupancy import settings_of
from lms.access.rules import DAY_PASS_LIMIT
from lms.audit.service import record
from lms.auth.models import User
from lms.branches.models import Branch
from lms.core.errors import Conflict
from lms.core.lookup import get_or_404
from lms.core.money import format_amount


def get_pass_or_404(db: Session, pass_id: int) -> DayPass:
    return get_or_404(db, DayPass, pass_id, "Day pass", "day_pass")


def sell_pass(db: Session, now: datetime.datetime, actor: User, branch: Branch, visitor_name: str) -> DayPass:
    """LIB-ACC-25, LIB-ACC-26."""
    today = now.date()
    if not branch.is_active:
        raise Conflict(
            f"Branch {branch.code} is inactive",
            code="BRANCH_INACTIVE",
            details={"field": "branch_id", "id": branch.id},
        )
    values = settings_of(db, branch.id)
    if not values["day_passes"]:
        raise Conflict("Day passes are disabled at this branch", code="DAY_PASSES_DISABLED")
    sold = (
        db.scalar(
            sa.select(sa.func.count()).select_from(DayPass).where(DayPass.branch_id == branch.id, DayPass.valid_on == today)
        )
        or 0
    )
    if sold >= DAY_PASS_LIMIT:
        raise Conflict(
            "The day pass limit of the branch is reached",
            code="DAY_PASS_LIMIT_REACHED",
            details={"limit": DAY_PASS_LIMIT},
        )
    day_pass = DayPass(
        code=f"DP-{branch.code}-{today.strftime('%Y%m%d')}-{sold + 1}",
        branch_id=branch.id,
        visitor_name=visitor_name,
        valid_on=today,
        price=values["day_pass_price"],
        status="unused",
        sold_at=now,
        sold_by=actor.id,
    )
    db.add(day_pass)
    db.flush()
    record(
        db,
        at=now,
        event="day_pass_sold",
        actor_user_id=actor.id,
        entity_type="day_pass",
        entity_id=day_pass.id,
        details={
            "code": day_pass.code,
            "branch_id": branch.id,
            "visitor_name": visitor_name,
            "price": format_amount(day_pass.price),
        },
    )
    return day_pass


def cancel_pass(db: Session, now: datetime.datetime, actor: User, day_pass: DayPass) -> DayPass:
    """LIB-ACC-27."""
    if day_pass.status != "unused":
        raise Conflict("The day pass cannot be cancelled", code="PASS_NOT_USABLE", details={"status": day_pass.status})
    day_pass.status = "cancelled"
    record(
        db,
        at=now,
        event="day_pass_cancelled",
        actor_user_id=actor.id,
        entity_type="day_pass",
        entity_id=day_pass.id,
        details={"code": day_pass.code, "branch_id": day_pass.branch_id},
    )
    return day_pass


def list_stmt(
    *, branch_id: int | None = None, valid_on: datetime.date | None = None, status: str | None = None
) -> sa.Select[tuple[DayPass]]:
    """LIB-ACC-28."""
    stmt = sa.select(DayPass).order_by(DayPass.id.desc())
    if branch_id is not None:
        stmt = stmt.where(DayPass.branch_id == branch_id)
    if valid_on is not None:
        stmt = stmt.where(DayPass.valid_on == valid_on)
    if status is not None:
        stmt = stmt.where(DayPass.status == status)
    return stmt
