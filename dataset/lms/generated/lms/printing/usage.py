"""Hooks and figures of module 29 used by other modules (members, branches).

Imports only models, schemas, quota and the audit log, so that the other modules can use it without import
cycles."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.members.models import Member
from lms.printing import quota
from lms.printing.models import Printer, PrintJob
from lms.printing.schemas import PrintingSummaryOut


def current_free_pages_left(db: Session, now: datetime.datetime, member: Member) -> int:
    """LIB-PRT-47: free pages left in the current month."""
    return quota.free_pages_left(db, member.id, member.membership_type, now.date().replace(day=1))


def member_summary(db: Session, now: datetime.datetime, member: Member) -> PrintingSummaryOut:
    """LIB-PRT-36."""
    return PrintingSummaryOut(
        free_pages_left=current_free_pages_left(db, now, member),
        pack_pages_left=quota.pack_pages_left(db, member.id),
        queued_jobs=quota.queued_count(db, member.id),
    )


def cancel_job(db: Session, now: datetime.datetime, actor_id: int | None, job: PrintJob, reason: str | None) -> None:
    """Set a ``queued`` job to ``cancelled`` and record ``print_job_cancelled`` (LIB-PRT-04, LIB-PRT-12, LIB-PRT-35)."""
    job.status = "cancelled"
    details = {"member_id": job.member_id, "printer_id": job.printer_id, "title": job.title}
    if reason is not None:
        details["reason"] = reason
    record(
        db,
        at=now,
        event="print_job_cancelled",
        actor_user_id=actor_id,
        entity_type="print_job",
        entity_id=job.id,
        details=details,
    )


def on_member_deactivated(db: Session, now: datetime.datetime, actor_id: int, member_id: int) -> None:
    """LIB-PRT-35: the queued jobs of the member are cancelled, without a notification; packs keep their pages."""
    stmt = sa.select(PrintJob).where(PrintJob.member_id == member_id, PrintJob.status == "queued").order_by(PrintJob.id)
    for job in list(db.scalars(stmt)):
        cancel_job(db, now, actor_id, job, "member_deactivated")
    db.flush()


def branch_has_printers(db: Session, branch_id: int) -> bool:
    """LIB-PRT-37: the branch has a printer that is not ``retired``."""
    stmt = sa.select(Printer.id).where(Printer.branch_id == branch_id, Printer.status != "retired").limit(1)
    return db.scalar(stmt) is not None
