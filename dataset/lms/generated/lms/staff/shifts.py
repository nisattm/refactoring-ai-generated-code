"""Shifts and attendance (LIB-STF-18 to LIB-STF-33)."""

from __future__ import annotations

import datetime
from collections.abc import Container
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import changes, record
from lms.auth.models import User
from lms.branches.models import Branch
from lms.core.errors import Conflict, NotFound, ValidationFailed, reference_not_found
from lms.core.timeutil import format_datetime
from lms.rooms.schemas import format_time
from lms.staff.models import COUNTING_STATUSES, LeaveRequest, Shift, StaffProfile
from lms.staff.schedule import load_schedule

MIN_REST = datetime.timedelta(hours=11)
CHECK_IN_EARLY = datetime.timedelta(minutes=30)
LATE_GRACE_MINUTES = 5
AUTO_CHECK_OUT = datetime.timedelta(minutes=60)
_DAY = datetime.timedelta(days=1)


def _error(code: str, message: str, **details: Any) -> Conflict:
    return Conflict(message, code=code, details=details)


def get_shift_or_404(db: Session, shift_id: int) -> Shift:
    shift = db.get(Shift, shift_id)
    if shift is None:
        raise NotFound(f"Shift {shift_id} does not exist", details={"resource": "shift", "id": shift_id})
    return shift


def staff_name(db: Session, staff_id: int) -> str:
    stmt = sa.select(User.full_name).join(StaffProfile, StaffProfile.user_id == User.id).where(StaffProfile.id == staff_id)
    return db.scalar(stmt) or ""


def _minutes(t: datetime.time) -> int:
    return t.hour * 60 + t.minute


def time_problems(start: datetime.time, end: datetime.time) -> list[dict[str, str]]:
    """27.1: ``start_time`` before ``end_time``, 2 to 10 hours long."""
    if start >= end:
        return [{"field": "end_time", "problem": "end_time must be after start_time"}]
    length = _minutes(end) - _minutes(start)
    if not 120 <= length <= 600:
        return [{"field": "end_time", "problem": "a shift must be 2 to 10 hours long"}]
    return []


def format_hours(minutes: int) -> float:
    return round(minutes / 60, 1)


def week_bounds(day: datetime.date) -> tuple[datetime.date, datetime.date]:
    first = day - datetime.timedelta(days=day.weekday())
    return first, first + datetime.timedelta(days=6)


def counting_shifts(
    db: Session, staff_id: int, first: datetime.date, last: datetime.date, *, exclude_id: int | None = None
) -> list[Shift]:
    stmt = sa.select(Shift).where(
        Shift.staff_id == staff_id, Shift.status.in_(COUNTING_STATUSES), Shift.date >= first, Shift.date <= last
    )
    if exclude_id is not None:
        stmt = stmt.where(Shift.id != exclude_id)
    return list(db.scalars(stmt.order_by(Shift.date, Shift.start_time, Shift.id)))


# --- checks of LIB-STF-19 ------------------------------------------------------------------------


def check_shift(
    db: Session,
    now: datetime.datetime,
    holidays: Container[datetime.date],
    profile: StaffProfile,
    branch: Branch,
    day: datetime.date,
    start: datetime.time,
    end: datetime.time,
    *,
    exclude_id: int | None = None,
) -> None:
    """The nine checks of LIB-STF-19, in order."""
    if not branch.is_active:
        raise _error("BRANCH_INACTIVE", f"Branch {branch.code} is inactive", field="branch_id", id=branch.id)
    if not profile.is_active:
        raise _error("STAFF_INACTIVE", "The staff profile is inactive")
    if day < now.date():
        raise _error("SHIFT_IN_PAST", "The shift date is in the past")
    schedule = load_schedule(db, branch.id)
    reason = schedule.closed_reason(day, holidays)
    if reason is not None:
        raise _error(
            "BRANCH_NOT_OPEN", "The branch is not open on this date", reason=reason.split(":")[0], date=day.isoformat()
        )
    if start < schedule.opens_at or end > schedule.closes_at:
        raise _error(
            "OUTSIDE_BRANCH_HOURS",
            "The shift is outside the opening hours of the branch",
            opens_at=format_time(schedule.opens_at),
            closes_at=format_time(schedule.closes_at),
        )
    leave_id = db.scalar(
        sa.select(sa.func.min(LeaveRequest.id)).where(
            LeaveRequest.staff_id == profile.id,
            LeaveRequest.status == "approved",
            LeaveRequest.from_date <= day,
            LeaveRequest.to_date >= day,
        )
    )
    if leave_id is not None:
        raise _error("STAFF_ON_LEAVE", "The staff member is on leave on this date", leave_id=leave_id)

    around = counting_shifts(db, profile.id, day - _DAY, day + _DAY, exclude_id=exclude_id)
    overlapping = [s.id for s in around if s.date == day and s.start_time < end and start < s.end_time]
    if overlapping:
        raise _error("SHIFT_OVERLAP", "The staff member has an overlapping shift", shift_id=min(overlapping))
    start_at = datetime.datetime.combine(day, start)
    end_at = datetime.datetime.combine(day, end)
    for other in around:
        if other.date == day:
            continue
        other_start = datetime.datetime.combine(other.date, other.start_time)
        other_end = datetime.datetime.combine(other.date, other.end_time)
        gap = start_at - other_end if other.date < day else other_start - end_at
        if gap < MIN_REST:
            raise _error("REST_PERIOD_TOO_SHORT", "Less than 11 hours of rest between shifts", shift_id=other.id)

    first, last = week_bounds(day)
    planned = sum(s.minutes for s in counting_shifts(db, profile.id, first, last, exclude_id=exclude_id))
    if planned + (_minutes(end) - _minutes(start)) > profile.weekly_hours * 60:
        raise _error(
            "WEEKLY_HOURS_EXCEEDED",
            "The weekly hours of the staff member are exceeded",
            planned_hours=format_hours(planned),
            limit=profile.weekly_hours,
        )


def _profile_or_404(db: Session, field: str, staff_id: int) -> StaffProfile:
    profile = db.get(StaffProfile, staff_id)
    if profile is None:
        raise reference_not_found(field, staff_id)
    return profile


def _branch_or_404(db: Session, field: str, branch_id: int) -> Branch:
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise reference_not_found(field, branch_id)
    return branch


def _snapshot(shift: Shift) -> dict[str, Any]:
    return {
        "staff_id": shift.staff_id,
        "branch_id": shift.branch_id,
        "date": shift.date.isoformat(),
        "start_time": format_time(shift.start_time),
        "end_time": format_time(shift.end_time),
    }


def create_shift(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    *,
    staff_id: int,
    branch_id: int,
    day: datetime.date,
    start: datetime.time,
    end: datetime.time,
) -> Shift:
    """LIB-STF-18, LIB-STF-19."""
    problems = time_problems(start, end)
    if problems:
        raise ValidationFailed(problems)
    profile = _profile_or_404(db, "staff_id", staff_id)
    branch = _branch_or_404(db, "branch_id", branch_id)
    check_shift(db, now, holidays, profile, branch, day, start, end)
    shift = Shift(
        staff_id=profile.id, branch_id=branch.id, date=day, start_time=start, end_time=end, status="planned"
    )
    db.add(shift)
    db.flush()
    record(
        db,
        at=now,
        event="shift_planned",
        actor_user_id=actor.id,
        entity_type="shift",
        entity_id=shift.id,
        details=_snapshot(shift),
    )
    return shift


def has_started(shift: Shift, now: datetime.datetime) -> bool:
    return shift.start_at <= now


def update_shift(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    shift: Shift,
    fields: dict[str, Any],
) -> Shift:
    """LIB-STF-22."""
    new = {
        "staff_id": fields.get("staff_id", shift.staff_id),
        "branch_id": fields.get("branch_id", shift.branch_id),
        "date": fields.get("date", shift.date),
        "start_time": fields.get("start_time", shift.start_time),
        "end_time": fields.get("end_time", shift.end_time),
    }
    problems = time_problems(new["start_time"], new["end_time"])
    if problems:
        raise ValidationFailed(problems)
    profile = _profile_or_404(db, "staff_id", new["staff_id"])
    branch = _branch_or_404(db, "branch_id", new["branch_id"])
    if shift.status != "planned" or has_started(shift, now) or shift.checked_in_at is not None:
        raise _error("SHIFT_NOT_CHANGEABLE", "The shift cannot be changed", status=shift.status)
    check_shift(
        db, now, holidays, profile, branch, new["date"], new["start_time"], new["end_time"], exclude_id=shift.id
    )
    old = _snapshot(shift)
    shift.staff_id = profile.id
    shift.branch_id = branch.id
    shift.date = new["date"]
    shift.start_time = new["start_time"]
    shift.end_time = new["end_time"]
    diff = changes(old, _snapshot(shift))
    record(
        db, at=now, event="shift_updated", actor_user_id=actor.id, entity_type="shift", entity_id=shift.id, details=diff
    )
    return shift


def cancel_shift(
    db: Session, now: datetime.datetime, actor_id: int | None, shift: Shift, reason: str
) -> Shift:
    """Set a shift to ``cancelled`` with ``reason`` (LIB-STF-04, 11, 23, 39)."""
    shift.status = "cancelled"
    shift.cancel_reason = reason
    record(
        db,
        at=now,
        event="shift_cancelled",
        actor_user_id=actor_id,
        entity_type="shift",
        entity_id=shift.id,
        details={"reason": reason, "staff_id": shift.staff_id, "date": shift.date.isoformat()},
    )
    return shift


def cancel_by_request(db: Session, now: datetime.datetime, actor: User, shift: Shift) -> Shift:
    """LIB-STF-23."""
    if shift.status != "planned" or has_started(shift, now) or shift.checked_in_at is not None:
        raise _error("SHIFT_NOT_CHANGEABLE", "The shift cannot be cancelled", status=shift.status)
    return cancel_shift(db, now, actor.id, shift, "staff_request")


def planned_shifts(
    db: Session, *conditions: sa.ColumnElement[bool]
) -> list[Shift]:
    stmt = (
        sa.select(Shift)
        .where(Shift.status == "planned", *conditions)
        .order_by(Shift.date, Shift.start_time, Shift.id)
    )
    return list(db.scalars(stmt))


def shift_list_stmt(
    *,
    staff_id: int | None = None,
    branch_id: int | None = None,
    status: str | None = None,
    first: datetime.date | None = None,
    last: datetime.date | None = None,
) -> sa.Select[tuple[Shift]]:
    """LIB-STF-24."""
    stmt = sa.select(Shift).order_by(Shift.date, Shift.start_time, Shift.id)
    if staff_id is not None:
        stmt = stmt.where(Shift.staff_id == staff_id)
    if branch_id is not None:
        stmt = stmt.where(Shift.branch_id == branch_id)
    if status is not None:
        stmt = stmt.where(Shift.status == status)
    if first is not None:
        stmt = stmt.where(Shift.date >= first)
    if last is not None:
        stmt = stmt.where(Shift.date <= last)
    return stmt


# --- copy a week -----------------------------------------------------------------------------------


def copy_week(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    *,
    branch_id: int,
    from_week: datetime.date,
    to_week: datetime.date,
) -> tuple[int, list[dict[str, Any]]]:
    """LIB-STF-25."""
    problems: list[dict[str, str]] = []
    if from_week.weekday() != 0:
        problems.append({"field": "from_week", "problem": "from_week must be a Monday"})
    if to_week.weekday() != 0:
        problems.append({"field": "to_week", "problem": "to_week must be a Monday"})
    if to_week <= now.date():
        problems.append({"field": "to_week", "problem": "to_week must be after today"})
    if to_week <= from_week:
        problems.append({"field": "to_week", "problem": "to_week must be after from_week"})
    if problems:
        raise ValidationFailed(problems)
    branch = _branch_or_404(db, "branch_id", branch_id)

    offset = to_week - from_week
    sources = list(
        db.scalars(
            sa.select(Shift)
            .where(
                Shift.branch_id == branch.id,
                Shift.status.in_(COUNTING_STATUSES),
                Shift.date >= from_week,
                Shift.date <= from_week + datetime.timedelta(days=6),
            )
            .order_by(Shift.date, Shift.start_time, Shift.id)
        )
    )
    created = 0
    skipped: list[dict[str, Any]] = []
    for source in sources:
        profile = db.get(StaffProfile, source.staff_id)
        assert profile is not None
        day = source.date + offset
        try:
            check_shift(db, now, holidays, profile, branch, day, source.start_time, source.end_time)
        except Conflict as exc:
            skipped.append({"source_shift_id": source.id, "error_code": exc.code})
            continue
        shift = Shift(
            staff_id=profile.id,
            branch_id=branch.id,
            date=day,
            start_time=source.start_time,
            end_time=source.end_time,
            status="planned",
        )
        db.add(shift)
        db.flush()
        created += 1
    record(
        db,
        at=now,
        event="shifts_copied",
        actor_user_id=actor.id,
        entity_type="shift",
        entity_id=None,
        details={
            "branch_id": branch.id,
            "from_week": from_week.isoformat(),
            "to_week": to_week.isoformat(),
            "created": created,
            "skipped": len(skipped),
        },
    )
    return created, skipped


# --- attendance --------------------------------------------------------------------------------------


def _worked_minutes(shift: Shift, until: datetime.datetime) -> int:
    assert shift.checked_in_at is not None
    begin = max(shift.checked_in_at, shift.start_at)
    return max(int((min(until, shift.end_at) - begin).total_seconds() // 60), 0)


def check_in(db: Session, now: datetime.datetime, actor: User, shift: Shift) -> Shift:
    """LIB-STF-29, LIB-STF-30."""
    if shift.status != "planned" or shift.checked_in_at is not None:
        raise _error("SHIFT_NOT_CHANGEABLE", "The shift cannot be checked in", status=shift.status)
    earliest = shift.start_at - CHECK_IN_EARLY
    if now < earliest:
        raise _error("CHECK_IN_TOO_EARLY", "Check-in is not open yet", opens_at=format_datetime(earliest))
    if now >= shift.end_at:
        raise _error("SHIFT_OVER", "The shift is over")
    shift.checked_in_at = now
    late = now - shift.start_at
    shift.late_minutes = (
        int(late.total_seconds() // 60) if late > datetime.timedelta(minutes=LATE_GRACE_MINUTES) else 0
    )
    record(
        db,
        at=now,
        event="shift_checked_in",
        actor_user_id=actor.id,
        entity_type="shift",
        entity_id=shift.id,
        details={"late_minutes": shift.late_minutes},
    )
    return shift


def check_out(db: Session, now: datetime.datetime, actor: User, shift: Shift) -> Shift:
    """LIB-STF-31."""
    if shift.status != "planned":
        raise _error("SHIFT_NOT_CHANGEABLE", "The shift cannot be checked out", status=shift.status)
    if shift.checked_in_at is None:
        raise _error("NOT_CHECKED_IN", "The shift has not been checked in")
    shift.checked_out_at = now
    shift.status = "completed"
    shift.worked_minutes = _worked_minutes(shift, now)
    record(
        db,
        at=now,
        event="shift_checked_out",
        actor_user_id=actor.id,
        entity_type="shift",
        entity_id=shift.id,
        details={"worked_minutes": shift.worked_minutes},
    )
    return shift


def process(db: Session, now: datetime.datetime, actor: User) -> tuple[int, int]:
    """LIB-STF-32."""
    missed = auto = 0
    for shift in planned_shifts(db, Shift.date <= now.date()):
        if shift.checked_in_at is None:
            if shift.end_at < now:
                shift.status = "missed"
                missed += 1
        elif shift.end_at + AUTO_CHECK_OUT < now:
            shift.status = "completed"
            shift.checked_out_at = shift.end_at + AUTO_CHECK_OUT
            shift.worked_minutes = _worked_minutes(shift, shift.end_at)
            auto += 1
    record(
        db,
        at=now,
        event="staff_processed",
        actor_user_id=actor.id,
        entity_type="staff",
        entity_id=None,
        details={"missed": missed, "auto_checked_out": auto},
    )
    return missed, auto


def in_progress_shift_exists(db: Session, staff_id: int) -> bool:
    """LIB-STF-48: a checked-in shift that is not checked out."""
    stmt = (
        sa.select(Shift.id)
        .where(Shift.staff_id == staff_id, Shift.status == "planned", Shift.checked_in_at.is_not(None))
        .limit(1)
    )
    return db.scalar(stmt) is not None
