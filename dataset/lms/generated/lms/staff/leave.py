"""Leave requests and the leave balance (LIB-STF-34 to LIB-STF-42)."""

from __future__ import annotations

import datetime
from collections.abc import Container
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.core.calendar import is_working_day
from lms.core.errors import Conflict, NotFound, ValidationFailed
from lms.staff import shifts
from lms.staff.models import LeaveRequest, Shift, StaffProfile

MAX_LEAVE_DAYS = 30
SICK_BACKDATE_DAYS = 7
SICK_AUTO_APPROVE_DAYS = 2
_DAY = datetime.timedelta(days=1)


def _error(code: str, message: str, **details: Any) -> Conflict:
    return Conflict(message, code=code, details=details)


def get_leave_or_404(db: Session, leave_id: int) -> LeaveRequest:
    leave = db.get(LeaveRequest, leave_id)
    if leave is None:
        raise NotFound(f"Leave request {leave_id} does not exist", details={"resource": "leave_request", "id": leave_id})
    return leave


def working_days(first: datetime.date, last: datetime.date, holidays: Container[datetime.date]) -> int:
    """Working days from ``first`` to ``last``, both included (LIB-COM-05)."""
    total = 0
    day = first
    while day <= last:
        if is_working_day(day, holidays):
            total += 1
        day += _DAY
    return total


def _year_bounds(year: int) -> tuple[datetime.date, datetime.date]:
    return datetime.date(year, 1, 1), datetime.date(year, 12, 31)


def days_in_year(leave: LeaveRequest, year: int, holidays: Container[datetime.date]) -> int:
    """Working days of the request that fall into the calendar ``year``."""
    first, last = _year_bounds(year)
    lo, hi = max(leave.from_date, first), min(leave.to_date, last)
    return working_days(lo, hi, holidays) if lo <= hi else 0


# --- balance ---------------------------------------------------------------------------------------


def entitled_days(profile: StaffProfile, year: int) -> int:
    """LIB-STF-40: for the year of ``started_on`` rounded down by the share of the year from that day."""
    if year < profile.started_on.year:
        return 0
    if year > profile.started_on.year:
        return profile.annual_leave_days
    first, last = _year_bounds(year)
    total = (last - first).days + 1
    remaining = (last - profile.started_on).days + 1
    return profile.annual_leave_days * remaining // total


def _annual_days(
    db: Session, staff_id: int, status: str, year: int, holidays: Container[datetime.date], *, exclude_id: int | None = None
) -> int:
    first, last = _year_bounds(year)
    stmt = sa.select(LeaveRequest).where(
        LeaveRequest.staff_id == staff_id,
        LeaveRequest.kind == "annual",
        LeaveRequest.status == status,
        LeaveRequest.from_date <= last,
        LeaveRequest.to_date >= first,
    )
    if exclude_id is not None:
        stmt = stmt.where(LeaveRequest.id != exclude_id)
    return sum(days_in_year(leave, year, holidays) for leave in db.scalars(stmt))


def balance(
    db: Session, profile: StaffProfile, year: int, holidays: Container[datetime.date]
) -> dict[str, int]:
    entitled = entitled_days(profile, year)
    used = _annual_days(db, profile.id, "approved", year, holidays)
    pending = _annual_days(db, profile.id, "pending", year, holidays)
    return {
        "staff_id": profile.id,
        "year": year,
        "entitled": entitled,
        "used": used,
        "pending": pending,
        "remaining": entitled - used - pending,
    }


def _check_balance(
    db: Session,
    profile: StaffProfile,
    leave_kind: str,
    first: datetime.date,
    last: datetime.date,
    holidays: Container[datetime.date],
    *,
    exclude_id: int | None = None,
) -> None:
    """``LEAVE_BALANCE_EXCEEDED`` for an annual leave that needs more than the remaining days of a year it touches."""
    if leave_kind != "annual":
        return
    for year in range(first.year, last.year + 1):
        lo, hi = max(first, _year_bounds(year)[0]), min(last, _year_bounds(year)[1])
        needed = working_days(lo, hi, holidays)
        remaining = (
            entitled_days(profile, year)
            - _annual_days(db, profile.id, "approved", year, holidays, exclude_id=exclude_id)
            - _annual_days(db, profile.id, "pending", year, holidays, exclude_id=exclude_id)
        )
        if needed > remaining:
            raise _error("LEAVE_BALANCE_EXCEEDED", "The annual leave balance is exceeded", remaining=remaining)


# --- request, decide, cancel ---------------------------------------------------------------------------


def cancel_shifts_of_leave(
    db: Session, now: datetime.datetime, actor_id: int | None, leave: LeaveRequest
) -> list[int]:
    """LIB-STF-39."""
    found = shifts.planned_shifts(
        db, Shift.staff_id == leave.staff_id, Shift.date >= leave.from_date, Shift.date <= leave.to_date
    )
    for shift in found:
        shifts.cancel_shift(db, now, actor_id, shift, "leave")
    return [s.id for s in found]


def request_leave(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    *,
    kind: str,
    from_date: datetime.date,
    to_date: datetime.date,
    note: str,
) -> tuple[LeaveRequest, list[int]]:
    """LIB-STF-34, LIB-STF-35, LIB-STF-42."""
    problems: list[dict[str, str]] = []
    if from_date > to_date:
        problems.append({"field": "to_date", "problem": "to_date must not be before from_date"})
    elif (to_date - from_date).days + 1 > MAX_LEAVE_DAYS:
        problems.append({"field": "to_date", "problem": "a leave request covers at most 30 calendar days"})
    if problems:
        raise ValidationFailed(problems)

    profile = db.scalar(sa.select(StaffProfile).where(StaffProfile.user_id == actor.id))
    if profile is None:
        raise Conflict("The user has no staff profile", code="NOT_STAFF")
    if not profile.is_active:
        raise _error("STAFF_INACTIVE", "The staff profile is inactive")
    today = now.date()
    earliest = today - datetime.timedelta(days=SICK_BACKDATE_DAYS) if kind == "sick" else today
    if from_date < earliest:
        raise _error("LEAVE_IN_PAST", "The leave starts too far in the past")
    days = working_days(from_date, to_date, holidays)
    if days == 0:
        raise _error("NO_WORKING_DAYS", "The leave contains no working days")
    overlap = db.scalar(
        sa.select(sa.func.min(LeaveRequest.id)).where(
            LeaveRequest.staff_id == profile.id,
            LeaveRequest.status.in_(("pending", "approved")),
            LeaveRequest.from_date <= to_date,
            LeaveRequest.to_date >= from_date,
        )
    )
    if overlap is not None:
        raise _error("LEAVE_OVERLAP", "The leave overlaps another request", leave_id=overlap)
    _check_balance(db, profile, kind, from_date, to_date, holidays)

    leave = LeaveRequest(
        staff_id=profile.id,
        kind=kind,
        from_date=from_date,
        to_date=to_date,
        days=days,
        note=note,
        status="pending",
        created_at=now,
    )
    auto = kind == "sick" and days <= SICK_AUTO_APPROVE_DAYS
    if auto:
        leave.status = "approved"
        leave.decided_at = now
    db.add(leave)
    db.flush()
    record(
        db,
        at=now,
        event="leave_requested",
        actor_user_id=actor.id,
        entity_type="leave_request",
        entity_id=leave.id,
        details={
            "staff_id": profile.id,
            "kind": kind,
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "days": days,
            "status": leave.status,
        },
    )
    cancelled = cancel_shifts_of_leave(db, now, actor.id, leave) if auto else []
    return leave, cancelled


def decide(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    leave: LeaveRequest,
    *,
    approve: bool,
    note: str | None,
    own_staff_id: int | None,
) -> tuple[LeaveRequest, list[int]]:
    """LIB-STF-38, LIB-STF-39."""
    if leave.status != "pending":
        raise _error("LEAVE_NOT_PENDING", "The leave request is not pending", status=leave.status)
    if own_staff_id is not None and leave.staff_id == own_staff_id:
        raise _error("OWN_LEAVE", "An admin cannot decide on their own leave")
    cancelled: list[int] = []
    if approve:
        profile = db.get(StaffProfile, leave.staff_id)
        assert profile is not None
        _check_balance(db, profile, leave.kind, leave.from_date, leave.to_date, holidays, exclude_id=leave.id)
    leave.status = "approved" if approve else "rejected"
    leave.decided_by = actor.id
    leave.decided_at = now
    leave.decision_note = note
    record(
        db,
        at=now,
        event="leave_approved" if approve else "leave_rejected",
        actor_user_id=actor.id,
        entity_type="leave_request",
        entity_id=leave.id,
        details={"staff_id": leave.staff_id, "note": note},
    )
    if approve:
        cancelled = cancel_shifts_of_leave(db, now, actor.id, leave)
    return leave, cancelled


def mark_cancelled(db: Session, now: datetime.datetime, actor_id: int | None, leave: LeaveRequest) -> LeaveRequest:
    leave.status = "cancelled"
    record(
        db,
        at=now,
        event="leave_cancelled",
        actor_user_id=actor_id,
        entity_type="leave_request",
        entity_id=leave.id,
        details={"staff_id": leave.staff_id},
    )
    return leave


def cancel(
    db: Session, now: datetime.datetime, actor: User, leave: LeaveRequest, *, is_owner: bool
) -> LeaveRequest:
    """LIB-STF-41: the owner cancels a pending request; an admin a pending or approved one that starts later."""
    allowed = (is_owner and leave.status == "pending") or (
        actor.role == "admin" and leave.status in ("pending", "approved") and leave.from_date > now.date()
    )
    if not allowed:
        raise _error("LEAVE_NOT_CANCELLABLE", "The leave request cannot be cancelled", status=leave.status)
    return mark_cancelled(db, now, actor.id, leave)


def leave_list_stmt(
    *,
    staff_id: int | None = None,
    status: str | None = None,
    kind: str | None = None,
    year: int | None = None,
) -> sa.Select[tuple[LeaveRequest]]:
    """LIB-STF-37."""
    stmt = sa.select(LeaveRequest).order_by(LeaveRequest.from_date, LeaveRequest.id)
    if staff_id is not None:
        stmt = stmt.where(LeaveRequest.staff_id == staff_id)
    if status is not None:
        stmt = stmt.where(LeaveRequest.status == status)
    if kind is not None:
        stmt = stmt.where(LeaveRequest.kind == kind)
    if year is not None:
        first, last = _year_bounds(year)
        stmt = stmt.where(LeaveRequest.from_date <= last, LeaveRequest.to_date >= first)
    return stmt
