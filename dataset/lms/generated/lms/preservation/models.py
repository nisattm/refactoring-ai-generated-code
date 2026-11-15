"""Inspection, budget, repair job and shipment models (section 31.1)."""

from __future__ import annotations

import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from lms.core.db import Base
from lms.core.money import MoneyType
from lms.core.timeutil import TZDateTime

OPEN_STATUSES = ("requested", "approved", "sent")


class Inspection(Base):
    __tablename__ = "copy_inspections"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    copy_id: Mapped[int] = mapped_column(sa.ForeignKey("copies.id"), index=True)
    condition: Mapped[str] = mapped_column(sa.String(10))
    note: Mapped[str] = mapped_column(sa.String(500), default="")
    inspected_by: Mapped[int] = mapped_column(sa.ForeignKey("users.id"))
    inspected_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)


class Budget(Base):
    __tablename__ = "preservation_budgets"
    __table_args__ = (sa.UniqueConstraint("branch_id", "year"), {"sqlite_autoincrement": True})

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(sa.ForeignKey("branches.id"), index=True)
    year: Mapped[int]
    amount: Mapped[Decimal] = mapped_column(MoneyType)


class Shipment(Base):
    __tablename__ = "repair_shipments"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(sa.String(40))
    supplier_id: Mapped[int] = mapped_column(sa.ForeignKey("suppliers.id"), index=True)
    branch_id: Mapped[int] = mapped_column(sa.ForeignKey("branches.id"), index=True)
    sent_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)


class RepairJob(Base):
    __tablename__ = "repair_jobs"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    copy_id: Mapped[int] = mapped_column(sa.ForeignKey("copies.id"), index=True)
    branch_id: Mapped[int] = mapped_column(sa.ForeignKey("branches.id"), index=True)
    kind: Mapped[str] = mapped_column(sa.String(15))
    provider: Mapped[str] = mapped_column(sa.String(10))
    supplier_id: Mapped[int | None] = mapped_column(sa.ForeignKey("suppliers.id"), index=True, default=None)
    priority: Mapped[str] = mapped_column(sa.String(10), default="normal")
    estimated_cost: Mapped[Decimal] = mapped_column(MoneyType)
    actual_cost: Mapped[Decimal | None] = mapped_column(MoneyType, default=None)
    status: Mapped[str] = mapped_column(sa.String(10), default="requested", index=True)
    outcome: Mapped[str | None] = mapped_column(sa.String(15), default=None)
    loan_id: Mapped[int | None] = mapped_column(sa.ForeignKey("loans.id"), default=None)
    shipment_id: Mapped[int | None] = mapped_column(sa.ForeignKey("repair_shipments.id"), index=True, default=None)
    note: Mapped[str] = mapped_column(sa.String(500), default="")
    cost_note: Mapped[str] = mapped_column(sa.String(500), default="")
    cost_overrun: Mapped[bool] = mapped_column(default=False)
    requested_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    approved_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    sent_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    returned_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    due_back: Mapped[datetime.date | None] = mapped_column(sa.Date, default=None)
    cancel_reason: Mapped[str | None] = mapped_column(sa.String(15), default=None)
    overdue_marked_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES

    def is_overdue(self, today: datetime.date) -> bool:
        return self.status == "sent" and self.due_back is not None and today > self.due_back
