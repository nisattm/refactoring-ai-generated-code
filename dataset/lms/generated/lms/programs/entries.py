"""Entries, completion and rewards (sections 34.6 and 34.7)."""

from __future__ import annotations

import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.catalog.models import Book, Copy
from lms.core.db import get_or_404
from lms.core.errors import Conflict
from lms.core.money import ZERO, format_amount
from lms.fines import service as fines
from lms.fines.models import Fee
from lms.loans.models import Loan
from lms.notifications.service import notify_program
from lms.programs import ranking
from lms.programs.models import (
    BOOK_SOURCES,
    LEVELS,
    Entry,
    Participation,
    Program,
    ProgramBook,
)
from lms.programs.rules import (
    BONUS_WEEKS,
    MANUAL_ENTRY_LIMIT,
    POINTS_EVENT,
    POINTS_FEATURED,
    POINTS_LATE,
    POINTS_MANUAL,
    POINTS_ON_TIME,
    POINTS_WEEKLY_BONUS,
    REWARD_REASON,
)


def get_participation_or_404(db: Session, participation_id: int) -> Participation:
    return get_or_404(db, Participation, participation_id, "Participation", "participation")


def get_entry_or_404(db: Session, entry_id: int) -> Entry:
    return get_or_404(db, Entry, entry_id, "Entry", "program_entry")


def _week_start(day: datetime.date) -> datetime.date:
    return day - datetime.timedelta(days=day.weekday())


def recompute(db: Session, participation: Participation, program: Program) -> None:
    """LIB-RDP-29: ``points``, ``books`` and ``level`` from the entries; a completed participation stays at
    ``bronze`` or above."""
    db.flush()
    entries = list(db.scalars(sa.select(Entry).where(Entry.participation_id == participation.id)))
    participation.points = sum(e.points for e in entries)
    participation.books = len({e.book_id for e in entries if e.source in BOOK_SOURCES and e.book_id is not None})
    level = ranking.level_for(participation.books, program.goal_books)
    if participation.completed_at is not None and level == "none":
        level = "bronze"
    participation.level = level


def _featured(db: Session, program_id: int, book_id: int) -> bool:
    stmt = sa.select(ProgramBook.id).where(ProgramBook.program_id == program_id, ProgramBook.book_id == book_id)
    return db.scalar(stmt.limit(1)) is not None


def _has_book(db: Session, participation_id: int, book_id: int) -> bool:
    stmt = sa.select(Entry.id).where(
        Entry.participation_id == participation_id, Entry.source.in_(BOOK_SOURCES), Entry.book_id == book_id
    )
    return db.scalar(stmt.limit(1)) is not None


def _add_weekly_bonus(db: Session, now: datetime.datetime, participation: Participation, on: datetime.date) -> None:
    """LIB-RDP-24: once, when book entries lie in 3 different calendar weeks."""
    db.flush()
    entries = list(db.scalars(sa.select(Entry).where(Entry.participation_id == participation.id)))
    if any(e.source == "bonus" for e in entries):
        return
    weeks = {_week_start(e.on) for e in entries if e.source in BOOK_SOURCES}
    if len(weeks) >= BONUS_WEEKS:
        db.add(
            Entry(
                participation_id=participation.id,
                source="bonus",
                points=POINTS_WEEKLY_BONUS,
                on=on,
                note="",
                created_at=now,
            )
        )


def _reward(db: Session, now: datetime.datetime, actor: User, participation: Participation, program: Program) -> Decimal:
    """LIB-RDP-32: waive open, unpaid late fees in order while they fit into the rest of ``reward_waiver``."""
    left = program.reward_waiver
    waived = ZERO
    stmt = (
        sa.select(Fee)
        .where(Fee.member_id == participation.member_id, Fee.kind == "late_fee", Fee.status == "open")
        .order_by(Fee.created_on, Fee.id)
    )
    for fee in list(db.scalars(stmt)):
        if fee.paid_amount > ZERO or fee.amount > left:
            continue
        fines.waive_fee(db, now, actor, fee, REWARD_REASON)
        left -= fee.amount
        waived += fee.amount
    return waived


def _complete(db: Session, now: datetime.datetime, actor: User, participation: Participation, program: Program) -> None:
    """LIB-RDP-28."""
    last = db.scalar(
        sa.select(sa.func.max(Participation.completion_no)).where(Participation.program_id == program.id)
    )
    participation.status = "completed"
    participation.completed_at = now
    participation.completion_no = (last or 0) + 1
    participation.reward_waived = _reward(db, now, actor, participation, program)
    recompute(db, participation, program)
    participation.top_level = participation.level
    record(
        db,
        at=now,
        event="program_completed",
        actor_user_id=actor.id,
        entity_type="program_participation",
        entity_id=participation.id,
        details={
            "program_id": program.id,
            "member_id": participation.member_id,
            "level": participation.level,
            "reward_waived": format_amount(participation.reward_waived),
        },
    )
    notify_program(
        db,
        now,
        participation.member_id,
        "program_completed",
        f'You completed the reading program "{program.name}" with {participation.books} books.',
        program_id=program.id,
    )


def settle(db: Session, now: datetime.datetime, actor: User, participation: Participation, program: Program) -> None:
    """Recompute the totals, then check completion (LIB-RDP-28) and higher levels (LIB-RDP-30)."""
    recompute(db, participation, program)
    if participation.completed_at is None:
        if participation.books >= program.goal_books:
            _complete(db, now, actor, participation, program)
        return
    old = ranking.level_index(participation.top_level)
    new = ranking.level_index(participation.level)
    for level in LEVELS[old + 1 : new + 1]:
        if level in ("silver", "gold"):
            notify_program(
                db,
                now,
                participation.member_id,
                "program_level_reached",
                f'You reached the {level} level in the reading program "{program.name}".',
                program_id=program.id,
            )
    if new > old:
        participation.top_level = participation.level


def add_entry(
    db: Session,
    now: datetime.datetime,
    actor: User,
    participation: Participation,
    program: Program,
    *,
    source: str,
    points: int,
    on: datetime.date,
    book_id: int | None = None,
    loan_id: int | None = None,
    event_id: int | None = None,
    note: str = "",
) -> Entry:
    """Create an entry with the featured bonus (LIB-RDP-23), then the weekly bonus (LIB-RDP-24), completion and
    levels."""
    if source in BOOK_SOURCES and book_id is not None and _featured(db, program.id, book_id):
        points += POINTS_FEATURED
    entry = Entry(
        participation_id=participation.id,
        source=source,
        book_id=book_id,
        loan_id=loan_id,
        event_id=event_id,
        points=points,
        on=on,
        note=note,
        created_at=now,
    )
    db.add(entry)
    if source in BOOK_SOURCES:
        _add_weekly_bonus(db, now, participation, on)
    settle(db, now, actor, participation, program)
    return entry


# --- automatic entries --------------------------------------------------------------------------


def _running_participations(db: Session, member_id: int, day: datetime.date) -> list[tuple[Participation, Program]]:
    stmt = (
        sa.select(Participation, Program)
        .join(Program, Program.id == Participation.program_id)
        .where(
            Participation.member_id == member_id,
            Participation.status.in_(("active", "completed")),
            Program.status == "published",
            Program.starts_on <= day,
            Program.ends_on >= day,
        )
        .order_by(Participation.id)
    )
    return [(p, program) for p, program in db.execute(stmt).all()]


def on_loan_returned(db: Session, now: datetime.datetime, actor: User, loan: Loan) -> None:
    """LIB-RDP-16 to LIB-RDP-18, LIB-RDP-41: called when a loan was returned (not when it was lost)."""
    day = now.date()
    book_id = db.scalar(sa.select(Copy.book_id).where(Copy.id == loan.copy_id))
    if book_id is None:
        return
    for participation, program in _running_participations(db, loan.member_id, day):
        if participation.joined_at > now:
            continue
        if program.branch_id is not None and program.branch_id != loan.branch_id:
            continue
        if _has_book(db, participation.id, book_id):
            continue
        late = loan.returned_on is not None and loan.returned_on > loan.due_date
        add_entry(
            db,
            now,
            actor,
            participation,
            program,
            source="loan",
            points=POINTS_LATE if late else POINTS_ON_TIME,
            on=day,
            book_id=book_id,
            loan_id=loan.id,
        )


def on_event_attended(
    db: Session, now: datetime.datetime, actor: User, member_id: int, event_id: int, branch_id: int
) -> None:
    """LIB-RDP-21."""
    day = now.date()
    for participation, program in _running_participations(db, member_id, day):
        if participation.joined_at > now:
            continue
        if program.branch_id is not None and program.branch_id != branch_id:
            continue
        exists = sa.select(Entry.id).where(Entry.participation_id == participation.id, Entry.event_id == event_id)
        if db.scalar(exists.limit(1)) is not None:
            continue
        add_entry(
            db, now, actor, participation, program, source="event", points=POINTS_EVENT, on=day, event_id=event_id
        )


# --- manual entries -----------------------------------------------------------------------------


def _not_active(participation: Participation) -> Conflict:
    return Conflict(
        "The participation is not active",
        code="PARTICIPATION_NOT_ACTIVE",
        details={"status": participation.status},
    )


def add_manual(
    db: Session,
    now: datetime.datetime,
    actor: User,
    participation: Participation,
    program: Program,
    book: Book,
    note: str,
) -> Entry:
    """LIB-RDP-19."""
    if participation.status == "left":
        raise _not_active(participation)
    today = now.date()
    if not program.is_running(today):
        raise Conflict("The program is not running", code="PROGRAM_NOT_RUNNING", details={"status": program.status})
    if _has_book(db, participation.id, book.id):
        raise Conflict("The book is already counted", code="BOOK_ALREADY_COUNTED", details={"book_id": book.id})
    manual = db.scalar(
        sa.select(sa.func.count())
        .select_from(Entry)
        .where(Entry.participation_id == participation.id, Entry.source == "manual")
    )
    if (manual or 0) >= MANUAL_ENTRY_LIMIT:
        raise Conflict(
            "The participation has too many manual entries",
            code="MANUAL_ENTRY_LIMIT",
            details={"limit": MANUAL_ENTRY_LIMIT},
        )
    entry = add_entry(
        db, now, actor, participation, program, source="manual", points=POINTS_MANUAL, on=today, book_id=book.id,
        note=note,
    )
    db.flush()
    record(
        db,
        at=now,
        event="program_entry_added",
        actor_user_id=actor.id,
        entity_type="program_entry",
        entity_id=entry.id,
        details={
            "program_id": program.id,
            "participation_id": participation.id,
            "member_id": participation.member_id,
            "book_id": book.id,
            "points": entry.points,
        },
    )
    return entry


def remove_manual(db: Session, now: datetime.datetime, actor: User, entry: Entry) -> None:
    """LIB-RDP-20, LIB-RDP-29."""
    participation = db.get(Participation, entry.participation_id)
    assert participation is not None
    program = db.get(Program, participation.program_id)
    assert program is not None
    if entry.source != "manual":
        raise Conflict("Only manual entries can be removed", code="ENTRY_NOT_MANUAL", details={"source": entry.source})
    if participation.status == "left":
        raise _not_active(participation)
    entry_id, points, book_id = entry.id, entry.points, entry.book_id
    db.delete(entry)
    recompute(db, participation, program)
    record(
        db,
        at=now,
        event="program_entry_removed",
        actor_user_id=actor.id,
        entity_type="program_entry",
        entity_id=entry_id,
        details={
            "program_id": program.id,
            "participation_id": participation.id,
            "member_id": participation.member_id,
            "book_id": book_id,
            "points": points,
        },
    )


# --- reading ------------------------------------------------------------------------------------


def entries_stmt(participation_id: int, source: str | None) -> sa.Select[tuple[Entry]]:
    """LIB-RDP-22."""
    stmt = (
        sa.select(Entry)
        .where(Entry.participation_id == participation_id)
        .order_by(Entry.created_at, Entry.id)
    )
    if source is not None:
        stmt = stmt.where(Entry.source == source)
    return stmt


def book_titles(db: Session, entries: list[Entry]) -> dict[int, str]:
    ids = {e.book_id for e in entries if e.book_id is not None}
    if not ids:
        return {}
    return {book_id: title for book_id, title in db.execute(sa.select(Book.id, Book.title).where(Book.id.in_(ids))).all()}
