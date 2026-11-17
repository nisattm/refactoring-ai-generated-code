"""Printer, print job and page pack models (section 37.1)."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from lms.core.db import Base
from lms.core.timeutil import TZDateTime
from lms.printing.rules import LOW_PAPER


class Printer(Base):
    __tablename__ = "printers"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(sa.ForeignKey("branches.id"), index=True)
    code: Mapped[str] = mapped_column(sa.String(10), unique=True)
    name: Mapped[str] = mapped_column(sa.String(200))
    color: Mapped[bool] = mapped_column(default=False)
    duplex: Mapped[bool] = mapped_column(default=False)
    paper_left: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(sa.String(20), default="active", index=True)

    @property
    def low_paper(self) -> bool:
        return self.paper_left < LOW_PAPER


class PrintJob(Base):
    __tablename__ = "print_jobs"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(sa.ForeignKey("members.id"), index=True)
    printer_id: Mapped[int] = mapped_column(sa.ForeignKey("printers.id"), index=True)
    title: Mapped[str] = mapped_column(sa.String(100))
    pages: Mapped[int]
    copies: Mapped[int] = mapped_column(default=1)
    color: Mapped[bool] = mapped_column(default=False)
    duplex: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(sa.String(10), default="queued", index=True)
    submitted_at: Mapped[datetime.datetime] = mapped_column(TZDateTime, index=True)
    released_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, index=True, default=None)
    sheets: Mapped[int]
    free_pages: Mapped[int] = mapped_column(default=0)
    pack_pages: Mapped[int] = mapped_column(default=0)
    charged_pages: Mapped[int] = mapped_column(default=0)
    fee_id: Mapped[int | None] = mapped_column(default=None)
    failed_reason: Mapped[str | None] = mapped_column(sa.String(200), default=None)

    @property
    def printed_pages(self) -> int:
        return self.pages * self.copies


class PrintPack(Base):
    __tablename__ = "print_packs"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(sa.ForeignKey("members.id"), index=True)
    pages: Mapped[int] = mapped_column(default=50)
    pages_left: Mapped[int] = mapped_column(default=50)
    bought_on: Mapped[datetime.date] = mapped_column(sa.Date)
    fee_id: Mapped[int | None] = mapped_column(default=None)


class PrintJobPackUse(Base):
    """The pages a released job took from a pack, so that a failed print can return them (LIB-PRT-24)."""

    __tablename__ = "print_job_pack_uses"

    job_id: Mapped[int] = mapped_column(sa.ForeignKey("print_jobs.id"), primary_key=True)
    pack_id: Mapped[int] = mapped_column(sa.ForeignKey("print_packs.id"), primary_key=True)
    pages: Mapped[int]


