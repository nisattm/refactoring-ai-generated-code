"""Equipment type, item, training, loan and reservation models (section 24.2)."""

from __future__ import annotations

import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from lms.core.db import Base
from lms.core.money import MoneyType
from lms.core.timeutil import TZDateTime


class EquipmentType(Base):
    __tablename__ = "equipment_types"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(sa.String(20), unique=True)
    name: Mapped[str] = mapped_column(sa.String(200))
    period_unit: Mapped[str] = mapped_column(sa.String(12))
    period: Mapped[int]
    hourly_late_fee: Mapped[Decimal] = mapped_column(MoneyType)
    requires_training: Mapped[bool] = mapped_column(default=False)
    max_open_per_member: Mapped[int]
    is_active: Mapped[bool] = mapped_column(default=True)


class EquipmentItem(Base):
    __tablename__ = "equipment_items"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    type_id: Mapped[int] = mapped_column(sa.ForeignKey("equipment_types.id"), index=True)
    asset_tag: Mapped[str] = mapped_column(sa.String(20), unique=True)
    serial_no: Mapped[str] = mapped_column(sa.String(50))
    branch_id: Mapped[int] = mapped_column(sa.ForeignKey("branches.id"), index=True)
    value: Mapped[Decimal] = mapped_column(MoneyType)
    status: Mapped[str] = mapped_column(sa.String(10), default="available", index=True)
    acquired_on: Mapped[datetime.date] = mapped_column(sa.Date)
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)


class EquipmentTraining(Base):
    __tablename__ = "equipment_trainings"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(sa.ForeignKey("members.id"), index=True)
    type_id: Mapped[int] = mapped_column(sa.ForeignKey("equipment_types.id"), index=True)
    completed_on: Mapped[datetime.date] = mapped_column(sa.Date)
    valid_until: Mapped[datetime.date] = mapped_column(sa.Date)
    recorded_by: Mapped[int] = mapped_column(sa.ForeignKey("users.id"))
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)


class EquipmentLoan(Base):
    __tablename__ = "equipment_loans"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(sa.ForeignKey("equipment_items.id"), index=True)
    member_id: Mapped[int] = mapped_column(sa.ForeignKey("members.id"), index=True)
    # Not part of the API under this name besides ``type_id`` of ``EquipmentLoanOut``; the item's type never changes.
    type_id: Mapped[int] = mapped_column(sa.ForeignKey("equipment_types.id"), index=True)
    branch_id: Mapped[int] = mapped_column(sa.ForeignKey("branches.id"), index=True)
    reservation_id: Mapped[int | None] = mapped_column(sa.ForeignKey("equipment_reservations.id"), default=None)
    loaned_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    due_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    extended: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(sa.String(10), default="open", index=True)
    returned_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    return_condition: Mapped[str | None] = mapped_column(sa.String(10), default=None)
    late_hours: Mapped[int | None] = mapped_column(default=None)
    lent_by: Mapped[int | None] = mapped_column(sa.ForeignKey("users.id"), default=None)
    received_by: Mapped[int | None] = mapped_column(sa.ForeignKey("users.id"), default=None)
    # Copied from the type when the loan is created (LIB-EQ-04); not part of the API.
    hourly_late_fee: Mapped[Decimal] = mapped_column(MoneyType)
    # Not part of the API: when the loan was closed (returned or lost), for the usage report (LIB-EQ-40).
    closed_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)


class EquipmentReservation(Base):
    __tablename__ = "equipment_reservations"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    type_id: Mapped[int] = mapped_column(sa.ForeignKey("equipment_types.id"), index=True)
    branch_id: Mapped[int] = mapped_column(sa.ForeignKey("branches.id"), index=True)
    member_id: Mapped[int] = mapped_column(sa.ForeignKey("members.id"), index=True)
    starts_at: Mapped[datetime.datetime] = mapped_column(TZDateTime, index=True)
    ends_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    status: Mapped[str] = mapped_column(sa.String(10), default="booked", index=True)
    loan_id: Mapped[int | None] = mapped_column(default=None)
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    closed_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    cancel_reason: Mapped[str | None] = mapped_column(sa.String(30), default=None)
