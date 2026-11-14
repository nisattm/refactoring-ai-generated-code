"""Staff, hours, closure, shift and leave models (section 27.1)."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from lms.core.clock import LOCAL_TZ
from lms.core.db import Base
from lms.core.timeutil import TZDateTime

COUNTING_STATUSES = ("planned", "completed")


class StaffProfile(Base):
    __tablename__ = "staff_profiles"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id"), unique=True)
    home_branch_id: Mapped[int] = mapped_column(sa.ForeignKey("branches.id"), index=True)
    employment: Mapped[str] = mapped_column(sa.String(10))
    weekly_hours: Mapped[int]
    annual_leave_days: Mapped[int]
    started_on: Mapped[datetime.date] = mapped_column(sa.Date)
    is_active: Mapped[bool] = mapped_column(default=True)


class BranchHours(Base):
    __tablename__ = "branch_hours"

    branch_id: Mapped[int] = mapped_column(sa.ForeignKey("branches.id"), primary_key=True)
    opens_at: Mapped[datetime.time] = mapped_column(sa.Time)
    closes_at: Mapped[datetime.time] = mapped_column(sa.Time)
    min_staff: Mapped[int] = mapped_column(default=1)


class Closure(Base):
    __tablename__ = "branch_closures"
    __table_args__ = (sa.UniqueConstraint("branch_id", "date"), {"sqlite_autoincrement": True})

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(sa.ForeignKey("branches.id"), index=True)
    date: Mapped[datetime.date] = mapped_column(sa.Date, index=True)
    reason: Mapped[str] = mapped_column(sa.String(200))
    created_by: Mapped[int] = mapped_column(sa.ForeignKey("users.id"))


class Shift(Base):
    __tablename__ = "shifts"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    staff_id: Mapped[int] = mapped_column(sa.ForeignKey("staff_profiles.id"), index=True)
    branch_id: Mapped[int] = mapped_column(sa.ForeignKey("branches.id"), index=True)
    date: Mapped[datetime.date] = mapped_column(sa.Date, index=True)
    start_time: Mapped[datetime.time] = mapped_column(sa.Time)
    end_time: Mapped[datetime.time] = mapped_column(sa.Time)
    status: Mapped[str] = mapped_column(sa.String(10), default="planned", index=True)
    cancel_reason: Mapped[str | None] = mapped_column(sa.String(30), default=None)
    checked_in_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    checked_out_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    late_minutes: Mapped[int | None] = mapped_column(default=None)
    worked_minutes: Mapped[int | None] = mapped_column(default=None)

    @property
    def start_at(self) -> datetime.datetime:
        return datetime.datetime.combine(self.date, self.start_time, LOCAL_TZ)

    @property
    def end_at(self) -> datetime.datetime:
        return datetime.datetime.combine(self.date, self.end_time, LOCAL_TZ)

    @property
    def minutes(self) -> int:
        return int((self.end_at - self.start_at).total_seconds() // 60)

    @property
    def counts(self) -> bool:
        return self.status in COUNTING_STATUSES


class LeaveRequest(Base):
    __tablename__ = "leave_requests"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    staff_id: Mapped[int] = mapped_column(sa.ForeignKey("staff_profiles.id"), index=True)
    kind: Mapped[str] = mapped_column(sa.String(10))
    from_date: Mapped[datetime.date] = mapped_column(sa.Date)
    to_date: Mapped[datetime.date] = mapped_column(sa.Date)
    days: Mapped[int]
    note: Mapped[str] = mapped_column(sa.String(500), default="")
    status: Mapped[str] = mapped_column(sa.String(10), default="pending", index=True)
    decided_by: Mapped[int | None] = mapped_column(sa.ForeignKey("users.id"), default=None)
    decided_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    decision_note: Mapped[str | None] = mapped_column(sa.String(500), default=None)
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
