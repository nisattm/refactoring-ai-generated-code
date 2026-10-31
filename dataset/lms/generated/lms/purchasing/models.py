"""Purchasing models (section 18.1)."""

from __future__ import annotations

import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from lms.core.db import Base
from lms.core.money import MoneyType
from lms.core.timeutil import TZDateTime


class Supplier(Base):
    __tablename__ = "suppliers"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(200))
    # Normalized name (LIB-COM-30): the uniqueness and ordering key.
    name_key: Mapped[str] = mapped_column(sa.String(200), unique=True)
    email: Mapped[str | None] = mapped_column(sa.String(254), default=None)
    phone: Mapped[str | None] = mapped_column(sa.String(40), default=None)
    is_active: Mapped[bool] = mapped_column(default=True)


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(sa.ForeignKey("suppliers.id"), index=True)
    branch_id: Mapped[int] = mapped_column(sa.ForeignKey("branches.id"), index=True)
    status: Mapped[str] = mapped_column(sa.String(20), default="draft", index=True)
    created_by: Mapped[int] = mapped_column(sa.ForeignKey("users.id"))
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    ordered_on: Mapped[datetime.date | None] = mapped_column(sa.Date, default=None)


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"
    __table_args__ = (
        sa.UniqueConstraint("order_id", "book_id"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(sa.ForeignKey("purchase_orders.id"), index=True)
    book_id: Mapped[int] = mapped_column(sa.ForeignKey("books.id"), index=True)
    quantity: Mapped[int]
    unit_price: Mapped[Decimal] = mapped_column(MoneyType)
    received_quantity: Mapped[int] = mapped_column(default=0)
