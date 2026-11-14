"""Request and response schemas of module 19 (section 27)."""

from __future__ import annotations

import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StrictInt

from lms.core.schemas import RequestModel
from lms.core.timeutil import format_datetime
from lms.rooms.schemas import HHMM, DateValue, format_time
from lms.staff.models import LeaveRequest, Shift, StaffProfile

Employment = Literal["full_time", "part_time"]
ShiftStatus = Literal["planned", "cancelled", "completed", "missed"]
LeaveKind = Literal["annual", "sick", "unpaid"]
LeaveStatus = Literal["pending", "approved", "rejected", "cancelled"]
Id = StrictInt


# --- requests --------------------------------------------------------------------------------


class StaffCreateIn(RequestModel):
    user_id: Id
    home_branch_id: Id
    employment: Employment
    weekly_hours: Id | None = None
    annual_leave_days: Id | None = None
    started_on: DateValue


class StaffPatchIn(RequestModel):
    home_branch_id: Id | None = None
    employment: Employment | None = None
    weekly_hours: Id | None = None
    annual_leave_days: Id | None = None
    is_active: bool | None = None


class HoursIn(RequestModel):
    opens_at: HHMM
    closes_at: HHMM
    min_staff: Id = 1


class ClosureIn(RequestModel):
    date: DateValue
    reason: Annotated[str, Field(min_length=1, max_length=200)]


class ShiftCreateIn(RequestModel):
    staff_id: Id
    branch_id: Id
    date: DateValue
    start_time: HHMM
    end_time: HHMM


class ShiftPatchIn(RequestModel):
    staff_id: Id | None = None
    branch_id: Id | None = None
    date: DateValue | None = None
    start_time: HHMM | None = None
    end_time: HHMM | None = None


class CopyWeekIn(RequestModel):
    branch_id: Id
    from_week: DateValue
    to_week: DateValue


class LeaveCreateIn(RequestModel):
    kind: LeaveKind
    from_date: DateValue
    to_date: DateValue
    note: Annotated[str, Field(max_length=500)] = ""


class DecisionIn(RequestModel):
    note: Annotated[str, Field(max_length=500)] | None = None


# --- responses -------------------------------------------------------------------------------


class StaffOut(BaseModel):
    id: int
    user_id: int
    home_branch_id: int
    employment: str
    weekly_hours: int
    annual_leave_days: int
    started_on: datetime.date
    is_active: bool
    full_name: str
    email: str


class HoursOut(BaseModel):
    branch_id: int
    opens_at: str
    closes_at: str
    min_staff: int


class ClosureOut(BaseModel):
    id: int
    branch_id: int
    date: datetime.date
    reason: str
    created_by: int


class ClosureCreatedOut(ClosureOut):
    cancelled_shifts: int
    cancelled_room_bookings: int
    cancelled_equipment_reservations: int
    cancelled_events: int


class OpenDayOut(BaseModel):
    date: datetime.date
    open: bool
    reason: str | None
    opens_at: str | None
    closes_at: str | None


class OpenDaysOut(BaseModel):
    branch_id: int
    days: list[OpenDayOut]


class ShiftOut(BaseModel):
    id: int
    staff_id: int
    staff_name: str
    branch_id: int
    date: datetime.date
    start_time: str
    end_time: str
    status: str
    cancel_reason: str | None
    checked_in_at: str | None
    checked_out_at: str | None
    late_minutes: int | None
    worked_minutes: int | None
    hours: float


class CopySkippedOut(BaseModel):
    source_shift_id: int
    error_code: str


class CopyWeekOut(BaseModel):
    created: int
    skipped: list[CopySkippedOut]


class LeaveOut(BaseModel):
    id: int
    staff_id: int
    kind: str
    from_date: datetime.date
    to_date: datetime.date
    days: int
    note: str
    status: str
    decided_by: int | None
    decided_at: str | None
    decision_note: str | None
    created_at: str
    cancelled_shift_ids: list[int] = Field(default_factory=list)


class LeaveBalanceOut(BaseModel):
    staff_id: int
    year: int
    entitled: int
    used: int
    pending: int
    remaining: int


class ProcessOut(BaseModel):
    missed: int
    auto_checked_out: int


class StaffHoursOut(BaseModel):
    staff_id: int
    full_name: str
    planned_hours: float
    worked_hours: float
    missed_shifts: int
    late_minutes: int
    leave_days: int


class SlotOut(BaseModel):
    start: str
    staff: int
    ok: bool


class CoverageOut(BaseModel):
    branch_id: int
    date: datetime.date
    open: bool
    min_staff: int
    slots: list[SlotOut]


class MissingDayOut(BaseModel):
    date: datetime.date
    missing_slots: int


class CoverageRangeOut(BaseModel):
    branch_id: int
    days: list[MissingDayOut]


# --- conversion ------------------------------------------------------------------------------


def _dt(value: datetime.datetime | None) -> str | None:
    return None if value is None else format_datetime(value)


def staff_out(profile: StaffProfile, full_name: str, email: str) -> StaffOut:
    return StaffOut(
        id=profile.id,
        user_id=profile.user_id,
        home_branch_id=profile.home_branch_id,
        employment=profile.employment,
        weekly_hours=profile.weekly_hours,
        annual_leave_days=profile.annual_leave_days,
        started_on=profile.started_on,
        is_active=profile.is_active,
        full_name=full_name,
        email=email,
    )


def shift_hours(shift: Shift) -> float:
    return round(shift.minutes / 60, 1)


def shift_out(shift: Shift, staff_name: str) -> ShiftOut:
    return ShiftOut(
        id=shift.id,
        staff_id=shift.staff_id,
        staff_name=staff_name,
        branch_id=shift.branch_id,
        date=shift.date,
        start_time=format_time(shift.start_time),
        end_time=format_time(shift.end_time),
        status=shift.status,
        cancel_reason=shift.cancel_reason,
        checked_in_at=_dt(shift.checked_in_at),
        checked_out_at=_dt(shift.checked_out_at),
        late_minutes=shift.late_minutes,
        worked_minutes=shift.worked_minutes,
        hours=shift_hours(shift),
    )


def leave_out(leave: LeaveRequest, cancelled_shift_ids: list[int] | None = None) -> LeaveOut:
    return LeaveOut(
        id=leave.id,
        staff_id=leave.staff_id,
        kind=leave.kind,
        from_date=leave.from_date,
        to_date=leave.to_date,
        days=leave.days,
        note=leave.note,
        status=leave.status,
        decided_by=leave.decided_by,
        decided_at=_dt(leave.decided_at),
        decision_note=leave.decision_note,
        created_at=format_datetime(leave.created_at),
        cancelled_shift_ids=cancelled_shift_ids or [],
    )
