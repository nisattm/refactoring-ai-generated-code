"""Room, booking and ban models (section 23.1)."""

from __future__ import annotations

import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lms.core.clock import LOCAL_TZ
from lms.core.db import Base
from lms.core.timeutil import TZDateTime


class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (sa.UniqueConstraint("branch_id", "code"), {"sqlite_autoincrement": True})

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(sa.ForeignKey("branches.id"), index=True)
    code: Mapped[str] = mapped_column(sa.String(10))
    name: Mapped[str] = mapped_column(sa.String(200))
    kind: Mapped[str] = mapped_column(sa.String(10))
    capacity: Mapped[int]
    min_participants: Mapped[int]
    features: Mapped[list[Any]] = mapped_column(sa.JSON, default=list)
    opens_at: Mapped[datetime.time] = mapped_column(sa.Time)
    closes_at: Mapped[datetime.time] = mapped_column(sa.Time)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)


class RoomBookingParticipant(Base):
    __tablename__ = "room_booking_participants"

    booking_id: Mapped[int] = mapped_column(sa.ForeignKey("room_bookings.id"), primary_key=True)
    member_id: Mapped[int] = mapped_column(sa.ForeignKey("members.id"), primary_key=True, index=True)


class RoomBooking(Base):
    __tablename__ = "room_bookings"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(sa.ForeignKey("rooms.id"), index=True)
    member_id: Mapped[int] = mapped_column(sa.ForeignKey("members.id"), index=True)
    date: Mapped[datetime.date] = mapped_column(sa.Date, index=True)
    start_time: Mapped[datetime.time] = mapped_column(sa.Time)
    end_time: Mapped[datetime.time] = mapped_column(sa.Time)
    status: Mapped[str] = mapped_column(sa.String(12), default="booked", index=True)
    purpose: Mapped[str] = mapped_column(sa.String(200), default="")
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    created_by: Mapped[int] = mapped_column(sa.ForeignKey("users.id"))
    checked_in_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    closed_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    cancel_reason: Mapped[str | None] = mapped_column(sa.String(30), default=None)
    late_cancellation: Mapped[bool] = mapped_column(default=False)

    participants: Mapped[list[RoomBookingParticipant]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by=RoomBookingParticipant.member_id
    )

    @property
    def participant_ids(self) -> list[int]:
        return sorted(p.member_id for p in self.participants)

    @property
    def person_ids(self) -> list[int]:
        """Organizer first, then the participants in ascending order."""
        return [self.member_id, *self.participant_ids]

    @property
    def start_at(self) -> datetime.datetime:
        return datetime.datetime.combine(self.date, self.start_time, LOCAL_TZ)

    @property
    def end_at(self) -> datetime.datetime:
        return datetime.datetime.combine(self.date, self.end_time, LOCAL_TZ)

    @property
    def duration_minutes(self) -> int:
        return int((self.end_at - self.start_at).total_seconds() // 60)


class RoomBan(Base):
    __tablename__ = "room_bans"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(sa.ForeignKey("members.id"), index=True)
    starts_on: Mapped[datetime.date] = mapped_column(sa.Date)
    ends_on: Mapped[datetime.date] = mapped_column(sa.Date)
    reason: Mapped[str] = mapped_column(sa.String(10))
    note: Mapped[str] = mapped_column(sa.String(500), default="")
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    created_by: Mapped[int | None] = mapped_column(sa.ForeignKey("users.id"), default=None)
    lifted_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    lifted_by: Mapped[int | None] = mapped_column(sa.ForeignKey("users.id"), default=None)

    def in_force_on(self, day: datetime.date) -> bool:
        return self.lifted_at is None and self.starts_on <= day <= self.ends_on
