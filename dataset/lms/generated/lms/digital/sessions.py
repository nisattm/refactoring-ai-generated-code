"""Database sessions (LIB-DIG-28 to LIB-DIG-32)."""

from __future__ import annotations

import datetime
from collections.abc import Container

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.auth.models import User
from lms.core.clock import LOCAL_TZ
from lms.core.errors import NotFound
from lms.core.timeutil import format_datetime
from lms.digital import state
from lms.digital.models import DigitalResource, DigitalSession
from lms.digital.rules import DAILY_SESSIONS, DIGITAL_RULES, SESSION_LENGTH
from lms.members.models import Member


def get_session_or_404(db: Session, session_id: int) -> DigitalSession:
    session = db.get(DigitalSession, session_id)
    if session is None:
        raise NotFound(f"Digital session {session_id} does not exist", details={"resource": "digital_session", "id": session_id})
    return session


def open_session(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    resource: DigitalResource,
    member: Member,
) -> DigitalSession:
    """LIB-DIG-28, LIB-DIG-30."""
    if resource.kind != "database":
        raise state.error("WRONG_RESOURCE_KIND", "The resource is an e-book, not a database", kind=resource.kind)
    state.check_member_and_resource(db, now, holidays, resource, member)
    own_open = [s for s in state.open_sessions(db, resource.id, now) if s.member_id == member.id]
    if own_open:
        raise state.error("SESSION_ALREADY_OPEN", "The member has an open session of this resource", session_id=own_open[0].id)
    day_start = datetime.datetime.combine(now.date(), datetime.time.min, LOCAL_TZ)
    today_count = db.scalar(
        sa.select(sa.func.count()).select_from(DigitalSession).where(
            DigitalSession.member_id == member.id,
            DigitalSession.resource_id == resource.id,
            DigitalSession.started_at >= day_start,
            DigitalSession.started_at < day_start + datetime.timedelta(days=1),
        )
    ) or 0
    if today_count >= DAILY_SESSIONS:
        raise state.error("DAILY_SESSION_LIMIT_REACHED", "The member has used all sessions of this resource today", limit=DAILY_SESSIONS)
    limit = DIGITAL_RULES[member.membership_type].sessions
    if state.member_open_sessions(db, member.id, now) >= limit:
        raise state.error("SESSION_LIMIT_REACHED", "The member has reached the session limit", limit=limit)
    capacity = state.capacity_at(db, resource.id, now)
    if capacity == 0:
        raise state.error("NO_ACTIVE_LICENSE", "The resource has no active license")
    open_now = state.open_sessions(db, resource.id, now)
    if len(open_now) >= capacity:
        raise state.error(
            "NO_SEAT_AVAILABLE",
            "No seat is available",
            next_free_at=format_datetime(min(s.expires_at for s in open_now)),
        )
    session = DigitalSession(resource_id=resource.id, member_id=member.id, started_at=now, expires_at=now + SESSION_LENGTH)
    db.add(session)
    db.flush()
    state.audit(
        db,
        now,
        actor.id,
        "digital_session_opened",
        "digital_session",
        session.id,
        resource_id=resource.id,
        member_id=member.id,
        expires_at=format_datetime(session.expires_at),
    )
    return session


def close_session(db: Session, now: datetime.datetime, session: DigitalSession) -> DigitalSession:
    """LIB-DIG-29: closing is not audited."""
    if not session.is_open(now):
        raise state.error("SESSION_NOT_OPEN", "The session is not open")
    session.closed_at = now
    return session


def member_session_stmt(
    member_id: int, now: datetime.datetime, *, open_: bool | None, resource_id: int | None
) -> sa.Select[tuple[DigitalSession]]:
    """LIB-DIG-32."""
    stmt = (
        sa.select(DigitalSession)
        .where(DigitalSession.member_id == member_id)
        .order_by(DigitalSession.started_at.desc(), DigitalSession.id.desc())
    )
    if resource_id is not None:
        stmt = stmt.where(DigitalSession.resource_id == resource_id)
    if open_ is not None:
        is_open = sa.and_(DigitalSession.closed_at.is_(None), DigitalSession.expires_at > now)
        stmt = stmt.where(is_open if open_ else sa.not_(is_open))
    return stmt
