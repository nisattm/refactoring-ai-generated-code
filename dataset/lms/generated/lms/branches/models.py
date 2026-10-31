"""Branch and transfer models (section 17.1)."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from lms.core.db import Base
from lms.core.timeutil import TZDateTime


class Branch(Base):
    __tablename__ = "branches"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(sa.String(10), unique=True)
    name: Mapped[str] = mapped_column(sa.String(200))
    address: Mapped[str] = mapped_column(sa.String(300), default="")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)


class Transfer(Base):
    """A copy moving between branches (section 17.1). Only the start of a transfer exists so far."""

    __tablename__ = "transfers"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    copy_id: Mapped[int] = mapped_column(sa.ForeignKey("copies.id"), index=True)
    from_branch_id: Mapped[int] = mapped_column(sa.ForeignKey("branches.id"))
    to_branch_id: Mapped[int] = mapped_column(sa.ForeignKey("branches.id"))
    reason: Mapped[str] = mapped_column(sa.String(20))
    reservation_id: Mapped[int | None] = mapped_column(default=None)
    started_on: Mapped[datetime.date] = mapped_column(sa.Date)
    expected_on: Mapped[datetime.date] = mapped_column(sa.Date)
    status: Mapped[str] = mapped_column(sa.String(10), default="in_transit", index=True)
    received_on: Mapped[datetime.date | None] = mapped_column(sa.Date, default=None)
