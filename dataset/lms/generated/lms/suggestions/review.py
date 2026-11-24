"""Review of suggestions: approve, reject, merge, change an approval (LIB-SUG-15 to LIB-SUG-25)."""

from __future__ import annotations

import datetime
from collections.abc import Container
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import changes, record
from lms.auth.models import User
from lms.catalog.models import Book
from lms.core.db import get_or_404, get_reference
from lms.core.errors import Conflict, Forbidden, ValidationFailed
from lms.core.money import format_amount
from lms.notifications.service import notify_suggestion
from lms.suggestions import arrival, rules
from lms.suggestions.models import Suggestion, Support
from lms.suggestions.service import invalid_status, supporters_of

LIBRARIAN_LIMIT = Decimal(rules.LIBRARIAN_LIMIT)


def check_approval_rights(actor: User, quantity: int, price: Decimal) -> None:
    """LIB-SUG-20: a total above 300.00 is for admins only."""
    if actor.role != "admin" and quantity * price > LIBRARIAN_LIMIT:
        raise Forbidden("Approvals above 300.00 need an administrator")


def approve(
    db: Session,
    now: datetime.datetime,
    actor: User,
    suggestion: Suggestion,
    *,
    book: Book,
    quantity: int,
    estimated_price: Decimal,
    review_note: str,
) -> Suggestion:
    """LIB-SUG-15, LIB-SUG-16."""
    if suggestion.status != "submitted":
        raise invalid_status(suggestion, "approve")
    if suggestion.isbn is not None and suggestion.isbn != book.isbn:
        raise Conflict(
            "The ISBN of the suggestion differs from the ISBN of the book",
            code="ISBN_MISMATCH",
            details={"suggestion_isbn": suggestion.isbn, "book_isbn": book.isbn, "book_id": book.id},
        )
    suggestion.status = "approved"
    suggestion.reviewed_at = now
    suggestion.book_id = book.id
    suggestion.quantity = quantity
    suggestion.estimated_price = estimated_price
    suggestion.review_note = review_note
    record(
        db,
        at=now,
        event="suggestion_approved",
        actor_user_id=actor.id,
        entity_type="suggestion",
        entity_id=suggestion.id,
        details={
            "book_id": book.id,
            "quantity": quantity,
            "estimated_price": format_amount(estimated_price),
            "review_note": review_note,
        },
    )
    notify_suggestion(
        db,
        now,
        suggestion.member_id,
        "suggestion_approved",
        f'Your suggestion "{suggestion.title}" was approved and will be ordered.',
        suggestion_id=suggestion.id,
    )
    return suggestion


def change_approval(
    db: Session, now: datetime.datetime, actor: User, suggestion: Suggestion, fields: dict[str, Any]
) -> Suggestion:
    """LIB-SUG-24."""
    if suggestion.status != "approved":
        raise invalid_status(suggestion, "change the approval of")
    assert suggestion.quantity is not None and suggestion.estimated_price is not None
    quantity = fields.get("quantity", suggestion.quantity)
    price = fields.get("estimated_price", suggestion.estimated_price)
    check_approval_rights(actor, quantity, price)
    diff = changes({name: getattr(suggestion, name) for name in fields}, fields)
    for name, value in fields.items():
        setattr(suggestion, name, value)
    if "estimated_price" in diff:
        diff["estimated_price"] = {k: format_amount(v) for k, v in diff["estimated_price"].items()}
    record(
        db,
        at=now,
        event="suggestion_approval_changed",
        actor_user_id=actor.id,
        entity_type="suggestion",
        entity_id=suggestion.id,
        details=diff,
    )
    return suggestion


def reject(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    suggestion: Suggestion,
    *,
    reject_reason: str,
    review_note: str,
    book_id: int | None,
) -> Suggestion:
    """LIB-SUG-17, LIB-SUG-18."""
    if reject_reason == "already_owned":
        if book_id is None:
            raise ValidationFailed.single("book_id", "book_id is required when the reason is already_owned")
        get_reference(db, Book, "book_id", book_id)
    if suggestion.status not in ("submitted", "approved"):
        raise invalid_status(suggestion, "reject")
    old = suggestion.status
    suggestion.status = "rejected"
    suggestion.reject_reason = reject_reason
    suggestion.review_note = review_note
    suggestion.reviewed_at = now
    record(
        db,
        at=now,
        event="suggestion_rejected",
        actor_user_id=actor.id,
        entity_type="suggestion",
        entity_id=suggestion.id,
        details={
            "status": {"old": old, "new": "rejected"},
            "reject_reason": reject_reason,
            "review_note": review_note,
            "book_id": book_id,
        },
    )
    notify_suggestion(
        db,
        now,
        suggestion.member_id,
        "suggestion_rejected",
        f'Your suggestion "{suggestion.title}" was rejected (reason: {reject_reason}).',
        suggestion_id=suggestion.id,
    )
    if reject_reason == "already_owned":
        assert book_id is not None
        arrival.create_reservations(db, now, actor, holidays, suggestion, book_id)
    return suggestion


def merge(
    db: Session, now: datetime.datetime, actor: User, source: Suggestion, target_id: int
) -> Suggestion:
    """LIB-SUG-22."""
    target = get_or_404(db, Suggestion, target_id, "Suggestion", "suggestion")
    if source.status != "submitted":
        raise invalid_status(source, "merge")
    if target.status not in ("submitted", "approved"):
        raise invalid_status(target, "merge into")
    existing = {s.member_id for s in supporters_of(db, target.id)} | {target.member_id}
    moving = [(source.member_id, True)] + [(s.member_id, s.reserve_on_arrival) for s in supporters_of(db, source.id)]
    db.execute(sa.delete(Support).where(Support.suggestion_id == source.id))
    for member_id, reserve in moving:
        if member_id in existing:
            continue
        existing.add(member_id)
        db.add(Support(suggestion_id=target.id, member_id=member_id, reserve_on_arrival=reserve, created_at=now))
    source.status = "merged"
    source.merged_into_id = target.id
    db.flush()
    record(
        db,
        at=now,
        event="suggestion_merged",
        actor_user_id=actor.id,
        entity_type="suggestion",
        entity_id=source.id,
        details={"into_suggestion_id": target.id},
    )
    return target
