"""Closing ended programs and ending reminders (LIB-RDP-05, LIB-RDP-35)."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.notifications.service import notify_program
from lms.programs.models import Participation, Program
from lms.programs.rules import REMINDER_DAYS
from lms.programs.schemas import ProcessOut


def _count(db: Session, program_id: int, status: str) -> int:
    return (
        db.scalar(
            sa.select(sa.func.count())
            .select_from(Participation)
            .where(Participation.program_id == program_id, Participation.status == status)
        )
        or 0
    )


def process(db: Session, now: datetime.datetime, actor: User) -> ProcessOut:
    today = now.date()
    ended = db.scalars(
        sa.select(Program).where(Program.status == "published", Program.ends_on < today).order_by(Program.id)
    ).all()
    completed = not_completed = 0
    for program in ended:
        program.status = "closed"
        program.closed_at = now
        completed += _count(db, program.id, "completed")
        not_completed += _count(db, program.id, "active")

    reminders = 0
    ending = db.scalars(
        sa.select(Program)
        .where(Program.status == "published", Program.ends_on == today + datetime.timedelta(days=REMINDER_DAYS))
        .order_by(Program.id)
    ).all()
    for program in ending:
        due = db.scalars(
            sa.select(Participation)
            .where(
                Participation.program_id == program.id,
                Participation.status == "active",
                Participation.reminded_at.is_(None),
            )
            .order_by(Participation.id)
        ).all()
        for participation in due:
            participation.reminded_at = now
            notify_program(
                db,
                now,
                participation.member_id,
                "program_ending",
                f'The reading program "{program.name}" ends on {program.ends_on.isoformat()}.',
                program_id=program.id,
            )
            reminders += 1

    result = ProcessOut(
        closed=len(ended),
        participants_completed=completed,
        participants_not_completed=not_completed,
        reminders=reminders,
    )
    record(
        db,
        at=now,
        event="programs_processed",
        actor_user_id=actor.id,
        entity_type="program",
        entity_id=None,
        details=result.model_dump(),
    )
    return result
