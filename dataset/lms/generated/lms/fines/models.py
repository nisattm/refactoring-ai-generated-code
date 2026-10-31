"""Fee and payment models (section 11.1)."""

from __future__ import annotations

import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from lms.core.db import Base
from lms.core.money import MoneyType
from lms.core.timeutil import TZDateTime


class Fee(Base):
    __tablename__ = "fees"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(sa.ForeignKey("members.id"), index=True)
    loan_id: Mapped[int | None] = mapped_column(sa.ForeignKey("loans.id"), index=True, default=None)
    kind: Mapped[str] = mapped_column(sa.String(20))
    amount: Mapped[Decimal] = mapped_column(MoneyType)
    paid_amount: Mapped[Decimal] = mapped_column(MoneyType, default=Decimal("0.00"))
    status: Mapped[str] = mapped_column(sa.String(10), default="open", index=True)
    created_on: Mapped[datetime.date] = mapped_column(sa.Date)
    waived_by: Mapped[int | None] = mapped_column(sa.ForeignKey("users.id"), default=None)
    waived_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    waive_reason: Mapped[str | None] = mapped_column(sa.String(500), default=None)

    @property
    def outstanding(self) -> Decimal:
        """``amount`` − ``paid_amount`` for open fees, zero otherwise (``FeeOut``)."""
        return self.amount - self.paid_amount if self.status == "open" else Decimal("0.00")


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(sa.ForeignKey("members.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(MoneyType)
    method: Mapped[str] = mapped_column(sa.String(10))
    received_by: Mapped[int] = mapped_column(sa.ForeignKey("users.id"))
    paid_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)


class PaymentAllocation(Base):
    __tablename__ = "payment_allocations"

    payment_id: Mapped[int] = mapped_column(sa.ForeignKey("payments.id"), primary_key=True)
    fee_id: Mapped[int] = mapped_column(sa.ForeignKey("fees.id"), primary_key=True)
    position: Mapped[int]
    amount: Mapped[Decimal] = mapped_column(MoneyType)
