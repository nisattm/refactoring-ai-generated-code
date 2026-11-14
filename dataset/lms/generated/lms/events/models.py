"""Event, series, registration and ban models (section 28.1)."""

from __future__ import annotations

import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from lms.core.clock import LOCAL_TZ
from lms.core.db import Base
from lms.core.money import MoneyType
from lms.core.timeutil import TZDateTime

ACTIVE_REGISTRATION_STATUSES = ("registered", "waitlisted")


class EventSeries(Base):
    __tablename__ = "event_series"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    created_by: Mapped[int] = mapped_column(sa.ForeignKey("users.id"))


class Event(Base):
    __tablename__ = "events"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(sa.String(200))
    description: Mapped[str] = mapped_column(sa.String(2000), default="")
    kind: Mapped[str] = mapped_column(sa.String(10))
    branch_id: Mapped[int] = mapped_column(sa.ForeignKey("branches.id"), index=True)
    room_id: Mapped[int | None] = mapped_column(sa.ForeignKey("rooms.id"), index=True, default=None)
    date: Mapped[datetime.date] = mapped_column(sa.Date, index=True)
    start_time: Mapped[datetime.time] = mapped_column(sa.Time)
    end_time: Mapped[datetime.time] = mapped_column(sa.Time)
    capacity: Mapped[int]
    fee: Mapped[Decimal] = mapped_column(MoneyType, default=Decimal("0.00"))
    audience: Mapped[str] = mapped_column(sa.String(10), default="all")
    staff_id: Mapped[int] = mapped_column(sa.ForeignKey("staff_profiles.id"), index=True)
    series_id: Mapped[int | None] = mapped_column(sa.ForeignKey("event_series.id"), index=True, default=None)
    status: Mapped[str] = mapped_column(sa.String(10), default="draft", index=True)
    cancel_reason: Mapped[str | None] = mapped_column(sa.String(30), default=None)
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    published_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)

    @property
    def start_at(self) -> datetime.datetime:
        return datetime.datetime.combine(self.date, self.start_time, LOCAL_TZ)

    @property
    def end_at(self) -> datetime.datetime:
        return datetime.datetime.combine(self.date, self.end_time, LOCAL_TZ)

    def is_upcoming(self, now: datetime.datetime) -> bool:
        """LIB-EVT section 28.1: ``published`` and now < start."""
        return self.status == "published" and now < self.start_at


class EventRegistration(Base):
    __tablename__ = "event_registrations"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(sa.ForeignKey("events.id"), index=True)
    member_id: Mapped[int] = mapped_column(sa.ForeignKey("members.id"), index=True)
    status: Mapped[str] = mapped_column(sa.String(10), index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    promoted_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    cancelled_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    attended_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    late_cancellation: Mapped[bool] = mapped_column(default=False)
    cancel_reason: Mapped[str | None] = mapped_column(sa.String(30), default=None)
    fee_id: Mapped[int | None] = mapped_column(sa.ForeignKey("fees.id", use_alter=True), default=None)

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_REGISTRATION_STATUSES


class EventBan(Base):
    __tablename__ = "event_bans"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(sa.ForeignKey("members.id"), index=True)
    starts_on: Mapped[datetime.date] = mapped_column(sa.Date)
    ends_on: Mapped[datetime.date] = mapped_column(sa.Date)
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)

    def in_force_on(self, day: datetime.date) -> bool:
        return self.starts_on <= day <= self.ends_on
