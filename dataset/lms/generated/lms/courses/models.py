"""Course, enrollment, reading list item and reserve loan models (section 29.1)."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from lms.core.db import Base
from lms.core.timeutil import TZDateTime

OPEN_COURSE_STATUSES = ("draft", "active")


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (
        sa.UniqueConstraint("code", "term"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(sa.String(10))
    title: Mapped[str] = mapped_column(sa.String(200))
    term: Mapped[str] = mapped_column(sa.String(12), index=True)
    instructor_id: Mapped[int] = mapped_column(sa.ForeignKey("members.id"), index=True)
    branch_id: Mapped[int] = mapped_column(sa.ForeignKey("branches.id"), index=True)
    starts_on: Mapped[datetime.date] = mapped_column(sa.Date)
    ends_on: Mapped[datetime.date] = mapped_column(sa.Date)
    enrollment_limit: Mapped[int] = mapped_column(default=100)
    status: Mapped[str] = mapped_column(sa.String(10), default="draft", index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    activated_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    closed_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)

    def is_running_on(self, day: datetime.date) -> bool:
        """29.1: ``active`` and ``starts_on`` <= day <= ``ends_on``."""
        return self.status == "active" and self.starts_on <= day <= self.ends_on


class Enrollment(Base):
    __tablename__ = "course_enrollments"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(sa.ForeignKey("courses.id"), index=True)
    member_id: Mapped[int] = mapped_column(sa.ForeignKey("members.id"), index=True)
    status: Mapped[str] = mapped_column(sa.String(10), default="enrolled", index=True)
    enrolled_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    dropped_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    drop_reason: Mapped[str | None] = mapped_column(sa.String(20), default=None)


class ReadingListItem(Base):
    __tablename__ = "reading_list_items"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(sa.ForeignKey("courses.id"), index=True)
    book_id: Mapped[int] = mapped_column(sa.ForeignKey("books.id"), index=True)
    kind: Mapped[str] = mapped_column(sa.String(12), default="required")
    loan_period: Mapped[str] = mapped_column(sa.String(2), default="2h")
    copies_wanted: Mapped[int] = mapped_column(default=1)
    note: Mapped[str] = mapped_column(sa.String(500), default="")
    position: Mapped[int | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(sa.String(10), default="requested", index=True)
    added_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)


class ReserveLoan(Base):
    __tablename__ = "reserve_loans"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    copy_id: Mapped[int] = mapped_column(sa.ForeignKey("copies.id"), index=True)
    item_id: Mapped[int] = mapped_column(sa.ForeignKey("reading_list_items.id"), index=True)
    course_id: Mapped[int] = mapped_column(sa.ForeignKey("courses.id"), index=True)
    member_id: Mapped[int] = mapped_column(sa.ForeignKey("members.id"), index=True)
    lent_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    due_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    # The item's ``loan_period`` at lending (LIB-CRS-14, LIB-CRS-29).
    loan_period: Mapped[str] = mapped_column(sa.String(2))
    renewed: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(sa.String(10), default="open", index=True)
    returned_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    late_minutes: Mapped[int | None] = mapped_column(default=None)
    fee_id: Mapped[int | None] = mapped_column(sa.ForeignKey("fees.id", use_alter=True), default=None)
    created_by: Mapped[int] = mapped_column(sa.ForeignKey("users.id"))
