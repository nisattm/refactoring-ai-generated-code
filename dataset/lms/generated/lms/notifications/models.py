"""Notification model (section 14.1)."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from lms.core.db import Base
from lms.core.timeutil import TZDateTime


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(sa.ForeignKey("members.id"), index=True)
    type: Mapped[str] = mapped_column(sa.String(30), index=True)
    message: Mapped[str] = mapped_column(sa.String(1000))
    loan_id: Mapped[int | None] = mapped_column(sa.ForeignKey("loans.id"), default=None, index=True)
    reservation_id: Mapped[int | None] = mapped_column(sa.ForeignKey("reservations.id"), default=None)
    fee_id: Mapped[int | None] = mapped_column(sa.ForeignKey("fees.id"), default=None)
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    read_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    # Not part of the API: the date a reminder is about (due date or day of notice), for LIB-NOT-06.
    reminder_date: Mapped[datetime.date | None] = mapped_column(sa.Date, default=None)
