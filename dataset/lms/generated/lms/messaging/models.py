"""Announcement and message thread models (section 35.1)."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from lms.core.db import Base
from lms.core.timeutil import TZDateTime

MEMBERSHIP_TYPES = ("student", "academic", "staff", "guest")
CATEGORIES = ("general", "loan", "fee", "room", "other")


class Announcement(Base):
    __tablename__ = "announcements"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(sa.String(200))
    body: Mapped[str] = mapped_column(sa.String(5000))
    branch_id: Mapped[int | None] = mapped_column(sa.ForeignKey("branches.id"), index=True, default=None)
    # The audience as sent by the client (a list of membership types).
    audience: Mapped[list[str]] = mapped_column(sa.JSON)
    priority: Mapped[str] = mapped_column(sa.String(10), default="normal")
    pinned: Mapped[bool] = mapped_column(default=False)
    publish_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    expires_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    status: Mapped[str] = mapped_column(sa.String(10), default="draft", index=True)
    published_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    withdrawn_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)

    def is_live(self, now: datetime.datetime) -> bool:
        """35.1: ``published``, ``publish_at`` <= now and not expired."""
        return (
            self.status == "published"
            and self.publish_at <= now
            and (self.expires_at is None or now < self.expires_at)
        )


class ReadMark(Base):
    __tablename__ = "announcement_reads"
    __table_args__ = (sa.UniqueConstraint("announcement_id", "member_id"), {"sqlite_autoincrement": True})

    id: Mapped[int] = mapped_column(primary_key=True)
    announcement_id: Mapped[int] = mapped_column(sa.ForeignKey("announcements.id"), index=True)
    member_id: Mapped[int] = mapped_column(sa.ForeignKey("members.id"), index=True)
    read_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)


class Thread(Base):
    __tablename__ = "threads"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(sa.ForeignKey("members.id"), index=True)
    branch_id: Mapped[int] = mapped_column(sa.ForeignKey("branches.id"), index=True)
    subject: Mapped[str] = mapped_column(sa.String(200))
    category: Mapped[str] = mapped_column(sa.String(10), default="general")
    loan_id: Mapped[int | None] = mapped_column(sa.ForeignKey("loans.id"), default=None)
    fee_id: Mapped[int | None] = mapped_column(sa.ForeignKey("fees.id"), default=None)
    status: Mapped[str] = mapped_column(sa.String(10), default="open", index=True)
    assigned_to: Mapped[int | None] = mapped_column(sa.ForeignKey("users.id"), index=True, default=None)
    due_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    close_reason: Mapped[str | None] = mapped_column(sa.String(20), default=None)
    rating: Mapped[int | None] = mapped_column(default=None)
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    closed_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    first_reply_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)


class Message(Base):
    __tablename__ = "thread_messages"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[int] = mapped_column(sa.ForeignKey("threads.id"), index=True)
    author: Mapped[str] = mapped_column(sa.String(10))
    user_id: Mapped[int | None] = mapped_column(sa.ForeignKey("users.id"), default=None)
    body: Mapped[str] = mapped_column(sa.String(2000))
    internal: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    read_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
