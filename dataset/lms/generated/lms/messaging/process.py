"""Scheduled announcements and inactive threads (LIB-MSG-07, LIB-MSG-28, LIB-MSG-42)."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.messaging.announcements import release_due
from lms.messaging.models import Message, Thread
from lms.messaging.rules import INACTIVE_DAYS
from lms.messaging.schemas import ProcessOut
from lms.messaging.usage import close_thread


def close_inactive(db: Session, now: datetime.datetime, actor: User) -> int:
    """LIB-MSG-28: ``answered`` threads whose last message is more than 14 days old."""
    limit = datetime.timedelta(days=INACTIVE_DAYS)
    answered = db.scalars(sa.select(Thread).where(Thread.status == "answered").order_by(Thread.id)).all()
    closed = 0
    for thread in answered:
        last = db.scalar(sa.select(sa.func.max(Message.created_at)).where(Message.thread_id == thread.id))
        if last is not None and now - last > limit:
            close_thread(db, now, actor.id, thread, "inactive")
            closed += 1
    return closed


def process(db: Session, now: datetime.datetime, actor: User) -> ProcessOut:
    released = release_due(db, now)
    closed = close_inactive(db, now, actor)
    result = ProcessOut(announcements_released=released, threads_closed=closed)
    record(
        db,
        at=now,
        event="messaging_processed",
        actor_user_id=actor.id,
        entity_type="messaging",
        entity_id=None,
        details=result.model_dump(),
    )
    return result
