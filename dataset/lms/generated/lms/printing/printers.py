"""Printers: create, change, refill (LIB-PRT-01 to LIB-PRT-06, LIB-PRT-33)."""

from __future__ import annotations

import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import changes, record
from lms.auth.models import User
from lms.branches.service import require_active_branch
from lms.core.errors import Conflict
from lms.core.lookup import get_or_404
from lms.notifications.service import notify_printing
from lms.printing.models import Printer, PrintJob
from lms.printing.rules import LOW_PAPER, MAX_PAPER
from lms.printing.usage import cancel_job


def get_printer_or_404(db: Session, printer_id: int) -> Printer:
    return get_or_404(db, Printer, printer_id, label="Printer", resource="printer")


def printer_list_stmt(
    *, branch_id: int | None, status: str | None, color: bool | None, low_paper: bool | None
) -> sa.Select[tuple[Printer]]:
    """LIB-PRT-02, LIB-PRT-33: ordered by ``code``."""
    stmt = sa.select(Printer).order_by(Printer.code, Printer.id)
    if branch_id is not None:
        stmt = stmt.where(Printer.branch_id == branch_id)
    if status is not None:
        stmt = stmt.where(Printer.status == status)
    if color is not None:
        stmt = stmt.where(Printer.color == color)
    if low_paper is not None:
        stmt = stmt.where(Printer.paper_left < LOW_PAPER if low_paper else Printer.paper_left >= LOW_PAPER)
    return stmt


def create_printer(
    db: Session, now: datetime.datetime, actor: User, *, branch_id: int, code: str, name: str, color: bool, duplex: bool
) -> Printer:
    """LIB-PRT-01."""
    require_active_branch(db, "branch_id", branch_id)
    if db.scalar(sa.select(Printer.id).where(Printer.code == code)) is not None:
        raise Conflict("A printer with this code already exists", details={"field": "code"})
    printer = Printer(
        branch_id=branch_id, code=code, name=name, color=color, duplex=duplex, paper_left=0, status="active"
    )
    db.add(printer)
    db.flush()
    record(
        db,
        at=now,
        event="printer_created",
        actor_user_id=actor.id,
        entity_type="printer",
        entity_id=printer.id,
        details={"branch_id": branch_id, "code": code, "name": name, "color": color, "duplex": duplex},
    )
    return printer


def _snapshot(printer: Printer) -> dict[str, Any]:
    return {"name": printer.name, "color": printer.color, "duplex": printer.duplex, "status": printer.status}


def _cancel_reason(printer: Printer, job: PrintJob) -> str | None:
    if printer.status != "active":
        return f"printer {printer.code} is {printer.status.replace('_', ' ')}"
    if job.color and not printer.color:
        return f"printer {printer.code} cannot print in color"
    if job.duplex and not printer.duplex:
        return f"printer {printer.code} cannot print on both sides"
    return None


def update_printer(db: Session, now: datetime.datetime, actor: User, printer: Printer, fields: dict[str, Any]) -> Printer:
    """LIB-PRT-03, LIB-PRT-04."""
    if printer.status == "retired" and fields:
        raise Conflict("The printer is retired", code="PRINTER_RETIRED")
    old = _snapshot(printer)
    for name, value in fields.items():
        setattr(printer, name, value)
    diff = changes(old, _snapshot(printer))
    if diff:
        record(
            db,
            at=now,
            event="printer_changed",
            actor_user_id=actor.id,
            entity_type="printer",
            entity_id=printer.id,
            details=diff,
        )
    queued = db.scalars(
        sa.select(PrintJob).where(PrintJob.printer_id == printer.id, PrintJob.status == "queued").order_by(PrintJob.id)
    )
    for job in list(queued):
        reason = _cancel_reason(printer, job)
        if reason is None:
            continue
        cancel_job(db, now, actor.id, job, reason)
        notify_printing(
            db,
            now,
            job.member_id,
            "print_job_cancelled",
            f'Your print job "{job.title}" was cancelled: {reason}.',
            print_job_id=job.id,
        )
    return printer


def refill(db: Session, now: datetime.datetime, actor: User, printer: Printer, sheets: int) -> Printer:
    """LIB-PRT-05."""
    if printer.status == "retired":
        raise Conflict("The printer is retired", code="PRINTER_RETIRED")
    if printer.paper_left + sheets > MAX_PAPER:
        raise Conflict(
            "The printer cannot hold that much paper",
            code="PAPER_CAPACITY_EXCEEDED",
            details={"paper_left": printer.paper_left},
        )
    printer.paper_left += sheets
    record(
        db,
        at=now,
        event="printer_refilled",
        actor_user_id=actor.id,
        entity_type="printer",
        entity_id=printer.id,
        details={"sheets": sheets, "paper_left": printer.paper_left},
    )
    return printer
