"""Staff and shifts endpoints (section 27.2)."""

from __future__ import annotations

import datetime
from typing import Annotated

from fastapi import APIRouter, Path, Query, Request, Response

from lms.auth.deps import AdminOnly, AnyUser, CurrentPrincipal, StaffOnly
from lms.branches.service import get_branch_or_404
from lms.core.clock import local_now
from lms.core.db import SessionDep
from lms.core.errors import Forbidden, NotFound, ValidationFailed
from lms.core.pagination import Page, PageDep, paginate, paginate_sequence
from lms.core.timeutil import parse_date
from lms.staff import hours as hours_service
from lms.staff import leave as leave_service
from lms.staff import profiles
from lms.staff import reports as report_service
from lms.staff import shifts as shift_service
from lms.staff.models import Closure, Shift
from lms.staff.schemas import (
    ClosureCreatedOut,
    ClosureIn,
    ClosureOut,
    CopyWeekIn,
    CopyWeekOut,
    CoverageOut,
    CoverageRangeOut,
    DecisionIn,
    Employment,
    HoursIn,
    HoursOut,
    LeaveBalanceOut,
    LeaveCreateIn,
    LeaveKind,
    LeaveOut,
    LeaveStatus,
    OpenDaysOut,
    ProcessOut,
    ShiftCreateIn,
    ShiftOut,
    ShiftPatchIn,
    ShiftStatus,
    StaffCreateIn,
    StaffHoursOut,
    StaffOut,
    StaffPatchIn,
    leave_out,
    shift_out,
)

router = APIRouter(tags=["staff and shifts"])

StaffId = Annotated[int, Path(ge=1)]
BranchId = Annotated[int, Path(ge=1)]
ClosureId = Annotated[int, Path(ge=1)]
ShiftId = Annotated[int, Path(ge=1)]
LeaveId = Annotated[int, Path(ge=1)]


def _date_param(name: str, raw: str | None, problems: list[dict[str, str]], *, required: bool = False) -> datetime.date | None:
    if raw is None:
        if required:
            problems.append({"field": name, "problem": "field required"})
        return None
    try:
        return parse_date(raw.strip())
    except ValueError:
        problems.append({"field": name, "problem": "expected a valid date in the form YYYY-MM-DD"})
        return None


def _shift_out(db: SessionDep, shift: Shift) -> ShiftOut:
    return shift_out(shift, shift_service.staff_name(db, shift.staff_id))


# --- staff profiles ------------------------------------------------------------------------------


@router.post("/staff", response_model=StaffOut, status_code=201)
def create_staff(body: StaffCreateIn, request: Request, db: SessionDep, admin: AdminOnly) -> StaffOut:
    now = local_now(request.app.state.settings.clock)
    profile = profiles.create_profile(
        db,
        now,
        admin.user,
        user_id=body.user_id,
        home_branch_id=body.home_branch_id,
        employment=body.employment,
        weekly_hours=body.weekly_hours,
        annual_leave_days=body.annual_leave_days,
        started_on=body.started_on,
    )
    return profiles.to_out(db, profile)


@router.get("/staff", response_model=Page[StaffOut])
def list_staff(
    db: SessionDep,
    _: AdminOnly,
    page: PageDep,
    home_branch_id: Annotated[int | None, Query()] = None,
    employment: Annotated[Employment | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
) -> Page[StaffOut]:
    stmt = profiles.list_stmt(home_branch_id=home_branch_id, employment=employment, is_active=is_active)
    return paginate(db, stmt, page, lambda p: profiles.to_out(db, p))


@router.get("/staff/me", response_model=StaffOut)
def get_own_staff(db: SessionDep, staff: StaffOnly) -> StaffOut:
    return profiles.to_out(db, profiles.own_profile(db, staff.user))


@router.post("/staff/process", response_model=ProcessOut)
def process_staff(request: Request, db: SessionDep, admin: AdminOnly) -> ProcessOut:
    now = local_now(request.app.state.settings.clock)
    missed, auto = shift_service.process(db, now, admin.user)
    return ProcessOut(missed=missed, auto_checked_out=auto)


@router.get("/staff/{staff_id}", response_model=StaffOut)
def get_staff(staff_id: StaffId, db: SessionDep, staff: StaffOnly) -> StaffOut:
    profile = profiles.get_profile_or_404(db, staff_id)
    profiles.require_own_or_admin(db, staff.user, staff_id)
    return profiles.to_out(db, profile)


@router.patch("/staff/{staff_id}", response_model=StaffOut)
def update_staff(staff_id: StaffId, body: StaffPatchIn, request: Request, db: SessionDep, admin: AdminOnly) -> StaffOut:
    now = local_now(request.app.state.settings.clock)
    profile = profiles.get_profile_or_404(db, staff_id)
    fields = {name: getattr(body, name) for name in body.model_fields_set}
    if any(value is None for value in fields.values()):
        raise ValidationFailed(
            [{"field": name, "problem": "value must not be null"} for name, value in fields.items() if value is None]
        )
    return profiles.to_out(db, profiles.update_profile(db, now, admin.user, profile, fields))


@router.get("/staff/{staff_id}/leave-balance", response_model=LeaveBalanceOut)
def leave_balance(
    staff_id: StaffId,
    request: Request,
    db: SessionDep,
    staff: StaffOnly,
    year: Annotated[int | None, Query(ge=1900, le=2100)] = None,
) -> LeaveBalanceOut:
    settings = request.app.state.settings
    profile = profiles.get_profile_or_404(db, staff_id)
    profiles.require_own_or_admin(db, staff.user, staff_id)
    chosen = year if year is not None else local_now(settings.clock).year
    return LeaveBalanceOut(**leave_service.balance(db, profile, chosen, settings.holidays))


# --- opening hours and closures ----------------------------------------------------------------------


@router.get("/branches/{branch_id}/hours", response_model=HoursOut)
def get_hours(branch_id: BranchId, db: SessionDep, _: AnyUser) -> HoursOut:
    get_branch_or_404(db, branch_id)
    return hours_service.hours_out(db, branch_id)


@router.put("/branches/{branch_id}/hours", response_model=HoursOut)
def put_hours(branch_id: BranchId, body: HoursIn, request: Request, db: SessionDep, admin: AdminOnly) -> HoursOut:
    now = local_now(request.app.state.settings.clock)
    branch = get_branch_or_404(db, branch_id)
    return hours_service.set_hours(db, now, admin.user, branch, body.opens_at, body.closes_at, body.min_staff)


@router.post("/branches/{branch_id}/closures", response_model=ClosureCreatedOut, status_code=201)
def add_closure(
    branch_id: BranchId, body: ClosureIn, request: Request, db: SessionDep, admin: AdminOnly
) -> ClosureCreatedOut:
    settings = request.app.state.settings
    now = local_now(settings.clock)
    branch = get_branch_or_404(db, branch_id)
    return hours_service.add_closure(db, now, admin.user, settings.holidays, branch, body.date, body.reason)


@router.delete("/closures/{closure_id}", status_code=204)
def remove_closure(closure_id: ClosureId, request: Request, db: SessionDep, admin: AdminOnly) -> Response:
    now = local_now(request.app.state.settings.clock)
    closure = db.get(Closure, closure_id)
    if closure is None:
        raise NotFound(f"Closure {closure_id} does not exist", details={"resource": "closure", "id": closure_id})
    hours_service.remove_closure(db, now, admin.user, closure)
    return Response(status_code=204)


@router.get("/closures", response_model=Page[ClosureOut])
def list_closures(
    db: SessionDep,
    _: AnyUser,
    page: PageDep,
    branch_id: Annotated[int | None, Query()] = None,
    first: Annotated[str | None, Query(alias="from")] = None,
    to: Annotated[str | None, Query()] = None,
) -> Page[ClosureOut]:
    problems: list[dict[str, str]] = []
    start = _date_param("from", first, problems)
    end = _date_param("to", to, problems)
    if problems:
        raise ValidationFailed(problems)
    stmt = hours_service.closure_list_stmt(branch_id=branch_id, first=start, last=end)
    return paginate(db, stmt, page, hours_service.closure_out)


@router.get("/branches/{branch_id}/open-days", response_model=OpenDaysOut)
def open_days(
    branch_id: BranchId,
    request: Request,
    db: SessionDep,
    _: AnyUser,
    first: Annotated[str | None, Query(alias="from")] = None,
    to: Annotated[str | None, Query()] = None,
) -> OpenDaysOut:
    problems: list[dict[str, str]] = []
    start = _date_param("from", first, problems, required=True)
    end = _date_param("to", to, problems, required=True)
    if problems:
        raise ValidationFailed(problems)
    assert start is not None and end is not None
    if start > end:
        raise ValidationFailed.single("from", "from must not be after to")
    if (end - start).days + 1 > hours_service.MAX_OPEN_DAYS:
        raise ValidationFailed.single("to", "the range must not be longer than 62 days")
    get_branch_or_404(db, branch_id)
    days = hours_service.open_days(db, request.app.state.settings.holidays, branch_id, start, end)
    return OpenDaysOut(branch_id=branch_id, days=days)


# --- shifts ----------------------------------------------------------------------------------------


@router.post("/shifts", response_model=ShiftOut, status_code=201)
def create_shift(body: ShiftCreateIn, request: Request, db: SessionDep, admin: AdminOnly) -> ShiftOut:
    settings = request.app.state.settings
    now = local_now(settings.clock)
    shift = shift_service.create_shift(
        db,
        now,
        admin.user,
        settings.holidays,
        staff_id=body.staff_id,
        branch_id=body.branch_id,
        day=body.date,
        start=body.start_time,
        end=body.end_time,
    )
    return _shift_out(db, shift)


@router.post("/shifts/copy-week", response_model=CopyWeekOut)
def copy_week(body: CopyWeekIn, request: Request, db: SessionDep, admin: AdminOnly) -> CopyWeekOut:
    settings = request.app.state.settings
    now = local_now(settings.clock)
    created, skipped = shift_service.copy_week(
        db,
        now,
        admin.user,
        settings.holidays,
        branch_id=body.branch_id,
        from_week=body.from_week,
        to_week=body.to_week,
    )
    return CopyWeekOut(created=created, skipped=skipped)


@router.get("/shifts", response_model=Page[ShiftOut])
def list_shifts(
    db: SessionDep,
    staff: StaffOnly,
    page: PageDep,
    staff_id: Annotated[int | None, Query()] = None,
    branch_id: Annotated[int | None, Query()] = None,
    status: Annotated[ShiftStatus | None, Query()] = None,
    first: Annotated[str | None, Query(alias="from")] = None,
    to: Annotated[str | None, Query()] = None,
) -> Page[ShiftOut]:
    problems: list[dict[str, str]] = []
    start = _date_param("from", first, problems)
    end = _date_param("to", to, problems)
    if problems:
        raise ValidationFailed(problems)
    if staff.user.role != "admin":
        own = profiles.own_profile(db, staff.user)
        if staff_id is not None and staff_id != own.id:
            raise Forbidden("Only your own shifts can be read")
        staff_id = own.id
    stmt = shift_service.shift_list_stmt(staff_id=staff_id, branch_id=branch_id, status=status, first=start, last=end)
    return paginate(db, stmt, page, lambda s: _shift_out(db, s))


@router.patch("/shifts/{shift_id}", response_model=ShiftOut)
def update_shift(shift_id: ShiftId, body: ShiftPatchIn, request: Request, db: SessionDep, admin: AdminOnly) -> ShiftOut:
    settings = request.app.state.settings
    now = local_now(settings.clock)
    shift = shift_service.get_shift_or_404(db, shift_id)
    fields = {name: getattr(body, name) for name in body.model_fields_set}
    if any(value is None for value in fields.values()):
        raise ValidationFailed(
            [{"field": name, "problem": "value must not be null"} for name, value in fields.items() if value is None]
        )
    return _shift_out(db, shift_service.update_shift(db, now, admin.user, settings.holidays, shift, fields))


@router.post("/shifts/{shift_id}/cancel", response_model=ShiftOut)
def cancel_shift(shift_id: ShiftId, request: Request, db: SessionDep, admin: AdminOnly) -> ShiftOut:
    now = local_now(request.app.state.settings.clock)
    shift = shift_service.get_shift_or_404(db, shift_id)
    return _shift_out(db, shift_service.cancel_by_request(db, now, admin.user, shift))


def _own_shift(db: SessionDep, shift_id: int, staff: StaffOnly) -> Shift:
    shift = shift_service.get_shift_or_404(db, shift_id)
    own = profiles.profile_of_user(db, staff.user.id)
    if own is None or own.id != shift.staff_id:
        raise Forbidden("Only the staff member of the shift can check in and out")
    return shift


@router.post("/shifts/{shift_id}/check-in", response_model=ShiftOut)
def check_in(shift_id: ShiftId, request: Request, db: SessionDep, staff: StaffOnly) -> ShiftOut:
    now = local_now(request.app.state.settings.clock)
    shift = _own_shift(db, shift_id, staff)
    return _shift_out(db, shift_service.check_in(db, now, staff.user, shift))


@router.post("/shifts/{shift_id}/check-out", response_model=ShiftOut)
def check_out(shift_id: ShiftId, request: Request, db: SessionDep, staff: StaffOnly) -> ShiftOut:
    now = local_now(request.app.state.settings.clock)
    shift = _own_shift(db, shift_id, staff)
    return _shift_out(db, shift_service.check_out(db, now, staff.user, shift))


# --- leave -------------------------------------------------------------------------------------------


@router.post("/leave-requests", response_model=LeaveOut, status_code=201)
def create_leave(body: LeaveCreateIn, request: Request, db: SessionDep, staff: StaffOnly) -> LeaveOut:
    settings = request.app.state.settings
    now = local_now(settings.clock)
    leave, cancelled = leave_service.request_leave(
        db,
        now,
        staff.user,
        settings.holidays,
        kind=body.kind,
        from_date=body.from_date,
        to_date=body.to_date,
        note=body.note,
    )
    return leave_out(leave, cancelled)


@router.get("/leave-requests", response_model=Page[LeaveOut])
def list_leave(
    db: SessionDep,
    staff: StaffOnly,
    page: PageDep,
    staff_id: Annotated[int | None, Query()] = None,
    status: Annotated[LeaveStatus | None, Query()] = None,
    kind: Annotated[LeaveKind | None, Query()] = None,
    year: Annotated[int | None, Query(ge=1900, le=2100)] = None,
) -> Page[LeaveOut]:
    if staff.user.role != "admin":
        own = profiles.own_profile(db, staff.user)
        if staff_id is not None and staff_id != own.id:
            raise Forbidden("Only your own leave requests can be read")
        staff_id = own.id
    stmt = leave_service.leave_list_stmt(staff_id=staff_id, status=status, kind=kind, year=year)
    return paginate(db, stmt, page, leave_out)


def _decide(
    leave_id: int, body: DecisionIn | None, request: Request, db: SessionDep, admin: CurrentPrincipal, approve: bool
) -> LeaveOut:
    settings = request.app.state.settings
    now = local_now(settings.clock)
    leave = leave_service.get_leave_or_404(db, leave_id)
    own = profiles.profile_of_user(db, admin.user.id)
    leave, cancelled = leave_service.decide(
        db,
        now,
        admin.user,
        settings.holidays,
        leave,
        approve=approve,
        note=body.note if body is not None else None,
        own_staff_id=own.id if own is not None else None,
    )
    return leave_out(leave, cancelled)


@router.post("/leave-requests/{leave_id}/approve", response_model=LeaveOut)
def approve_leave(
    leave_id: LeaveId, request: Request, db: SessionDep, admin: AdminOnly, body: DecisionIn | None = None
) -> LeaveOut:
    return _decide(leave_id, body, request, db, admin, True)


@router.post("/leave-requests/{leave_id}/reject", response_model=LeaveOut)
def reject_leave(
    leave_id: LeaveId, request: Request, db: SessionDep, admin: AdminOnly, body: DecisionIn | None = None
) -> LeaveOut:
    return _decide(leave_id, body, request, db, admin, False)


@router.post("/leave-requests/{leave_id}/cancel", response_model=LeaveOut)
def cancel_leave(leave_id: LeaveId, request: Request, db: SessionDep, staff: StaffOnly) -> LeaveOut:
    now = local_now(request.app.state.settings.clock)
    leave = leave_service.get_leave_or_404(db, leave_id)
    own = profiles.profile_of_user(db, staff.user.id)
    is_owner = own is not None and own.id == leave.staff_id
    if not is_owner and staff.user.role != "admin":
        raise Forbidden("Only the owner or an admin can cancel a leave request")
    return leave_out(leave_service.cancel(db, now, staff.user, leave, is_owner=is_owner))


# --- reports -----------------------------------------------------------------------------------------


@router.get("/reports/staff-hours", response_model=Page[StaffHoursOut])
def staff_hours_report(
    request: Request,
    db: SessionDep,
    _: AdminOnly,
    page: PageDep,
    first: Annotated[str | None, Query(alias="from")] = None,
    to: Annotated[str | None, Query()] = None,
    branch_id: Annotated[int | None, Query()] = None,
) -> Page[StaffHoursOut]:
    problems: list[dict[str, str]] = []
    start = _date_param("from", first, problems, required=True)
    end = _date_param("to", to, problems, required=True)
    if problems:
        raise ValidationFailed(problems)
    assert start is not None and end is not None
    if start > end:
        raise ValidationFailed.single("from", "from must not be after to")
    if (end - start).days + 1 > 92:
        raise ValidationFailed.single("to", "the range must not be longer than 92 days")
    items = report_service.staff_hours(db, request.app.state.settings.holidays, start, end, branch_id=branch_id)
    return paginate_sequence(items, page)


@router.get("/reports/branch-coverage", response_model=CoverageOut | CoverageRangeOut)
def branch_coverage_report(
    request: Request,
    db: SessionDep,
    _: AdminOnly,
    branch_id: Annotated[int, Query(ge=1)],
    day: Annotated[str | None, Query(alias="date")] = None,
    first: Annotated[str | None, Query(alias="from")] = None,
    to: Annotated[str | None, Query()] = None,
) -> CoverageOut | CoverageRangeOut:
    holidays = request.app.state.settings.holidays
    problems: list[dict[str, str]] = []
    one_day = _date_param("date", day, problems)
    start = _date_param("from", first, problems)
    end = _date_param("to", to, problems)
    if problems:
        raise ValidationFailed(problems)
    if one_day is not None:
        get_branch_or_404(db, branch_id)
        return report_service.coverage(db, holidays, branch_id, one_day)
    if start is None or end is None:
        raise ValidationFailed.single("date", "either date or from and to is required")
    if start > end:
        raise ValidationFailed.single("from", "from must not be after to")
    if (end - start).days + 1 > 31:
        raise ValidationFailed.single("to", "the range must not be longer than 31 days")
    get_branch_or_404(db, branch_id)
    return report_service.understaffed_days(db, holidays, branch_id, start, end)
