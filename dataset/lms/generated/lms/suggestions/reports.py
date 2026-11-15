"""Suggestions report (LIB-SUG-44)."""

from __future__ import annotations

import datetime
from decimal import ROUND_HALF_UP, Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.core.clock import LOCAL_TZ
from lms.suggestions.models import Suggestion
from lms.suggestions.schemas import REJECT_REASONS, RejectedCountsOut, SuggestionReportOut, TopOut
from lms.suggestions.service import stats

TOP = 5


def suggestion_report(
    db: Session, first: datetime.date, last: datetime.date, branch_id: int | None
) -> SuggestionReportOut:
    start = datetime.datetime.combine(first, datetime.time.min, LOCAL_TZ)
    end = datetime.datetime.combine(last + datetime.timedelta(days=1), datetime.time.min, LOCAL_TZ)
    stmt = sa.select(Suggestion).where(Suggestion.submitted_at >= start, Suggestion.submitted_at < end)
    if branch_id is not None:
        stmt = stmt.where(Suggestion.branch_id == branch_id)
    suggestions = list(db.scalars(stmt.order_by(Suggestion.id)))

    def count(*statuses: str) -> int:
        return sum(1 for s in suggestions if s.status in statuses)

    rejected = RejectedCountsOut(
        **{reason: sum(1 for s in suggestions if s.status == "rejected" and s.reject_reason == reason) for reason in REJECT_REASONS}
    )
    days = [
        (s.available_at.date() - s.submitted_at.date()).days
        for s in suggestions
        if s.available_at is not None
    ]
    average = None
    if days:
        mean = (Decimal(sum(days)) / Decimal(len(days))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        average = format(mean, "f")
    figures = stats(db, suggestions)
    ranked = sorted(suggestions, key=lambda s: (-figures[s.id][0], s.submitted_at, s.id))[:TOP]
    return SuggestionReportOut(
        submitted=len(suggestions),
        approved=count("approved", "ordered", "available"),
        rejected=rejected,
        ordered=count("ordered"),
        available=count("available"),
        withdrawn=count("withdrawn"),
        merged=count("merged"),
        expired=count("expired"),
        average_days_to_available=average,
        top=[TopOut(suggestion_id=s.id, title=s.title, score=figures[s.id][0]) for s in ranked],
    )
