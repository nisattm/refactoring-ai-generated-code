"""Inventory count, expected copy, scan and line models (section 32.1)."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from lms.core.db import Base
from lms.core.timeutil import TZDateTime


class InventoryCount(Base):
    __tablename__ = "inventory_counts"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(sa.ForeignKey("branches.id"), index=True)
    name: Mapped[str] = mapped_column(sa.String(200))
    shelf_prefix: Mapped[str | None] = mapped_column(sa.String(20), default=None)
    status: Mapped[str] = mapped_column(sa.String(10), default="open", index=True)
    cancel_reason: Mapped[str | None] = mapped_column(sa.String(15), default=None)
    started_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    closed_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    applied_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)


class ExpectedCopy(Base):
    """The snapshot of a count (LIB-INV-02): one row per expected copy."""

    __tablename__ = "inventory_expected"

    count_id: Mapped[int] = mapped_column(sa.ForeignKey("inventory_counts.id"), primary_key=True)
    copy_id: Mapped[int] = mapped_column(sa.ForeignKey("copies.id"), primary_key=True, index=True)


class InventoryScan(Base):
    __tablename__ = "inventory_scans"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    count_id: Mapped[int] = mapped_column(sa.ForeignKey("inventory_counts.id"), index=True)
    barcode: Mapped[str] = mapped_column(sa.String(200))
    copy_id: Mapped[int | None] = mapped_column(sa.ForeignKey("copies.id"), index=True, default=None)
    result: Mapped[str] = mapped_column(sa.String(20), index=True)
    scanned_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    scanned_by: Mapped[int] = mapped_column(sa.ForeignKey("users.id"))
    # Not part of the API: set when applying the count changed the copy of this scan (LIB-INV-18, LIB-INV-32).
    applied: Mapped[bool] = mapped_column(default=False, server_default=sa.false())


class InventoryLine(Base):
    __tablename__ = "inventory_lines"

    count_id: Mapped[int] = mapped_column(sa.ForeignKey("inventory_counts.id"), primary_key=True)
    copy_id: Mapped[int] = mapped_column(sa.ForeignKey("copies.id"), primary_key=True)
    outcome: Mapped[str] = mapped_column(sa.String(10), index=True)
