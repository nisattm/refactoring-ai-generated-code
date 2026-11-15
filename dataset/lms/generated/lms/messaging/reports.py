"""Messaging report (LIB-MSG-39)."""

from __future__ import annotations

import datetime
from decimal import ROUND_HALF_UP, Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.core.clock import LOCAL_TZ
from lms.messaging.models import CATEGORIES, Announcement, ReadMark, Thread
from lms.messaging.schemas import AnnouncementsReportOut, ByCategoryOut, MessagingReportOut


def _mean(values: list[Decimal]) -> str | None:
    if not values:
        return None
    mean = (sum(values, Decimal(0)) / Decimal(len(values))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return format(mean, "f")


def messaging_report(
    db: Session, now: datetime.datetime, first: datetime.date, last: datetime.date, branch_id: int | None
) -> MessagingReportOut:
    start = datetime.datetime.combine(first, datetime.time.min, LOCAL_TZ)
    end = datetime.datetime.combine(last + datetime.timedelta(days=1), datetime.time.min, LOCAL_TZ)
    threads_stmt = sa.select(Thread).where(Thread.created_at >= start, Thread.created_at < end)
    announcements_stmt = sa.select(Announcement.id, Announcement.priority).where(
        Announcement.published_at >= start, Announcement.published_at < end
    )
    if branch_id is not None:
        threads_stmt = threads_stmt.where(Thread.branch_id == branch_id)
        announcements_stmt = announcements_stmt.where(Announcement.branch_id == branch_id)
    threads = list(db.scalars(threads_stmt.order_by(Thread.id)))
    announcements = db.execute(announcements_stmt).all()

    replied = [t for t in threads if t.first_reply_at is not None]
    hours = [Decimal((t.first_reply_at - t.created_at).total_seconds()) / Decimal(3600) for t in replied]
    ratings = [Decimal(t.rating) for t in threads if t.rating is not None]
    reads = 0
    if announcements:
        reads = (
            db.scalar(
                sa.select(sa.func.count())
                .select_from(ReadMark)
                .where(ReadMark.announcement_id.in_([a_id for a_id, _ in announcements]))
            )
            or 0
        )
    return MessagingReportOut(
        threads=len(threads),
        by_category=ByCategoryOut(**{c: sum(1 for t in threads if t.category == c) for c in CATEGORIES}),
        answered=len(replied),
        average_first_reply_hours=_mean(hours),
        overdue_now=sum(1 for t in threads if t.status == "open" and t.due_at is not None and now > t.due_at),
        closed=sum(1 for t in threads if t.status == "closed"),
        average_rating=_mean(ratings),
        announcements=AnnouncementsReportOut(
            published=len(announcements),
            important=sum(1 for _, priority in announcements if priority == "important"),
            reads=reads,
        ),
    )
