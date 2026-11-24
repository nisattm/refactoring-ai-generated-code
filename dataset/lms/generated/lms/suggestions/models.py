"""Suggestion and support models (section 33.1)."""

from __future__ import annotations

import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from lms.core.db import Base
from lms.core.money import MoneyType
from lms.core.timeutil import TZDateTime

OPEN_STATUSES = ("submitted", "approved", "ordered")


class Suggestion(Base):
    __tablename__ = "suggestions"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(sa.ForeignKey("members.id"), index=True)
    title: Mapped[str] = mapped_column(sa.String(300))
    author_text: Mapped[str] = mapped_column(sa.String(200), default="")
    isbn: Mapped[str | None] = mapped_column(sa.String(13), index=True, default=None)
    publication_year: Mapped[int | None] = mapped_column(default=None)
    reason: Mapped[str] = mapped_column(sa.String(500), default="")
    branch_id: Mapped[int] = mapped_column(sa.ForeignKey("branches.id"), index=True)
    status: Mapped[str] = mapped_column(sa.String(10), default="submitted", index=True)
    reject_reason: Mapped[str | None] = mapped_column(sa.String(20), default=None)
    review_note: Mapped[str] = mapped_column(sa.String(500), default="")
    book_id: Mapped[int | None] = mapped_column(sa.ForeignKey("books.id"), index=True, default=None)
    quantity: Mapped[int | None] = mapped_column(default=None)
    estimated_price: Mapped[Decimal | None] = mapped_column(MoneyType, default=None)
    purchase_order_id: Mapped[int | None] = mapped_column(sa.ForeignKey("purchase_orders.id"), index=True, default=None)
    merged_into_id: Mapped[int | None] = mapped_column(sa.ForeignKey("suggestions.id"), default=None)
    withdraw_reason: Mapped[str | None] = mapped_column(sa.String(20), default=None)
    submitted_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    ordered_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    available_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES


class Support(Base):
    __tablename__ = "suggestion_supports"
    __table_args__ = (sa.UniqueConstraint("suggestion_id", "member_id"), {"sqlite_autoincrement": True})

    id: Mapped[int] = mapped_column(primary_key=True)
    suggestion_id: Mapped[int] = mapped_column(sa.ForeignKey("suggestions.id"), index=True)
    member_id: Mapped[int] = mapped_column(sa.ForeignKey("members.id"), index=True)
    reserve_on_arrival: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
