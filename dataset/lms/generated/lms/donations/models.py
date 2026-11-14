"""Donor, donation, donation item and receiving models (section 30.1)."""

from __future__ import annotations

import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from lms.core.db import Base
from lms.core.money import MoneyType
from lms.core.timeutil import TZDateTime

OPEN_STATUSES = ("offered", "accepted", "partially_received")


class Donor(Base):
    __tablename__ = "donors"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(sa.String(15))
    name: Mapped[str] = mapped_column(sa.String(200))
    # Normalized name (LIB-COM-30): the ordering and search key.
    name_key: Mapped[str] = mapped_column(sa.String(200), index=True)
    email: Mapped[str | None] = mapped_column(sa.String(254), default=None)
    # Normalized e-mail (LIB-COM-30): the uniqueness key.
    email_key: Mapped[str | None] = mapped_column(sa.String(254), unique=True, default=None)
    phone: Mapped[str | None] = mapped_column(sa.String(40), default=None)
    member_id: Mapped[int | None] = mapped_column(sa.ForeignKey("members.id"), unique=True, default=None)
    anonymous: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    merged_into_id: Mapped[int | None] = mapped_column(sa.ForeignKey("donors.id"), default=None)
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)


class Donation(Base):
    __tablename__ = "donations"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    donor_id: Mapped[int] = mapped_column(sa.ForeignKey("donors.id"), index=True)
    branch_id: Mapped[int] = mapped_column(sa.ForeignKey("branches.id"), index=True)
    status: Mapped[str] = mapped_column(sa.String(20), default="offered", index=True)
    note: Mapped[str] = mapped_column(sa.String(500), default="")
    offered_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    received_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    expected_by: Mapped[datetime.date | None] = mapped_column(sa.Date, default=None)
    cancel_reason: Mapped[str | None] = mapped_column(sa.String(30), default=None)
    receipt_no: Mapped[str | None] = mapped_column(sa.String(20), default=None)

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES


class DonationItem(Base):
    __tablename__ = "donation_items"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    donation_id: Mapped[int] = mapped_column(sa.ForeignKey("donations.id"), index=True)
    title: Mapped[str] = mapped_column(sa.String(300))
    author_text: Mapped[str] = mapped_column(sa.String(200), default="")
    isbn: Mapped[str | None] = mapped_column(sa.String(13), default=None)
    publication_year: Mapped[int]
    condition: Mapped[str] = mapped_column(sa.String(10))
    quantity: Mapped[int]
    decision: Mapped[str] = mapped_column(sa.String(10), default="pending")
    decline_reason: Mapped[str | None] = mapped_column(sa.String(20), default=None)
    book_id: Mapped[int | None] = mapped_column(sa.ForeignKey("books.id"), index=True, default=None)
    accepted_quantity: Mapped[int | None] = mapped_column(default=None)
    estimated_value: Mapped[Decimal | None] = mapped_column(MoneyType, default=None)
    received_quantity: Mapped[int] = mapped_column(default=0)


class Receiving(Base):
    __tablename__ = "donation_receivings"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    donation_id: Mapped[int] = mapped_column(sa.ForeignKey("donations.id"), index=True)
    item_id: Mapped[int] = mapped_column(sa.ForeignKey("donation_items.id"), index=True)
    copies: Mapped[int]
    value: Mapped[Decimal] = mapped_column(MoneyType)
    received_on: Mapped[datetime.date] = mapped_column(sa.Date, index=True)
