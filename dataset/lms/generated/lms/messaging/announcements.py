"""Announcements: create, change, publish, withdraw, read and statistics (sections 35.3 and 35.6)."""

from __future__ import annotations

import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import changes, record
from lms.auth.models import User
from lms.branches.models import Branch
from lms.core.db import get_or_404
from lms.core.errors import Conflict, ValidationFailed
from lms.members.models import Member
from lms.messaging import usage
from lms.messaging.models import Announcement, ReadMark
from lms.messaging.rules import MAX_ANNOUNCEMENT_DAYS, PIN_LIMIT
from lms.messaging.schemas import AnnouncementOut, ReadOut, StatsOut, announcement_out
from lms.notifications.service import notify_announcement
from lms.core.timeutil import format_datetime


def get_announcement_or_404(db: Session, announcement_id: int) -> Announcement:
    return get_or_404(db, Announcement, announcement_id, "Announcement", "announcement")


def _status_error(announcement: Announcement) -> Conflict:
    return Conflict(
        "The announcement status does not allow this",
        code="INVALID_ANNOUNCEMENT_STATUS",
        details={"status": announcement.status},
    )


# --- validation ---------------------------------------------------------------------------------


def check_expiry(publish_at: datetime.datetime, expires_at: datetime.datetime | None) -> None:
    """35.1: ``expires_at`` is after ``publish_at`` and at most 90 days after it."""
    if expires_at is None:
        return
    if expires_at <= publish_at:
        raise ValidationFailed.single("expires_at", "expires_at must be after publish_at")
    if expires_at - publish_at > datetime.timedelta(days=MAX_ANNOUNCEMENT_DAYS):
        raise ValidationFailed.single("expires_at", "expires_at must be at most 90 days after publish_at")


def check_branch(db: Session, branch_id: int | None) -> None:
    """LIB-MSG-01: an unknown branch is ``422``, an inactive one ``409 BRANCH_INACTIVE``."""
    if branch_id is None:
        return
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise ValidationFailed.single("branch_id", f"branch {branch_id} does not exist")
    if not branch.is_active:
        raise Conflict(
            f"Branch {branch.code} is inactive", code="BRANCH_INACTIVE", details={"field": "branch_id", "id": branch_id}
        )


def _iso(value: Any) -> Any:
    return format_datetime(value) if isinstance(value, datetime.datetime) else value


# --- create and change --------------------------------------------------------------------------


def create_announcement(db: Session, now: datetime.datetime, actor: User, data: dict[str, Any]) -> Announcement:
    """LIB-MSG-01."""
    publish_at = data["publish_at"] if data["publish_at"] is not None else now
    check_expiry(publish_at, data["expires_at"])
    check_branch(db, data["branch_id"])
    announcement = Announcement(**{**data, "publish_at": publish_at}, status="draft", created_at=now)
    db.add(announcement)
    db.flush()
    record(
        db,
        at=now,
        event="announcement_created",
        actor_user_id=actor.id,
        entity_type="announcement",
        entity_id=announcement.id,
        details={
            "title": announcement.title,
            "branch_id": announcement.branch_id,
            "audience": list(announcement.audience),
            "priority": announcement.priority,
            "pinned": announcement.pinned,
            "publish_at": format_datetime(announcement.publish_at),
            "expires_at": _iso(announcement.expires_at),
        },
    )
    return announcement


def update_announcement(
    db: Session, now: datetime.datetime, actor: User, announcement: Announcement, fields: dict[str, Any]
) -> Announcement:
    """LIB-MSG-02."""
    if announcement.status == "withdrawn":
        raise _status_error(announcement)
    publish_at = fields.get("publish_at", announcement.publish_at)
    check_expiry(publish_at, fields.get("expires_at", announcement.expires_at))
    if "branch_id" in fields and fields["branch_id"] != announcement.branch_id:
        check_branch(db, fields["branch_id"])
    if "publish_at" in fields and fields["publish_at"] != announcement.publish_at and announcement.is_live(now):
        raise Conflict(
            "The publication time of a live announcement cannot change",
            code="ANNOUNCEMENT_LIVE",
            details={"publish_at": format_datetime(announcement.publish_at)},
        )

    old = {name: getattr(announcement, name) for name in fields}
    diff = changes(old, fields)
    for name, value in fields.items():
        setattr(announcement, name, value)
    if announcement.status == "published" and ("title" in diff or "body" in diff):
        db.execute(sa.delete(ReadMark).where(ReadMark.announcement_id == announcement.id))
    if diff:
        record(
            db,
            at=now,
            event="announcement_updated",
            actor_user_id=actor.id,
            entity_type="announcement",
            entity_id=announcement.id,
            details={name: {"old": _iso(c["old"]), "new": _iso(c["new"])} for name, c in diff.items()},
        )
    return announcement


# --- publish and withdraw -----------------------------------------------------------------------


def notify_audience(db: Session, now: datetime.datetime, announcement: Announcement) -> None:
    """LIB-MSG-06: one ``announcement`` notification for every member the announcement is for."""
    for member in usage.audience_members(db, announcement):
        notify_announcement(db, now, member.id, announcement.title, announcement_id=announcement.id)


def publish(db: Session, now: datetime.datetime, actor: User, announcement: Announcement) -> Announcement:
    """LIB-MSG-03 and LIB-MSG-04."""
    if announcement.status != "draft":
        raise _status_error(announcement)
    if announcement.expires_at is not None and announcement.expires_at <= now:
        raise Conflict(
            "The announcement has already expired",
            code="ANNOUNCEMENT_EXPIRED",
            details={"expires_at": format_datetime(announcement.expires_at)},
        )
    if announcement.pinned:
        pinned = db.scalar(
            sa.select(sa.func.count())
            .select_from(Announcement)
            .where(
                Announcement.id != announcement.id,
                Announcement.status == "published",
                Announcement.pinned.is_(True),
                sa.or_(Announcement.expires_at.is_(None), Announcement.expires_at > now),
                Announcement.branch_id.is_(None)
                if announcement.branch_id is None
                else Announcement.branch_id == announcement.branch_id,
            )
        )
        if (pinned or 0) >= PIN_LIMIT:
            raise Conflict(
                "Too many pinned announcements",
                code="PIN_LIMIT_REACHED",
                details={"limit": PIN_LIMIT},
            )
    announcement.status = "published"
    released = announcement.publish_at <= now
    if released:
        announcement.published_at = now
    record(
        db,
        at=now,
        event="announcement_published",
        actor_user_id=actor.id,
        entity_type="announcement",
        entity_id=announcement.id,
        details={"publish_at": format_datetime(announcement.publish_at), "scheduled": not released},
    )
    if released and announcement.priority == "important":
        notify_audience(db, now, announcement)
    return announcement


def withdraw(db: Session, now: datetime.datetime, actor: User, announcement: Announcement) -> Announcement:
    """LIB-MSG-05."""
    if announcement.status != "published":
        raise _status_error(announcement)
    announcement.status = "withdrawn"
    announcement.withdrawn_at = now
    record(
        db,
        at=now,
        event="announcement_withdrawn",
        actor_user_id=actor.id,
        entity_type="announcement",
        entity_id=announcement.id,
        details={},
    )
    return announcement


def release_due(db: Session, now: datetime.datetime) -> int:
    """LIB-MSG-07: scheduled announcements that became live get ``published_at`` and notify."""
    due = db.scalars(
        sa.select(Announcement)
        .where(
            Announcement.status == "published",
            Announcement.publish_at <= now,
            Announcement.published_at.is_(None),
        )
        .order_by(Announcement.id)
    ).all()
    for announcement in due:
        announcement.published_at = now
        expired = announcement.expires_at is not None and announcement.expires_at <= now
        if announcement.priority == "important" and not expired:
            notify_audience(db, now, announcement)
    db.flush()
    return len(due)


# --- reading ------------------------------------------------------------------------------------


def list_stmt(
    now: datetime.datetime,
    *,
    status: str | None,
    branch_id: int | None,
    live: bool | None,
    scheduled: bool | None,
) -> sa.Select[tuple[Announcement]]:
    """LIB-MSG-10."""
    stmt = sa.select(Announcement).order_by(Announcement.id.desc())
    if status is not None:
        stmt = stmt.where(Announcement.status == status)
    if branch_id is not None:
        stmt = stmt.where(Announcement.branch_id == branch_id)
    is_live = sa.and_(
        Announcement.status == "published",
        Announcement.publish_at <= now,
        sa.or_(Announcement.expires_at.is_(None), Announcement.expires_at > now),
    )
    if live is not None:
        stmt = stmt.where(is_live if live else sa.not_(is_live))
    if scheduled is not None:
        is_scheduled = sa.and_(Announcement.status == "published", Announcement.publish_at > now)
        stmt = stmt.where(is_scheduled if scheduled else sa.not_(is_scheduled))
    return stmt


def member_visible(announcement: Announcement, member: Member, now: datetime.datetime) -> bool:
    return announcement.is_live(now) and usage.is_for(announcement, member)


def member_out(db: Session, now: datetime.datetime, announcement: Announcement, read: bool) -> AnnouncementOut:
    result = announcement_out(announcement, now)
    result.read = read
    return result


def mark_read(db: Session, now: datetime.datetime, announcement: Announcement, member: Member) -> datetime.datetime:
    """LIB-MSG-11: a read mark exists once; repeating changes nothing."""
    mark = db.scalar(
        sa.select(ReadMark).where(ReadMark.announcement_id == announcement.id, ReadMark.member_id == member.id)
    )
    if mark is None:
        mark = ReadMark(announcement_id=announcement.id, member_id=member.id, read_at=now)
        db.add(mark)
        db.flush()
    return mark.read_at


def read_out(announcement: Announcement, read_at: datetime.datetime) -> ReadOut:
    return ReadOut(announcement_id=announcement.id, read_at=format_datetime(read_at))


def stats(db: Session, announcement: Announcement) -> StatsOut:
    """LIB-MSG-12."""
    audience_size = len(usage.audience_members(db, announcement))
    reads = db.scalar(
        sa.select(sa.func.count()).select_from(ReadMark).where(ReadMark.announcement_id == announcement.id)
    ) or 0
    rate = "0.0"
    if audience_size:
        rate = format((Decimal(reads) * 100 / Decimal(audience_size)).quantize(Decimal("0.1"), ROUND_HALF_UP), "f")
    return StatsOut(audience_size=audience_size, reads=reads, read_rate=rate)
