"""Card, access settings, visit, day pass, ban and denied scan models (section 36.1)."""

from __future__ import annotations

import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from lms.core.db import Base
from lms.core.money import MoneyType
from lms.core.timeutil import TZDateTime

DEFAULT_DAY_PASS_PRICE = Decimal("5.00")


class Card(Base):
    __tablename__ = "cards"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(sa.ForeignKey("members.id"), index=True)
    status: Mapped[str] = mapped_column(sa.String(10), default="active", index=True)
    issued_on: Mapped[datetime.date] = mapped_column(sa.Date)
    expires_on: Mapped[datetime.date] = mapped_column(sa.Date)
    replaces_id: Mapped[int | None] = mapped_column(default=None)
    fee_id: Mapped[int | None] = mapped_column(default=None)
    ended_on: Mapped[datetime.date | None] = mapped_column(sa.Date, default=None)

    @property
    def card_no(self) -> str:
        """``"LC"`` followed by the id padded to 8 digits, so numbers are given in order."""
        return f"LC{self.id:08d}"


class AccessSettings(Base):
    __tablename__ = "access_settings"

    branch_id: Mapped[int] = mapped_column(sa.ForeignKey("branches.id"), primary_key=True)
    capacity: Mapped[int | None] = mapped_column(default=None)
    guest_entry: Mapped[bool] = mapped_column(default=True)
    day_passes: Mapped[bool] = mapped_column(default=True)
    day_pass_price: Mapped[Decimal] = mapped_column(MoneyType, default=DEFAULT_DAY_PASS_PRICE)


class DayPass(Base):
    __tablename__ = "day_passes"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(sa.String(40), unique=True)
    branch_id: Mapped[int] = mapped_column(sa.ForeignKey("branches.id"), index=True)
    visitor_name: Mapped[str] = mapped_column(sa.String(200))
    valid_on: Mapped[datetime.date] = mapped_column(sa.Date, index=True)
    price: Mapped[Decimal] = mapped_column(MoneyType)
    status: Mapped[str] = mapped_column(sa.String(10), default="unused", index=True)
    sold_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    sold_by: Mapped[int] = mapped_column(sa.ForeignKey("users.id"))


class Visit(Base):
    __tablename__ = "visits"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(sa.ForeignKey("branches.id"), index=True)
    member_id: Mapped[int | None] = mapped_column(sa.ForeignKey("members.id"), index=True, default=None)
    day_pass_id: Mapped[int | None] = mapped_column(sa.ForeignKey("day_passes.id"), index=True, default=None)
    card_id: Mapped[int | None] = mapped_column(sa.ForeignKey("cards.id"), default=None)
    entered_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    left_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, index=True, default=None)
    closed_by: Mapped[str | None] = mapped_column(sa.String(10), default=None)

    @property
    def minutes(self) -> int | None:
        if self.left_at is None:
            return None
        return int((self.left_at - self.entered_at).total_seconds() // 60)


class AccessBan(Base):
    __tablename__ = "access_bans"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(sa.ForeignKey("members.id"), index=True)
    reason: Mapped[str] = mapped_column(sa.String(200))
    starts_on: Mapped[datetime.date] = mapped_column(sa.Date)
    ends_on: Mapped[datetime.date] = mapped_column(sa.Date)
    lifted_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    created_by: Mapped[int] = mapped_column(sa.ForeignKey("users.id"))

    def in_force_on(self, day: datetime.date) -> bool:
        return self.lifted_at is None and self.starts_on <= day <= self.ends_on


class AccessAlert(Base):
    """A scan with a lost card (LIB-ACC-21)."""

    __tablename__ = "access_alerts"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(sa.ForeignKey("cards.id"))
    branch_id: Mapped[int] = mapped_column(sa.ForeignKey("branches.id"))
    at: Mapped[datetime.datetime] = mapped_column(TZDateTime, index=True)


class DeniedScan(Base):
    """A refused entry scan with its error code (LIB-ACC-45)."""

    __tablename__ = "access_denied_scans"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(sa.ForeignKey("branches.id"), index=True)
    code: Mapped[str] = mapped_column(sa.String(40))
    card_id: Mapped[int | None] = mapped_column(default=None)
    day_pass_id: Mapped[int | None] = mapped_column(default=None)
    at: Mapped[datetime.datetime] = mapped_column(TZDateTime, index=True)
