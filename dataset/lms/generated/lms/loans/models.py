"""Loan model (section 9.1)."""

from __future__ import annotations

import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from lms.core.db import Base
from lms.core.money import MoneyType


class Loan(Base):
    __tablename__ = "loans"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    copy_id: Mapped[int] = mapped_column(sa.ForeignKey("copies.id"), index=True)
    member_id: Mapped[int] = mapped_column(sa.ForeignKey("members.id"), index=True)
    branch_id: Mapped[int] = mapped_column(sa.ForeignKey("branches.id"), index=True)
    loan_date: Mapped[datetime.date] = mapped_column(sa.Date)
    due_date: Mapped[datetime.date] = mapped_column(sa.Date)
    loan_period_days: Mapped[int]
    max_renewals: Mapped[int]
    daily_fee: Mapped[Decimal] = mapped_column(MoneyType)
    renewal_count: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(sa.String(10), default="open", index=True)
    returned_on: Mapped[datetime.date | None] = mapped_column(sa.Date, default=None)
    return_branch_id: Mapped[int | None] = mapped_column(sa.ForeignKey("branches.id"), default=None)
    condition_on_return: Mapped[str | None] = mapped_column(sa.String(10), default=None)
    late_days: Mapped[int | None] = mapped_column(default=None)
    created_by: Mapped[int] = mapped_column(sa.ForeignKey("users.id"))
