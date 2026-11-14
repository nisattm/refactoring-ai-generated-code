"""Staff profiles (LIB-STF-01 to LIB-STF-06, LIB-STF-48)."""

from __future__ import annotations

import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import changes, record
from lms.auth.models import User
from lms.branches.models import Branch
from lms.core.errors import (
    Conflict,
    Forbidden,
    NotFound,
    ValidationFailed,
    reference_not_found,
)
from lms.staff import leave as leave_service
from lms.staff import shifts
from lms.staff.models import LeaveRequest, Shift, StaffProfile
from lms.staff.schemas import StaffOut, staff_out

FULL_TIME_HOURS = 40
PART_TIME_HOURS = (10, 30)
LEAVE_DEFAULTS = {"full_time": 14, "part_time": 7}
_FIELDS = ("home_branch_id", "employment", "weekly_hours", "annual_leave_days", "is_active")


def get_profile_or_404(db: Session, staff_id: int) -> StaffProfile:
    profile = db.get(StaffProfile, staff_id)
    if profile is None:
        raise NotFound(f"Staff profile {staff_id} does not exist", details={"resource": "staff", "id": staff_id})
    return profile


def profile_of_user(db: Session, user_id: int) -> StaffProfile | None:
    return db.scalar(sa.select(StaffProfile).where(StaffProfile.user_id == user_id))


def own_profile(db: Session, user: User) -> StaffProfile:
    """The staff profile of the authenticated user; ``409 NOT_STAFF`` without one (27.2)."""
    profile = profile_of_user(db, user.id)
    if profile is None:
        raise Conflict("The user has no staff profile", code="NOT_STAFF")
    return profile


def require_own_or_admin(db: Session, user: User, staff_id: int) -> None:
    """Reading another staff member's data is ``403 FORBIDDEN`` (27.2)."""
    if user.role == "admin":
        return
    profile = profile_of_user(db, user.id)
    if profile is None or profile.id != staff_id:
        raise Forbidden("Only your own staff data can be accessed")


def to_out(db: Session, profile: StaffProfile) -> StaffOut:
    user = db.get(User, profile.user_id)
    assert user is not None
    return staff_out(profile, user.full_name, user.email)


def weekly_hours_problems(employment: str, weekly_hours: int | None, annual_leave_days: int | None) -> list[dict[str, str]]:
    problems: list[dict[str, str]] = []
    if employment == "full_time":
        if weekly_hours != FULL_TIME_HOURS:
            problems.append({"field": "weekly_hours", "problem": "weekly_hours must be 40 for full_time"})
    elif weekly_hours is None or not PART_TIME_HOURS[0] <= weekly_hours <= PART_TIME_HOURS[1]:
        problems.append({"field": "weekly_hours", "problem": "weekly_hours must be 10-30 for part_time"})
    if annual_leave_days is None or not 0 <= annual_leave_days <= 30:
        problems.append({"field": "annual_leave_days", "problem": "annual_leave_days must be 0-30"})
    return problems


def _snapshot(profile: StaffProfile) -> dict[str, Any]:
    return {name: getattr(profile, name) for name in _FIELDS}


def create_profile(
    db: Session,
    now: datetime.datetime,
    actor: User,
    *,
    user_id: int,
    home_branch_id: int,
    employment: str,
    weekly_hours: int | None,
    annual_leave_days: int | None,
    started_on: datetime.date,
) -> StaffProfile:
    """LIB-STF-01, LIB-STF-02."""
    if weekly_hours is None and employment == "full_time":
        weekly_hours = FULL_TIME_HOURS
    if annual_leave_days is None:
        annual_leave_days = LEAVE_DEFAULTS[employment]
    problems = weekly_hours_problems(employment, weekly_hours, annual_leave_days)
    if started_on > now.date():
        problems.append({"field": "started_on", "problem": "started_on must not be after today"})
    if problems:
        raise ValidationFailed(problems)
    assert weekly_hours is not None

    user = db.get(User, user_id)
    if user is None:
        raise reference_not_found("user_id", user_id)
    branch = db.get(Branch, home_branch_id)
    if branch is None:
        raise reference_not_found("home_branch_id", home_branch_id)
    if not user.is_active:
        raise Conflict("The user is inactive", code="USER_INACTIVE")
    if user.role == "member":
        raise Conflict("Members cannot have a staff profile", code="NOT_STAFF_ROLE")
    if profile_of_user(db, user_id) is not None:
        raise Conflict("The user already has a staff profile", details={"field": "user_id"})
    if not branch.is_active:
        raise Conflict(
            f"Branch {branch.code} is inactive",
            code="BRANCH_INACTIVE",
            details={"field": "home_branch_id", "id": branch.id},
        )
    profile = StaffProfile(
        user_id=user_id,
        home_branch_id=home_branch_id,
        employment=employment,
        weekly_hours=weekly_hours,
        annual_leave_days=annual_leave_days,
        started_on=started_on,
        is_active=True,
    )
    db.add(profile)
    db.flush()
    record(
        db,
        at=now,
        event="staff_created",
        actor_user_id=actor.id,
        entity_type="staff",
        entity_id=profile.id,
        details={**_snapshot(profile), "user_id": user_id, "started_on": started_on.isoformat()},
    )
    return profile


def deactivate(db: Session, now: datetime.datetime, actor_id: int | None, profile: StaffProfile) -> None:
    """LIB-STF-04: cancel the planned shifts that start after now and the pending leave requests."""
    for shift in shifts.planned_shifts(db, Shift.staff_id == profile.id, Shift.date >= now.date()):
        if shift.start_at > now:
            shifts.cancel_shift(db, now, actor_id, shift, "staff_deactivated")
    pending = db.scalars(
        sa.select(LeaveRequest)
        .where(LeaveRequest.staff_id == profile.id, LeaveRequest.status == "pending")
        .order_by(LeaveRequest.id)
    )
    for leave in list(pending):
        leave_service.mark_cancelled(db, now, actor_id, leave)


def update_profile(
    db: Session, now: datetime.datetime, actor: User, profile: StaffProfile, fields: dict[str, Any]
) -> StaffProfile:
    """LIB-STF-03, LIB-STF-04."""
    new = {name: fields.get(name, getattr(profile, name)) for name in _FIELDS}
    problems = weekly_hours_problems(new["employment"], new["weekly_hours"], new["annual_leave_days"])
    if problems:
        raise ValidationFailed(problems)
    if "home_branch_id" in fields and fields["home_branch_id"] != profile.home_branch_id:
        branch = db.get(Branch, fields["home_branch_id"])
        if branch is None:
            raise reference_not_found("home_branch_id", fields["home_branch_id"])
        if not branch.is_active:
            raise Conflict(
                f"Branch {branch.code} is inactive",
                code="BRANCH_INACTIVE",
                details={"field": "home_branch_id", "id": branch.id},
            )
    old = _snapshot(profile)
    deactivating = profile.is_active and new["is_active"] is False
    for name, value in new.items():
        setattr(profile, name, value)
    diff = changes(old, _snapshot(profile))
    if diff:
        record(
            db, at=now, event="staff_updated", actor_user_id=actor.id, entity_type="staff", entity_id=profile.id, details=diff
        )
    if deactivating:
        deactivate(db, now, actor.id, profile)
    return profile


def on_user_deactivated(db: Session, now: datetime.datetime, actor: User, user: User) -> None:
    """LIB-STF-06, LIB-STF-48: called before a user is deactivated."""
    profile = profile_of_user(db, user.id)
    if profile is None:
        return
    if shifts.in_progress_shift_exists(db, profile.id):
        raise Conflict("The user has a shift in progress", code="SHIFT_IN_PROGRESS", details={"staff_id": profile.id})
    if profile.is_active:
        profile.is_active = False
        record(
            db,
            at=now,
            event="staff_updated",
            actor_user_id=actor.id,
            entity_type="staff",
            entity_id=profile.id,
            details={"is_active": {"old": True, "new": False}},
        )
        deactivate(db, now, actor.id, profile)


def list_stmt(
    *, home_branch_id: int | None = None, employment: str | None = None, is_active: bool | None = None
) -> sa.Select[tuple[StaffProfile]]:
    """LIB-STF-05."""
    stmt = sa.select(StaffProfile).order_by(StaffProfile.id)
    if home_branch_id is not None:
        stmt = stmt.where(StaffProfile.home_branch_id == home_branch_id)
    if employment is not None:
        stmt = stmt.where(StaffProfile.employment == employment)
    if is_active is not None:
        stmt = stmt.where(StaffProfile.is_active == is_active)
    return stmt
