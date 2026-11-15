"""Hooks and figures of module 26 used by other modules (members, branches) and the programs report.

Imports only models, schemas and the audit log, so that the other modules can use it without import cycles."""

from __future__ import annotations

import datetime
from decimal import ROUND_HALF_UP, Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.catalog.models import Book
from lms.core.clock import LOCAL_TZ
from lms.core.money import ZERO, format_amount
from lms.programs.models import BOOK_SOURCES, Entry, Participation, Program
from lms.programs.schemas import ProgramReportOut, ProgramSummaryOut, TopBookOut

TOP_BOOKS = 3


def branch_has_open_programs(db: Session, branch_id: int) -> bool:
    """LIB-RDP-40."""
    stmt = sa.select(Program.id).where(Program.branch_id == branch_id, Program.status.in_(("draft", "published")))
    return db.scalar(stmt.limit(1)) is not None


def on_member_deactivated(db: Session, now: datetime.datetime, actor_user_id: int | None, member_id: int) -> None:
    """LIB-RDP-38: the ``active`` participations become ``left``. Nobody is notified (LIB-RDP-42)."""
    active = db.scalars(
        sa.select(Participation)
        .where(Participation.member_id == member_id, Participation.status == "active")
        .order_by(Participation.id)
    ).all()
    for participation in active:
        participation.status = "left"
        participation.left_at = now
        participation.leave_reason = "member_deactivated"
        record(
            db,
            at=now,
            event="program_left",
            actor_user_id=actor_user_id,
            entity_type="program_participation",
            entity_id=participation.id,
            details={
                "program_id": participation.program_id,
                "member_id": member_id,
                "leave_reason": "member_deactivated",
            },
        )
    db.flush()


def member_summary(db: Session, now: datetime.datetime, member_id: int) -> ProgramSummaryOut:
    """LIB-RDP-39."""
    start = datetime.datetime(now.year, 1, 1, tzinfo=LOCAL_TZ)
    end = datetime.datetime(now.year + 1, 1, 1, tzinfo=LOCAL_TZ)
    active = db.scalar(
        sa.select(sa.func.count())
        .select_from(Participation)
        .where(Participation.member_id == member_id, Participation.status == "active")
    )
    completed = db.scalar(
        sa.select(sa.func.count())
        .select_from(Participation)
        .where(
            Participation.member_id == member_id,
            Participation.completed_at >= start,
            Participation.completed_at < end,
        )
    )
    points = db.scalar(
        sa.select(sa.func.coalesce(sa.func.sum(Entry.points), 0))
        .join(Participation, Participation.id == Entry.participation_id)
        .where(
            Participation.member_id == member_id,
            Entry.on >= datetime.date(now.year, 1, 1),
            Entry.on <= datetime.date(now.year, 12, 31),
        )
    )
    return ProgramSummaryOut(active=active or 0, completed_this_year=completed or 0, points_this_year=int(points or 0))


# --- programs report (LIB-RDP-44) ---------------------------------------------------------------


def report_stmt(first: datetime.date, last: datetime.date) -> sa.Select[tuple[Program]]:
    return (
        sa.select(Program)
        .where(Program.status.in_(("published", "closed")), Program.starts_on <= last, Program.ends_on >= first)
        .order_by(Program.starts_on, Program.id)
    )


def report_out(db: Session, program: Program) -> ProgramReportOut:
    participations = db.scalars(sa.select(Participation).where(Participation.program_id == program.id)).all()
    counted = [p for p in participations if p.status in ("active", "completed")]
    completed = sum(1 for p in counted if p.status == "completed")
    rate = "0.0"
    if counted:
        rate = format((Decimal(completed) * 100 / Decimal(len(counted))).quantize(Decimal("0.1"), ROUND_HALF_UP), "f")
    per_book = db.execute(
        sa.select(Entry.book_id, sa.func.count())
        .join(Participation, Participation.id == Entry.participation_id)
        .where(Participation.program_id == program.id, Entry.source.in_(BOOK_SOURCES), Entry.book_id.is_not(None))
        .group_by(Entry.book_id)
    ).all()
    top = sorted(per_book, key=lambda row: (-row[1], row[0]))[:TOP_BOOKS]
    titles = {book_id: title for book_id, title in db.execute(sa.select(Book.id, Book.title).where(Book.id.in_([b for b, _ in top]))).all()} if top else {}
    waived = sum((p.reward_waived for p in participations), ZERO)
    return ProgramReportOut(
        program_id=program.id,
        name=program.name,
        status=program.status,
        participants=len(counted),
        completed=completed,
        completion_rate=rate,
        books_counted=sum(count for _, count in per_book),
        points=sum(p.points for p in participations),
        rewards_waived=format_amount(waived),
        top_books=[TopBookOut(book_id=b, title=titles.get(b, ""), count=count) for b, count in top],
    )
