"""Light-weight lookups and hooks of module 25 used by other modules (members, branches, catalog, purchasing).

Imports only models, rules, notifications and the audit log, so that the other modules can use it without import
cycles."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.core.clock import LOCAL_TZ
from lms.suggestions.models import OPEN_STATUSES, Suggestion, Support
from lms.suggestions.schemas import SuggestionSummaryOut

# --- effects on other modules ---------------------------------------------------------------


def branch_has_open(db: Session, branch_id: int) -> bool:
    """LIB-SUG-47."""
    stmt = sa.select(Suggestion.id).where(Suggestion.branch_id == branch_id, Suggestion.status.in_(OPEN_STATUSES))
    return db.scalar(stmt.limit(1)) is not None


def book_in_use(db: Session, book_id: int) -> bool:
    """LIB-SUG-39: the book of an ``approved``, ``ordered`` or ``available`` suggestion cannot be deleted."""
    stmt = sa.select(Suggestion.id).where(
        Suggestion.book_id == book_id, Suggestion.status.in_(("approved", "ordered", "available"))
    )
    return db.scalar(stmt.limit(1)) is not None


def book_open_count(db: Session, book_id: int) -> int:
    """LIB-SUG-41: ``BookOut.open_suggestions``."""
    stmt = sa.select(sa.func.count()).select_from(Suggestion).where(
        Suggestion.book_id == book_id, Suggestion.status.in_(("approved", "ordered"))
    )
    return db.scalar(stmt) or 0


def order_suggestion_ids(db: Session, order_id: int) -> list[int]:
    """LIB-SUG-40: ``suggestion_ids`` of a purchase order, ascending."""
    return list(
        db.scalars(sa.select(Suggestion.id).where(Suggestion.purchase_order_id == order_id).order_by(Suggestion.id))
    )


def has_ordered(db: Session, order_id: int, book_id: int) -> bool:
    """LIB-SUG-30: the order has an ``ordered`` suggestion for the book."""
    stmt = sa.select(Suggestion.id).where(
        Suggestion.purchase_order_id == order_id, Suggestion.book_id == book_id, Suggestion.status == "ordered"
    )
    return db.scalar(stmt.limit(1)) is not None


def _back_to_approved(suggestion: Suggestion) -> None:
    suggestion.status = "approved"
    suggestion.purchase_order_id = None
    suggestion.ordered_at = None


def on_order_lines_replaced(db: Session, order_id: int, book_ids: set[int]) -> None:
    """LIB-SUG-29: suggestions of the draft order whose book is no longer in its lines go back to ``approved``."""
    stmt = sa.select(Suggestion).where(Suggestion.purchase_order_id == order_id, Suggestion.status == "ordered")
    for suggestion in db.scalars(stmt.order_by(Suggestion.id)):
        if suggestion.book_id not in book_ids:
            _back_to_approved(suggestion)


def on_order_cancelled(db: Session, order_id: int) -> None:
    """LIB-SUG-29: the ``ordered`` suggestions of a cancelled order go back to ``approved``."""
    stmt = sa.select(Suggestion).where(Suggestion.purchase_order_id == order_id, Suggestion.status == "ordered")
    for suggestion in db.scalars(stmt.order_by(Suggestion.id)):
        _back_to_approved(suggestion)


def on_member_deactivated(db: Session, now: datetime.datetime, actor_user_id: int | None, member_id: int) -> None:
    """LIB-SUG-36: ``submitted`` suggestions of the member are withdrawn and their supports of open suggestions
    removed; ``approved`` and ``ordered`` suggestions stay. Nobody is notified."""
    submitted = db.scalars(
        sa.select(Suggestion).where(Suggestion.member_id == member_id, Suggestion.status == "submitted").order_by(Suggestion.id)
    )
    for suggestion in submitted:
        suggestion.status = "withdrawn"
        suggestion.withdraw_reason = "member_deactivated"
        record(
            db,
            at=now,
            event="suggestion_withdrawn",
            actor_user_id=actor_user_id,
            entity_type="suggestion",
            entity_id=suggestion.id,
            details={"member_id": member_id, "withdraw_reason": "member_deactivated"},
        )
    supports = db.execute(
        sa.select(Support, Suggestion.id)
        .join(Suggestion, Suggestion.id == Support.suggestion_id)
        .where(Support.member_id == member_id, Suggestion.status.in_(OPEN_STATUSES))
        .order_by(Support.id)
    ).all()
    for support, suggestion_id in supports:
        db.delete(support)
        record(
            db,
            at=now,
            event="suggestion_support_removed",
            actor_user_id=actor_user_id,
            entity_type="suggestion",
            entity_id=suggestion_id,
            details={"member_id": member_id, "reason": "member_deactivated"},
        )
    db.flush()


def open_count(db: Session, member_id: int) -> int:
    """Open suggestions of the member (own)."""
    stmt = sa.select(sa.func.count()).select_from(Suggestion).where(
        Suggestion.member_id == member_id, Suggestion.status.in_(OPEN_STATUSES)
    )
    return db.scalar(stmt) or 0


def supported_count(db: Session, member_id: int) -> int:
    """Open suggestions the member supports."""
    stmt = (
        sa.select(sa.func.count())
        .select_from(Support)
        .join(Suggestion, Suggestion.id == Support.suggestion_id)
        .where(Support.member_id == member_id, Suggestion.status.in_(OPEN_STATUSES))
    )
    return db.scalar(stmt) or 0


def member_summary(db: Session, now: datetime.datetime, member_id: int) -> SuggestionSummaryOut:
    """LIB-SUG-38."""
    start = datetime.datetime(now.year, 1, 1, tzinfo=LOCAL_TZ)
    end = datetime.datetime(now.year + 1, 1, 1, tzinfo=LOCAL_TZ)
    available = db.scalar(
        sa.select(sa.func.count())
        .select_from(Suggestion)
        .where(Suggestion.member_id == member_id, Suggestion.available_at >= start, Suggestion.available_at < end)
    )
    return SuggestionSummaryOut(
        open=open_count(db, member_id), supported=supported_count(db, member_id), available_this_year=available or 0
    )
