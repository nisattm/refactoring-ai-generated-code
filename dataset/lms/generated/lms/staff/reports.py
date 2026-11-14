"""Staff reports (LIB-STF-43 to LIB-STF-46)."""

from __future__ import annotations

import datetime
from collections import defaultdict
from collections.abc import Container
from decimal import ROUND_HALF_UP, Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.auth.models import User
from lms.rooms.schemas import format_time
from lms.staff.leave import working_days
from lms.staff.models import COUNTING_STATUSES, LeaveRequest, Shift, StaffProfile
from lms.staff.schedule import load_schedule
from lms.staff.schemas import (
    CoverageOut,
    CoverageRangeOut,
    MissingDayOut,
    SlotOut,
    StaffHoursOut,
)

_HALF = datetime.timedelta(minutes=30)
_DAY = datetime.timedelta(days=1)


def _hours(minutes: int) -> float:
    value = (Decimal(minutes) / 60).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return float(value)


def staff_hours(
    db: Session,
    holidays: Container[datetime.date],
    first: datetime.date,
    last: datetime.date,
    *,
    branch_id: int | None = None,
) -> list[StaffHoursOut]:
    """LIB-STF-43."""
    stmt = sa.select(Shift).where(Shift.date >= first, Shift.date <= last)
    if branch_id is not None:
        stmt = stmt.where(Shift.branch_id == branch_id)
    planned: dict[int, int] = defaultdict(int)
    worked: dict[int, int] = defaultdict(int)
    missed: dict[int, int] = defaultdict(int)
    late: dict[int, int] = defaultdict(int)
    for shift in db.scalars(stmt):
        if shift.status in COUNTING_STATUSES:
            planned[shift.staff_id] += shift.minutes
        if shift.status == "missed":
            missed[shift.staff_id] += 1
        worked[shift.staff_id] += shift.worked_minutes or 0
        late[shift.staff_id] += shift.late_minutes or 0

    leave_days: dict[int, int] = defaultdict(int)
    leaves = db.scalars(
        sa.select(LeaveRequest).where(
            LeaveRequest.status == "approved", LeaveRequest.from_date <= last, LeaveRequest.to_date >= first
        )
    )
    for leave in leaves:
        leave_days[leave.staff_id] += working_days(max(leave.from_date, first), min(leave.to_date, last), holidays)

    profiles = db.execute(
        sa.select(StaffProfile, User.full_name).join(User, User.id == StaffProfile.user_id).order_by(StaffProfile.id)
    )
    items: list[StaffHoursOut] = []
    for profile, full_name in profiles:
        in_branch = branch_id is None or profile.home_branch_id == branch_id
        items.append(
            StaffHoursOut(
                staff_id=profile.id,
                full_name=full_name,
                planned_hours=_hours(planned[profile.id]),
                worked_hours=_hours(worked[profile.id]),
                missed_shifts=missed[profile.id],
                late_minutes=late[profile.id],
                leave_days=leave_days[profile.id] if in_branch else 0,
            )
        )
    return items


def _slots(db: Session, holidays: Container[datetime.date], branch_id: int, day: datetime.date) -> tuple[bool, int, list[SlotOut]]:
    schedule = load_schedule(db, branch_id)
    if not schedule.is_open_on(day, holidays):
        return False, schedule.min_staff, []
    shifts = list(
        db.scalars(
            sa.select(Shift).where(
                Shift.branch_id == branch_id, Shift.date == day, Shift.status.in_(COUNTING_STATUSES)
            )
        )
    )
    slots: list[SlotOut] = []
    anchor = datetime.date(2000, 1, 1)
    cursor = datetime.datetime.combine(anchor, schedule.opens_at)
    end = datetime.datetime.combine(anchor, schedule.closes_at)
    while cursor < end:
        start_time, stop_time = cursor.time(), (cursor + _HALF).time()
        covering = sum(1 for s in shifts if s.start_time <= start_time and stop_time <= s.end_time)
        slots.append(SlotOut(start=format_time(start_time), staff=covering, ok=covering >= schedule.min_staff))
        cursor += _HALF
    return True, schedule.min_staff, slots


def coverage(db: Session, holidays: Container[datetime.date], branch_id: int, day: datetime.date) -> CoverageOut:
    """LIB-STF-44."""
    is_open, min_staff, slots = _slots(db, holidays, branch_id, day)
    return CoverageOut(branch_id=branch_id, date=day, open=is_open, min_staff=min_staff, slots=slots)


def understaffed_days(
    db: Session, holidays: Container[datetime.date], branch_id: int, first: datetime.date, last: datetime.date
) -> CoverageRangeOut:
    """LIB-STF-45."""
    days: list[MissingDayOut] = []
    day = first
    while day <= last:
        is_open, _, slots = _slots(db, holidays, branch_id, day)
        if is_open:
            days.append(MissingDayOut(date=day, missing_slots=sum(1 for s in slots if not s.ok)))
        day += _DAY
    return CoverageRangeOut(branch_id=branch_id, days=days)
