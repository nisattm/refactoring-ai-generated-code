"""Hooks and figures of module 27 used by other modules (members, branches, users) and for audiences.

Imports only models, schemas and the audit log, so that the other modules can use it without import cycles."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.members.models import Member
from lms.messaging.models import Announcement, Message, ReadMark, Thread
from lms.messaging.schemas import MessagesSummaryOut, audience_key


# --- audiences (35.1) ---------------------------------------------------------------------------


def is_for(announcement: Announcement, member: Member) -> bool:
    """35.1: the member is ``active``, the type is in ``audience`` and the branch fits."""
    if member.status != "active":
        return False
    if member.membership_type not in {audience_key(item) for item in announcement.audience}:
        return False
    return announcement.branch_id is None or announcement.branch_id == member.home_branch_id


def audience_members(db: Session, announcement: Announcement) -> list[Member]:
    """The members the announcement is for now, by id."""
    stmt = sa.select(Member).where(Member.status == "active").order_by(Member.id)
    if announcement.branch_id is not None:
        stmt = stmt.where(Member.home_branch_id == announcement.branch_id)
    return [m for m in db.scalars(stmt) if is_for(announcement, m)]


def live_stmt(now: datetime.datetime) -> sa.Select[tuple[Announcement]]:
    return sa.select(Announcement).where(
        Announcement.status == "published",
        Announcement.publish_at <= now,
        sa.or_(Announcement.expires_at.is_(None), Announcement.expires_at > now),
    )


def live_for_member(db: Session, now: datetime.datetime, member: Member) -> list[Announcement]:
    """The live announcements for the member in the order of LIB-MSG-09."""
    stmt = live_stmt(now).order_by(Announcement.pinned.desc(), Announcement.publish_at.desc(), Announcement.id.desc())
    return [a for a in db.scalars(stmt) if is_for(a, member)]


def read_ids(db: Session, member_id: int) -> set[int]:
    return set(db.scalars(sa.select(ReadMark.announcement_id).where(ReadMark.member_id == member_id)))


# --- hooks --------------------------------------------------------------------------------------


def branch_has_open_items(db: Session, branch_id: int, now: datetime.datetime) -> bool:
    """LIB-MSG-34: a thread that is not ``closed`` or a ``published`` announcement that is live or scheduled."""
    thread = sa.select(Thread.id).where(Thread.branch_id == branch_id, Thread.status != "closed")
    if db.scalar(thread.limit(1)) is not None:
        return True
    announcement = sa.select(Announcement.id).where(
        Announcement.branch_id == branch_id,
        Announcement.status == "published",
        sa.or_(Announcement.expires_at.is_(None), Announcement.expires_at > now),
    )
    return db.scalar(announcement.limit(1)) is not None


def on_member_deactivated(db: Session, now: datetime.datetime, actor_user_id: int | None, member_id: int) -> None:
    """LIB-MSG-32: the threads that are not ``closed`` are closed. Nobody is notified (LIB-MSG-37)."""
    threads = db.scalars(
        sa.select(Thread).where(Thread.member_id == member_id, Thread.status != "closed").order_by(Thread.id)
    ).all()
    for thread in threads:
        close_thread(db, now, actor_user_id, thread, "member_deactivated")
    db.flush()


def close_thread(
    db: Session, now: datetime.datetime, actor_user_id: int | None, thread: Thread, reason: str
) -> None:
    thread.status = "closed"
    thread.closed_at = now
    thread.close_reason = reason
    record(
        db,
        at=now,
        event="thread_closed",
        actor_user_id=actor_user_id,
        entity_type="thread",
        entity_id=thread.id,
        details={"member_id": thread.member_id, "close_reason": reason},
    )


def on_user_deactivated(db: Session, user_id: int) -> None:
    """LIB-MSG-36: the threads assigned to the user lose their assignee."""
    db.execute(sa.update(Thread).where(Thread.assigned_to == user_id).values(assigned_to=None))


def member_summary(db: Session, now: datetime.datetime, member_id: int) -> MessagesSummaryOut:
    """LIB-MSG-33."""
    member = db.get(Member, member_id)
    unread_announcements = 0
    if member is not None:
        seen = read_ids(db, member_id)
        unread_announcements = sum(1 for a in live_for_member(db, now, member) if a.id not in seen)
    open_threads = db.scalar(
        sa.select(sa.func.count()).select_from(Thread).where(Thread.member_id == member_id, Thread.status != "closed")
    )
    unread_replies = db.scalar(
        sa.select(sa.func.count())
        .select_from(Message)
        .join(Thread, Thread.id == Message.thread_id)
        .where(
            Thread.member_id == member_id,
            Message.author == "staff",
            Message.internal.is_(False),
            Message.read_at.is_(None),
        )
    )
    return MessagesSummaryOut(
        unread_announcements=unread_announcements, open_threads=open_threads or 0, unread_replies=unread_replies or 0
    )
