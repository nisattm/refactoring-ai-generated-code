"""Reservation model (section 10.1)."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from lms.core.db import Base
from lms.core.timeutil import TZDateTime

ACTIVE_STATUSES = ("waiting", "in_transit", "ready")


class Reservation(Base):
    __tablename__ = "reservations"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(sa.ForeignKey("books.id"), index=True)
    member_id: Mapped[int] = mapped_column(sa.ForeignKey("members.id"), index=True)
    pickup_branch_id: Mapped[int] = mapped_column(sa.ForeignKey("branches.id"), index=True)
    status: Mapped[str] = mapped_column(sa.String(12), default="waiting", index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    copy_id: Mapped[int | None] = mapped_column(sa.ForeignKey("copies.id"), default=None, index=True)
    ready_on: Mapped[datetime.date | None] = mapped_column(sa.Date, default=None)
    hold_until: Mapped[datetime.date | None] = mapped_column(sa.Date, default=None)
    closed_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    cancel_reason: Mapped[str | None] = mapped_column(sa.String(20), default=None)

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_STATUSES
