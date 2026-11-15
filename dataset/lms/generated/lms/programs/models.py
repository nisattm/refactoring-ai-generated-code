"""Reading program models (section 34.1)."""

from __future__ import annotations

import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from lms.core.db import Base
from lms.core.money import MoneyType
from lms.core.timeutil import TZDateTime

LEVELS = ("none", "bronze", "silver", "gold")
BOOK_SOURCES = ("loan", "manual")


class Program(Base):
    __tablename__ = "programs"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(200))
    # Normalized name (LIB-COM-30): unique among programs that are not ``cancelled``.
    name_key: Mapped[str] = mapped_column(sa.String(200), index=True)
    description: Mapped[str] = mapped_column(sa.String(1000), default="")
    branch_id: Mapped[int | None] = mapped_column(sa.ForeignKey("branches.id"), index=True, default=None)
    audience: Mapped[str] = mapped_column(sa.String(10), default="all")
    starts_on: Mapped[datetime.date] = mapped_column(sa.Date)
    ends_on: Mapped[datetime.date] = mapped_column(sa.Date)
    goal_books: Mapped[int]
    max_participants: Mapped[int | None] = mapped_column(default=None)
    reward_waiver: Mapped[Decimal] = mapped_column(MoneyType, default=Decimal("0.00"))
    status: Mapped[str] = mapped_column(sa.String(10), default="draft", index=True)
    published_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    closed_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)

    def is_running(self, day: datetime.date) -> bool:
        """34.1: ``published`` and ``starts_on`` <= day <= ``ends_on``."""
        return self.status == "published" and self.starts_on <= day <= self.ends_on


class ProgramBook(Base):
    __tablename__ = "program_books"
    __table_args__ = (sa.UniqueConstraint("program_id", "book_id"), {"sqlite_autoincrement": True})

    id: Mapped[int] = mapped_column(primary_key=True)
    program_id: Mapped[int] = mapped_column(sa.ForeignKey("programs.id"), index=True)
    book_id: Mapped[int] = mapped_column(sa.ForeignKey("books.id"), index=True)


class Participation(Base):
    __tablename__ = "program_participations"
    __table_args__ = (sa.UniqueConstraint("program_id", "member_id"), {"sqlite_autoincrement": True})

    id: Mapped[int] = mapped_column(primary_key=True)
    program_id: Mapped[int] = mapped_column(sa.ForeignKey("programs.id"), index=True)
    member_id: Mapped[int] = mapped_column(sa.ForeignKey("members.id"), index=True)
    status: Mapped[str] = mapped_column(sa.String(10), default="active", index=True)
    joined_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    left_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    leave_reason: Mapped[str | None] = mapped_column(sa.String(20), default=None)
    public: Mapped[bool] = mapped_column(default=True)
    points: Mapped[int] = mapped_column(default=0)
    books: Mapped[int] = mapped_column(default=0)
    level: Mapped[str] = mapped_column(sa.String(6), default="none")
    completed_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    reward_waived: Mapped[Decimal] = mapped_column(MoneyType, default=Decimal("0.00"))
    # Not part of the API: order of completion in the program (LIB-RDP-34), the highest level reached
    # (LIB-RDP-30) and the ending reminder already sent (LIB-RDP-35).
    completion_no: Mapped[int | None] = mapped_column(default=None)
    top_level: Mapped[str] = mapped_column(sa.String(6), default="none")
    reminded_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)


class Entry(Base):
    __tablename__ = "program_entries"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    participation_id: Mapped[int] = mapped_column(sa.ForeignKey("program_participations.id"), index=True)
    source: Mapped[str] = mapped_column(sa.String(10))
    book_id: Mapped[int | None] = mapped_column(sa.ForeignKey("books.id"), index=True, default=None)
    loan_id: Mapped[int | None] = mapped_column(sa.ForeignKey("loans.id"), default=None)
    event_id: Mapped[int | None] = mapped_column(sa.ForeignKey("events.id"), default=None)
    points: Mapped[int]
    on: Mapped[datetime.date] = mapped_column("on_date", sa.Date)
    note: Mapped[str] = mapped_column(sa.String(200), default="")
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
