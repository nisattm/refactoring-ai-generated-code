"""Access bans (LIB-ACC-29 to LIB-ACC-33)."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.access.models import AccessBan
from lms.access.rules import MAX_BAN_DAYS
from lms.access.usage import open_visit_of_member
from lms.audit.service import record
from lms.auth.models import User
from lms.core.errors import Conflict, ValidationFailed
from lms.core.lookup import get_or_404
from lms.members.models import Member
from lms.notifications.service import notify_access


def get_ban_or_404(db: Session, ban_id: int) -> AccessBan:
    return get_or_404(db, AccessBan, ban_id, "Access ban", "access_ban")


def create_ban(
    db: Session,
    now: datetime.datetime,
    actor: User,
    member: Member,
    reason: str,
    starts_on: datetime.date | None,
    ends_on: datetime.date,
) -> AccessBan:
    """LIB-ACC-29, LIB-ACC-33."""
    today = now.date()
    start = starts_on if starts_on is not None else today
    problems: list[dict[str, str]] = []
    if start < today:
        problems.append({"field": "starts_on", "problem": "starts_on must not be in the past"})
    if ends_on < start:
        problems.append({"field": "ends_on", "problem": "ends_on must not be before starts_on"})
    elif (ends_on - start).days > MAX_BAN_DAYS:
        problems.append({"field": "ends_on", "problem": "ends_on must be at most 365 days after starts_on"})
    if problems:
        raise ValidationFailed(problems)
    overlapping = db.scalar(
        sa.select(AccessBan.id)
        .where(
            AccessBan.member_id == member.id,
            AccessBan.lifted_at.is_(None),
            AccessBan.starts_on <= ends_on,
            AccessBan.ends_on >= start,
        )
        .order_by(AccessBan.id)
        .limit(1)
    )
    if overlapping is not None:
        raise Conflict("The ban overlaps another ban", code="BAN_OVERLAPS", details={"ban_id": overlapping})
    ban = AccessBan(member_id=member.id, reason=reason, starts_on=start, ends_on=ends_on, created_by=actor.id)
    db.add(ban)
    db.flush()
    record(
        db,
        at=now,
        event="access_ban_created",
        actor_user_id=actor.id,
        entity_type="access_ban",
        entity_id=ban.id,
        details={
            "member_id": member.id,
            "reason": reason,
            "starts_on": start.isoformat(),
            "ends_on": ends_on.isoformat(),
        },
    )
    notify_access(
        db, now, member.id, "access_banned", f"You are banned from entering the library until {ends_on.isoformat()}."
    )
    if start == today:
        visit = open_visit_of_member(db, member.id)
        if visit is not None:
            visit.left_at = now
            visit.closed_by = "staff"
    return ban


def lift_ban(db: Session, now: datetime.datetime, actor: User, ban: AccessBan) -> AccessBan:
    """LIB-ACC-30."""
    if ban.lifted_at is not None:
        raise Conflict("The ban is already lifted", code="BAN_ALREADY_LIFTED")
    ban.lifted_at = now
    record(
        db,
        at=now,
        event="access_ban_lifted",
        actor_user_id=actor.id,
        entity_type="access_ban",
        entity_id=ban.id,
        details={"member_id": ban.member_id},
    )
    return ban
