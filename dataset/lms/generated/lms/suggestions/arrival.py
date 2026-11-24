"""Reservations for the people behind a suggestion and the arrival of ordered copies (LIB-SUG-18, LIB-SUG-30 to
LIB-SUG-33)."""

from __future__ import annotations

import datetime
from collections.abc import Collection, Container

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.core.errors import Conflict
from lms.notifications.service import notify_suggestion
from lms.reservations.service import create_reservation
from lms.suggestions.models import Suggestion
from lms.suggestions.service import supporters_of


def create_reservations(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    suggestion: Suggestion,
    book_id: int,
    ignore_copy_ids: Collection[int] = (),
) -> None:
    """LIB-SUG-33: the member, then each supporter with ``reserve_on_arrival`` (in support order), reserve the book
    for pickup at the branch of the suggestion. A person for whom LIB-RES-02 fails is skipped."""
    people = [suggestion.member_id]
    people += [s.member_id for s in supporters_of(db, suggestion.id) if s.reserve_on_arrival]
    for member_id in people:
        try:
            create_reservation(
                db,
                now,
                actor,
                holidays,
                member_id=member_id,
                book_id=book_id,
                pickup_branch_id=suggestion.branch_id,
                ignore_copy_ids=ignore_copy_ids,
            )
        except Conflict:
            continue


def make_available(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    order_id: int,
    book_id: int,
    new_copy_ids: Collection[int],
) -> None:
    """LIB-SUG-30: the ``ordered`` suggestions of the order for the book become ``available``, their people get
    reservations and are notified. The new copies are released by the caller afterwards."""
    stmt = sa.select(Suggestion).where(
        Suggestion.purchase_order_id == order_id, Suggestion.book_id == book_id, Suggestion.status == "ordered"
    )
    for suggestion in db.scalars(stmt.order_by(Suggestion.id)).all():
        suggestion.status = "available"
        suggestion.available_at = now
        record(
            db,
            at=now,
            event="suggestion_available",
            actor_user_id=actor.id,
            entity_type="suggestion",
            entity_id=suggestion.id,
            details={"purchase_order_id": order_id, "book_id": book_id},
        )
        create_reservations(db, now, actor, holidays, suggestion, book_id, new_copy_ids)
        people = [suggestion.member_id] + [s.member_id for s in supporters_of(db, suggestion.id)]
        for member_id in dict.fromkeys(people):
            notify_suggestion(
                db,
                now,
                member_id,
                "suggestion_available",
                f'"{suggestion.title}" you suggested or supported is now available at the library.',
                suggestion_id=suggestion.id,
            )
