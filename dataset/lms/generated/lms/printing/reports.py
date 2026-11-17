"""Printing report (LIB-PRT-44, LIB-PRT-45)."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.branches.models import Branch
from lms.core.money import ZERO, format_amount
from lms.fines.models import Fee
from lms.members.models import Member
from lms.printing import quota
from lms.printing.models import Printer, PrintJob, PrintPack
from lms.printing.schemas import PrintingReportOut


def printing_report(
    db: Session, first: datetime.date, last: datetime.date, branch_id: int | None
) -> list[PrintingReportOut]:
    """One row per branch with printers, ordered by branch ``code``."""
    start = quota.day_bounds(first)[0]
    end = quota.day_bounds(last)[1]
    branch_stmt = (
        sa.select(Branch).where(Branch.id.in_(sa.select(Printer.branch_id))).order_by(Branch.code, Branch.id)
    )
    if branch_id is not None:
        branch_stmt = branch_stmt.where(Branch.id == branch_id)
    rows: list[PrintingReportOut] = []
    for branch in db.scalars(branch_stmt):
        jobs = list(
            db.scalars(
                sa.select(PrintJob)
                .join(Printer, Printer.id == PrintJob.printer_id)
                .where(
                    Printer.branch_id == branch.id,
                    PrintJob.status.in_(("printed", "failed")),
                    PrintJob.released_at >= start,
                    PrintJob.released_at < end,
                )
            )
        )
        revenue = ZERO
        pending = ZERO
        for job in jobs:
            fee = db.get(Fee, job.fee_id) if job.fee_id is not None else None
            if fee is None:
                continue
            if fee.status != "waived":
                revenue += fee.amount
            if job.status == "failed":
                pending += fee.paid_amount
        packs = db.scalar(
            sa.select(sa.func.count())
            .select_from(PrintPack)
            .join(Member, Member.id == PrintPack.member_id)
            .where(Member.home_branch_id == branch.id, PrintPack.bought_on >= first, PrintPack.bought_on <= last)
        )
        rows.append(
            PrintingReportOut(
                branch_id=branch.id,
                jobs_printed=len(jobs),
                pages=sum(j.pages * j.copies for j in jobs),
                color_pages=sum(j.pages * j.copies for j in jobs if j.color),
                sheets=sum(j.sheets for j in jobs),
                free_pages=sum(j.free_pages for j in jobs),
                pack_pages=sum(j.pack_pages for j in jobs),
                charged_pages=sum(j.charged_pages for j in jobs),
                revenue=format_amount(revenue),
                packs_sold=packs or 0,
                jobs_failed=sum(1 for j in jobs if j.status == "failed"),
                refunds_pending=format_amount(pending),
            )
        )
    return rows
