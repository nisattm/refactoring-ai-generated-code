"""Programs: create, change, publish, cancel, copy, featured books and reading (sections 34.3 and 34.4)."""

from __future__ import annotations

import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import changes, record
from lms.auth.models import User
from lms.branches.models import Branch
from lms.catalog.models import Book
from lms.core.errors import Conflict, NotFound, ValidationFailed
from lms.core.money import format_amount
from lms.core.text import normalize
from lms.notifications.service import notify_program
from lms.programs.models import Participation, Program, ProgramBook
from lms.programs.rules import MAX_DAYS, MIN_DAYS
from lms.programs.schemas import ProgramOut, program_out

PUBLISHED_FIELDS = ("description", "ends_on", "max_participants")


def get_program_or_404(db: Session, program_id: int) -> Program:
    program = db.get(Program, program_id)
    if program is None:
        raise NotFound(f"Program {program_id} does not exist", details={"resource": "program", "id": program_id})
    return program


def _status_error(program: Program) -> Conflict:
    return Conflict(
        "The program status does not allow this", code="INVALID_PROGRAM_STATUS", details={"status": program.status}
    )


# --- figures ------------------------------------------------------------------------------------


def counts(db: Session, program_id: int) -> tuple[int, int]:
    """``(participants, completed)``: ``active`` and ``completed`` participations, and the completed ones."""
    rows = db.execute(
        sa.select(Participation.status, sa.func.count())
        .where(Participation.program_id == program_id, Participation.status.in_(("active", "completed")))
        .group_by(Participation.status)
    ).all()
    by_status = {status: n for status, n in rows}
    completed = by_status.get("completed", 0)
    return by_status.get("active", 0) + completed, completed


def to_out(db: Session, program: Program) -> ProgramOut:
    participants, completed = counts(db, program.id)
    return program_out(program, participants=participants, completed=completed)


# --- validation ---------------------------------------------------------------------------------


def check_span(starts_on: datetime.date, ends_on: datetime.date) -> None:
    """34.1: ``ends_on`` − ``starts_on`` is 13 to 120 days."""
    days = (ends_on - starts_on).days
    if not MIN_DAYS <= days <= MAX_DAYS:
        raise ValidationFailed.single("ends_on", "ends_on must be 13 to 120 days after starts_on")


def check_branch(db: Session, branch_id: int | None) -> Branch | None:
    """LIB-RDP-01: an unknown branch is ``422``, an inactive one ``409 BRANCH_INACTIVE``."""
    if branch_id is None:
        return None
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise ValidationFailed.single("branch_id", f"branch {branch_id} does not exist")
    if not branch.is_active:
        raise Conflict(
            f"Branch {branch.code} is inactive", code="BRANCH_INACTIVE", details={"field": "branch_id", "id": branch_id}
        )
    return branch


def check_name_free(db: Session, name: str, *, except_id: int | None = None) -> None:
    stmt = sa.select(Program.id).where(Program.name_key == normalize(name), Program.status != "cancelled")
    if except_id is not None:
        stmt = stmt.where(Program.id != except_id)
    if db.scalar(stmt.limit(1)) is not None:
        raise Conflict("A program with this name exists", code="CONFLICT", details={"field": "name"})


# --- create and change --------------------------------------------------------------------------


def _created(db: Session, now: datetime.datetime, actor: User, program: Program, **extra: Any) -> None:
    record(
        db,
        at=now,
        event="program_created",
        actor_user_id=actor.id,
        entity_type="program",
        entity_id=program.id,
        details={
            "name": program.name,
            "branch_id": program.branch_id,
            "starts_on": program.starts_on.isoformat(),
            "ends_on": program.ends_on.isoformat(),
            "goal_books": program.goal_books,
            **extra,
        },
    )


def create_program(db: Session, now: datetime.datetime, actor: User, data: dict[str, Any]) -> Program:
    """LIB-RDP-01."""
    check_span(data["starts_on"], data["ends_on"])
    check_branch(db, data["branch_id"])
    check_name_free(db, data["name"])
    program = Program(**data, name_key=normalize(data["name"]), status="draft", created_at=now)
    db.add(program)
    db.flush()
    _created(db, now, actor, program)
    return program


def update_program(
    db: Session, now: datetime.datetime, actor: User, program: Program, fields: dict[str, Any]
) -> Program:
    """LIB-RDP-02."""
    if program.status in ("closed", "cancelled"):
        raise _status_error(program)
    today = now.date()
    if program.status == "published":
        locked = [name for name in fields if name not in PUBLISHED_FIELDS]
        if locked:
            raise Conflict(
                "Only description, ends_on and max_participants can change on a published program",
                code="PROGRAM_PUBLISHED",
                details={"fields": locked},
            )
        ends_on = fields.get("ends_on")
        if ends_on is not None and (ends_on < today or ends_on < program.ends_on):
            raise ValidationFailed.single("ends_on", "ends_on must not be earlier than today or the current ends_on")
        limit = fields.get("max_participants")
        if limit is not None:
            participants, _ = counts(db, program.id)
            if limit < participants:
                raise Conflict(
                    "max_participants is below the number of participants",
                    code="PARTICIPANTS_ABOVE_LIMIT",
                    details={"participants": participants},
                )
    check_span(fields.get("starts_on", program.starts_on), fields.get("ends_on", program.ends_on))
    if "branch_id" in fields and fields["branch_id"] != program.branch_id:
        check_branch(db, fields["branch_id"])
    if "name" in fields:
        check_name_free(db, fields["name"], except_id=program.id)

    old = {name: getattr(program, name) for name in fields}
    diff = changes(old, fields)
    for name, value in fields.items():
        setattr(program, name, value)
    if "name" in fields:
        program.name_key = normalize(fields["name"])
    if diff:
        record(
            db,
            at=now,
            event="program_updated",
            actor_user_id=actor.id,
            entity_type="program",
            entity_id=program.id,
            details={name: _jsonable(change) for name, change in diff.items()},
        )
    return program


def _jsonable(change: dict[str, Any]) -> dict[str, Any]:
    def convert(value: Any) -> Any:
        if isinstance(value, datetime.date):
            return value.isoformat()
        if hasattr(value, "quantize"):
            return format_amount(value)
        return value

    return {"old": convert(change["old"]), "new": convert(change["new"])}


# --- publish and cancel -------------------------------------------------------------------------


def publish(db: Session, now: datetime.datetime, actor: User, program: Program) -> Program:
    """LIB-RDP-03."""
    if program.status != "draft":
        raise _status_error(program)
    if program.ends_on < now.date():
        raise Conflict("The program has already ended", code="PROGRAM_ENDED", details={"ends_on": program.ends_on.isoformat()})
    program.status = "published"
    program.published_at = now
    record(
        db,
        at=now,
        event="program_published",
        actor_user_id=actor.id,
        entity_type="program",
        entity_id=program.id,
        details={"starts_on": program.starts_on.isoformat(), "ends_on": program.ends_on.isoformat()},
    )
    return program


def cancel(db: Session, now: datetime.datetime, actor: User, program: Program) -> Program:
    """LIB-RDP-04."""
    if program.status not in ("draft", "published"):
        raise _status_error(program)
    program.status = "cancelled"
    active = db.scalars(
        sa.select(Participation)
        .where(Participation.program_id == program.id, Participation.status == "active")
        .order_by(Participation.id)
    ).all()
    for participation in active:
        participation.status = "left"
        participation.left_at = now
        participation.leave_reason = "program_cancelled"
        notify_program(
            db,
            now,
            participation.member_id,
            "program_cancelled",
            f'The reading program "{program.name}" was cancelled.',
            program_id=program.id,
        )
    record(
        db,
        at=now,
        event="program_cancelled",
        actor_user_id=actor.id,
        entity_type="program",
        entity_id=program.id,
        details={"participants_left": len(active)},
    )
    return program


# --- featured books -----------------------------------------------------------------------------


def featured_books(db: Session, program_id: int) -> list[tuple[int, str]]:
    """LIB-RDP-08: ``(book_id, title)`` ordered by ``title``, then ``id``."""
    rows = db.execute(
        sa.select(Book.id, Book.title)
        .join(ProgramBook, ProgramBook.book_id == Book.id)
        .where(ProgramBook.program_id == program_id)
    ).all()
    return sorted(((book_id, title) for book_id, title in rows), key=lambda row: (normalize(row[1]), row[0]))


def set_books(
    db: Session, now: datetime.datetime, actor: User, program: Program, book_ids: list[int]
) -> list[tuple[int, str]]:
    """LIB-RDP-08."""
    problems = []
    if len(set(book_ids)) != len(book_ids):
        problems.append({"field": "book_ids", "problem": "book_ids must be distinct"})
    known = set(db.scalars(sa.select(Book.id).where(Book.id.in_(book_ids)))) if book_ids else set()
    for index, book_id in enumerate(book_ids):
        if book_id not in known:
            problems.append({"field": f"book_ids.{index}", "problem": f"book {book_id} does not exist"})
    if problems:
        raise ValidationFailed(problems)
    if program.status not in ("draft", "published"):
        raise _status_error(program)
    db.execute(sa.delete(ProgramBook).where(ProgramBook.program_id == program.id))
    for book_id in book_ids:
        db.add(ProgramBook(program_id=program.id, book_id=book_id))
    db.flush()
    record(
        db,
        at=now,
        event="program_books_set",
        actor_user_id=actor.id,
        entity_type="program",
        entity_id=program.id,
        details={"book_ids": sorted(book_ids)},
    )
    return featured_books(db, program.id)


# --- copy ---------------------------------------------------------------------------------------


def _copy_name(db: Session, name: str) -> str:
    candidate = f"{name} (copy)"
    n = 1
    while db.scalar(
        sa.select(Program.id).where(Program.name_key == normalize(candidate), Program.status != "cancelled").limit(1)
    ):
        n += 1
        candidate = f"{name} (copy {n})"
    return candidate


def copy_program(
    db: Session, now: datetime.datetime, actor: User, source: Program, starts_on: datetime.date
) -> Program:
    """LIB-RDP-09."""
    name = _copy_name(db, source.name)
    program = Program(
        name=name,
        name_key=normalize(name),
        description=source.description,
        branch_id=source.branch_id,
        audience=source.audience,
        starts_on=starts_on,
        ends_on=starts_on + (source.ends_on - source.starts_on),
        goal_books=source.goal_books,
        max_participants=source.max_participants,
        reward_waiver=source.reward_waiver,
        status="draft",
        created_at=now,
    )
    db.add(program)
    db.flush()
    for book_id in db.scalars(select_books(source.id)):
        db.add(ProgramBook(program_id=program.id, book_id=book_id))
    db.flush()
    _created(db, now, actor, program, copied_from=source.id)
    return program


def select_books(program_id: int) -> sa.Select[tuple[int]]:
    return sa.select(ProgramBook.book_id).where(ProgramBook.program_id == program_id).order_by(ProgramBook.book_id)


# --- reading ------------------------------------------------------------------------------------


def list_stmt(
    *, status: str | None, branch_id: int | None, running: bool | None, today: datetime.date, member_view: bool
) -> sa.Select[tuple[Program]]:
    """LIB-RDP-07."""
    stmt = sa.select(Program).order_by(Program.starts_on, Program.id)
    if member_view:
        stmt = stmt.where(Program.status.in_(("published", "closed")))
    if status is not None:
        stmt = stmt.where(Program.status == status)
    if branch_id is not None:
        stmt = stmt.where(Program.branch_id == branch_id)
    if running is not None:
        is_running = sa.and_(Program.status == "published", Program.starts_on <= today, Program.ends_on >= today)
        stmt = stmt.where(is_running if running else sa.not_(is_running))
    return stmt
