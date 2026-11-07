"""Digital resource, license, loan, hold and session models (section 25.1)."""

from __future__ import annotations

import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from lms.core.db import Base
from lms.core.money import MoneyType
from lms.core.timeutil import TZDateTime


class DigitalResource(Base):
    __tablename__ = "digital_resources"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(sa.String(10), index=True)
    title: Mapped[str] = mapped_column(sa.String(200))
    # Normalized title (LIB-COM-30): the ordering key.
    title_key: Mapped[str] = mapped_column(sa.String(200), index=True)
    provider: Mapped[str] = mapped_column(sa.String(100))
    book_id: Mapped[int | None] = mapped_column(sa.ForeignKey("books.id"), default=None, index=True)
    loan_days: Mapped[int | None] = mapped_column(default=None)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)


class DigitalLicense(Base):
    __tablename__ = "digital_licenses"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    resource_id: Mapped[int] = mapped_column(sa.ForeignKey("digital_resources.id"), index=True)
    model: Mapped[str] = mapped_column(sa.String(12))
    copies: Mapped[int]
    starts_on: Mapped[datetime.date] = mapped_column(sa.Date)
    ends_on: Mapped[datetime.date | None] = mapped_column(sa.Date, default=None)
    cost: Mapped[Decimal] = mapped_column(MoneyType)
    order_id: Mapped[int | None] = mapped_column(sa.ForeignKey("purchase_orders.id"), default=None, index=True)
    cancelled_on: Mapped[datetime.date | None] = mapped_column(sa.Date, default=None)

    def counts_on(self, day: datetime.date) -> bool:
        """The license counts on ``day`` (25.1)."""
        return (
            self.starts_on <= day
            and (self.ends_on is None or day <= self.ends_on)
            and (self.cancelled_on is None or day < self.cancelled_on)
        )

    def status_on(self, today: datetime.date) -> str:
        if self.cancelled_on is not None:
            return "cancelled"
        if today < self.starts_on:
            return "pending"
        if self.ends_on is not None and self.ends_on < today:
            return "ended"
        return "active"


class DigitalLoan(Base):
    __tablename__ = "digital_loans"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    resource_id: Mapped[int] = mapped_column(sa.ForeignKey("digital_resources.id"), index=True)
    member_id: Mapped[int] = mapped_column(sa.ForeignKey("members.id"), index=True)
    hold_id: Mapped[int | None] = mapped_column(sa.ForeignKey("digital_holds.id"), default=None)
    borrowed_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    due_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    renewed: Mapped[bool] = mapped_column(default=False)
    renewed_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    status: Mapped[str] = mapped_column(sa.String(10), default="open", index=True)
    ended_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)

    def is_active(self, now: datetime.datetime) -> bool:
        """An ``open`` loan before its ``due_at`` (25.1)."""
        return self.status == "open" and now < self.due_at

    def effective_status(self, now: datetime.datetime) -> str:
        if self.status == "open" and now >= self.due_at:
            return "expired"
        return self.status

    def effective_ended_at(self, now: datetime.datetime) -> datetime.datetime | None:
        if self.status == "open" and now >= self.due_at:
            return self.due_at
        return self.ended_at


class DigitalHold(Base):
    __tablename__ = "digital_holds"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    resource_id: Mapped[int] = mapped_column(sa.ForeignKey("digital_resources.id"), index=True)
    member_id: Mapped[int] = mapped_column(sa.ForeignKey("members.id"), index=True)
    status: Mapped[str] = mapped_column(sa.String(10), default="waiting", index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    ready_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    ready_until: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    closed_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    cancel_reason: Mapped[str | None] = mapped_column(sa.String(30), default=None)

    def is_lapsed(self, now: datetime.datetime) -> bool:
        """A ``ready`` hold past its ``ready_until`` (25.1)."""
        return self.status == "ready" and self.ready_until is not None and now > self.ready_until

    def is_kept(self, now: datetime.datetime) -> bool:
        return self.status == "ready" and not self.is_lapsed(now)


class DigitalSession(Base):
    __tablename__ = "digital_sessions"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    resource_id: Mapped[int] = mapped_column(sa.ForeignKey("digital_resources.id"), index=True)
    member_id: Mapped[int] = mapped_column(sa.ForeignKey("members.id"), index=True)
    started_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    expires_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    closed_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)

    def is_open(self, now: datetime.datetime) -> bool:
        return self.closed_at is None and now < self.expires_at
