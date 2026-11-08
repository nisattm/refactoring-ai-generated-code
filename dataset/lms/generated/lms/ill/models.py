"""Partner, incoming request and outgoing request models (section 26.1)."""

from __future__ import annotations

import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from lms.core.db import Base
from lms.core.money import MoneyType
from lms.core.timeutil import TZDateTime

# Statuses of an open incoming request (26.2).
OPEN_STATUSES = ("requested", "sent", "rejected", "received", "on_loan")


class IllPartner(Base):
    __tablename__ = "ill_partners"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(sa.String(10), unique=True)
    name: Mapped[str] = mapped_column(sa.String(200))
    email: Mapped[str] = mapped_column(sa.String(254))
    request_fee: Mapped[Decimal] = mapped_column(MoneyType)
    daily_late_fee: Mapped[Decimal] = mapped_column(MoneyType)
    max_outgoing: Mapped[int]
    is_active: Mapped[bool] = mapped_column(default=True)


class IllRequest(Base):
    """An incoming request: the library borrows a book for a member."""

    __tablename__ = "ill_requests"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(sa.ForeignKey("members.id"), index=True)
    title: Mapped[str] = mapped_column(sa.String(200))
    author: Mapped[str] = mapped_column(sa.String(200))
    isbn: Mapped[str | None] = mapped_column(sa.String(13), default=None)
    status: Mapped[str] = mapped_column(sa.String(12), default="requested", index=True)
    partner_id: Mapped[int | None] = mapped_column(sa.ForeignKey("ill_partners.id"), index=True, default=None)
    tried_partner_ids: Mapped[list[int]] = mapped_column(sa.JSON, default=list)
    pickup_branch_id: Mapped[int | None] = mapped_column(sa.ForeignKey("branches.id"), index=True, default=None)
    received_on: Mapped[datetime.date | None] = mapped_column(sa.Date, default=None)
    collect_until: Mapped[datetime.date | None] = mapped_column(sa.Date, default=None)
    partner_due_on: Mapped[datetime.date | None] = mapped_column(sa.Date, default=None)
    due_on: Mapped[datetime.date | None] = mapped_column(sa.Date, default=None)
    replacement_cost: Mapped[Decimal | None] = mapped_column(MoneyType, default=None)
    renewal: Mapped[str] = mapped_column(sa.String(10), default="none")
    collected_on: Mapped[datetime.date | None] = mapped_column(sa.Date, default=None)
    returned_on: Mapped[datetime.date | None] = mapped_column(sa.Date, default=None)
    closed_on: Mapped[datetime.date | None] = mapped_column(sa.Date, default=None)
    cancel_reason: Mapped[str | None] = mapped_column(sa.String(30), default=None)
    reject_reason: Mapped[str | None] = mapped_column(sa.String(200), default=None)
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    # Fees of the partner at the time of sending (LIB-ILL-02); not part of the API.
    stored_request_fee: Mapped[Decimal | None] = mapped_column(MoneyType, default=None)
    stored_daily_late_fee: Mapped[Decimal | None] = mapped_column(MoneyType, default=None)


class IllRequestAction(Base):
    """A send or reject action of an incoming request, for the activity report (LIB-ILL-38)."""

    __tablename__ = "ill_request_actions"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(sa.ForeignKey("ill_requests.id"), index=True)
    partner_id: Mapped[int] = mapped_column(sa.ForeignKey("ill_partners.id"), index=True)
    action: Mapped[str] = mapped_column(sa.String(10))
    on_date: Mapped[datetime.date] = mapped_column(sa.Date)


class IllOutgoing(Base):
    """An outgoing request: the library lends a copy to a partner."""

    __tablename__ = "ill_outgoing"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    partner_id: Mapped[int] = mapped_column(sa.ForeignKey("ill_partners.id"), index=True)
    book_id: Mapped[int] = mapped_column(sa.ForeignKey("books.id"), index=True)
    status: Mapped[str] = mapped_column(sa.String(10), default="requested", index=True)
    copy_id: Mapped[int | None] = mapped_column(sa.ForeignKey("copies.id"), default=None)
    shipped_on: Mapped[datetime.date | None] = mapped_column(sa.Date, default=None)
    due_on: Mapped[datetime.date | None] = mapped_column(sa.Date, default=None)
    returned_on: Mapped[datetime.date | None] = mapped_column(sa.Date, default=None)
    amount_due: Mapped[Decimal | None] = mapped_column(MoneyType, default=None)
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    # Not part of the API: the date it was reported lost, for the activity report (LIB-ILL-38).
    lost_on: Mapped[datetime.date | None] = mapped_column(sa.Date, default=None)
