"""Opening hours and closures of a branch (LIB-STF-07, LIB-STF-09, LIB-STF-14)."""

from __future__ import annotations

import dataclasses
import datetime
from collections.abc import Container

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.branches.models import Branch
from lms.core.calendar import day_reason
from lms.staff.models import BranchHours, Closure

DEFAULT_OPENS = datetime.time(8, 0)
DEFAULT_CLOSES = datetime.time(20, 0)
DEFAULT_MIN_STAFF = 1


@dataclasses.dataclass(frozen=True)
class BranchSchedule:
    """Hours and closure dates of one branch. The default is the schedule of LIB-EQ-01."""

    opens_at: datetime.time = DEFAULT_OPENS
    closes_at: datetime.time = DEFAULT_CLOSES
    min_staff: int = DEFAULT_MIN_STAFF
    active: bool = True
    closures: dict[datetime.date, str] = dataclasses.field(default_factory=dict)

    def closed_reason(self, day: datetime.date, holidays: Container[datetime.date]) -> str | None:
        """``weekend``, ``holiday``, ``closure: <reason>`` (or ``inactive``) for a date on which the branch is
        not open; ``None`` when it is open (27.1)."""
        reason = day_reason(day, holidays)
        if reason is not None:
            return reason
        if day in self.closures:
            return f"closure: {self.closures[day]}"
        if not self.active:
            return "inactive"
        return None

    def is_open_on(self, day: datetime.date, holidays: Container[datetime.date]) -> bool:
        return self.closed_reason(day, holidays) is None

    def is_calendar_open(self, day: datetime.date, holidays: Container[datetime.date]) -> bool:
        """Like ``is_open_on`` but ignoring whether the branch is active (inactive branches are rejected earlier)."""
        reason = self.closed_reason(day, holidays)
        return reason is None or reason == "inactive"


def hours_of(db: Session, branch_id: int) -> BranchHours | None:
    return db.get(BranchHours, branch_id)


def closure_map(db: Session, branch_id: int) -> dict[datetime.date, str]:
    return {c.date: c.reason for c in db.scalars(sa.select(Closure).where(Closure.branch_id == branch_id))}


def load_schedule(db: Session, branch_id: int) -> BranchSchedule:
    hours = hours_of(db, branch_id)
    branch = db.get(Branch, branch_id)
    return BranchSchedule(
        opens_at=hours.opens_at if hours is not None else DEFAULT_OPENS,
        closes_at=hours.closes_at if hours is not None else DEFAULT_CLOSES,
        min_staff=hours.min_staff if hours is not None else DEFAULT_MIN_STAFF,
        active=branch.is_active if branch is not None else True,
        closures=closure_map(db, branch_id),
    )


def has_closure_on(db: Session, branch_id: int, day: datetime.date) -> bool:
    stmt = sa.select(Closure.id).where(Closure.branch_id == branch_id, Closure.date == day).limit(1)
    return db.scalar(stmt) is not None
