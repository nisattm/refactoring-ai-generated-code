"""Ordering approved suggestions and expiry of old ones (LIB-SUG-26 to LIB-SUG-28, LIB-SUG-34, LIB-SUG-35)."""

from __future__ import annotations

import datetime
from collections import defaultdict
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.branches.models import Branch
from lms.core.errors import BusinessRuleViolation, Conflict, reference_not_found
from lms.core.lookup import get_reference_or_404
from lms.notifications.service import notify_suggestion
from lms.purchasing import service as purchasing
from lms.purchasing.models import PurchaseOrder, Supplier
from lms.purchasing.schemas import LineIn
from lms.suggestions import rules
from lms.suggestions.models import Suggestion
from lms.suggestions.schemas import ProcessOut
from lms.suggestions.service import invalid_status

MAX_LINE_QUANTITY = 100


def order(
    db: Session,
    now: datetime.datetime,
    actor: User,
    *,
    supplier_id: int,
    branch_id: int,
    suggestion_ids: list[int],
) -> PurchaseOrder:
    """LIB-SUG-26, LIB-SUG-27: all or nothing."""
    supplier = get_reference_or_404(db, Supplier, "supplier_id", supplier_id)
    branch = get_reference_or_404(db, Branch, "branch_id", branch_id)
    found = {s.id: s for s in db.scalars(sa.select(Suggestion).where(Suggestion.id.in_(suggestion_ids)))}
    for suggestion_id in suggestion_ids:
        if suggestion_id not in found:
            raise reference_not_found("suggestion_ids", suggestion_id)
    suggestions = [found[i] for i in suggestion_ids]

    if not branch.is_active:  # LIB-BR-04: before all other 409 checks
        raise Conflict(
            f"Branch {branch.code} is inactive", code="BRANCH_INACTIVE", details={"field": "branch_id", "id": branch.id}
        )
    if not supplier.is_active:
        raise Conflict("The supplier is inactive", code="SUPPLIER_INACTIVE", details={"id": supplier.id})
    for suggestion in suggestions:
        if suggestion.status != "approved":
            error = invalid_status(suggestion, "order")
            error.details["suggestion_id"] = suggestion.id
            raise error
    for suggestion in suggestions:
        if suggestion.branch_id != branch_id:
            raise Conflict(
                f"Suggestion {suggestion.id} is for another branch",
                code="SUGGESTION_BRANCH_MISMATCH",
                details={"suggestion_id": suggestion.id},
            )

    quantities: dict[int, int] = defaultdict(int)
    prices: dict[int, Decimal] = {}
    for suggestion in suggestions:
        assert suggestion.book_id is not None and suggestion.quantity is not None
        assert suggestion.estimated_price is not None
        quantities[suggestion.book_id] += suggestion.quantity
        prices[suggestion.book_id] = max(prices.get(suggestion.book_id, suggestion.estimated_price), suggestion.estimated_price)
    for book_id, quantity in quantities.items():
        if quantity > MAX_LINE_QUANTITY:
            raise BusinessRuleViolation(
                "The suggestions of a book add up to more than 100 copies",
                details={"book_id": book_id, "quantity": quantity},
            )
    lines = [LineIn(book_id=b, quantity=quantities[b], unit_price=prices[b]) for b in sorted(quantities)]
    purchase_order = purchasing.create_order(
        db, now, actor, supplier_id=supplier_id, branch_id=branch_id, lines=lines
    )
    for suggestion in sorted(suggestions, key=lambda s: s.id):
        suggestion.status = "ordered"
        suggestion.ordered_at = now
        suggestion.purchase_order_id = purchase_order.id
    db.flush()
    record(
        db,
        at=now,
        event="suggestions_ordered",
        actor_user_id=actor.id,
        entity_type="purchase_order",
        entity_id=purchase_order.id,
        details={"supplier_id": supplier_id, "branch_id": branch_id, "suggestion_ids": sorted(suggestion_ids)},
    )
    for suggestion in sorted(suggestions, key=lambda s: s.id):
        notify_suggestion(
            db,
            now,
            suggestion.member_id,
            "suggestion_ordered",
            f'The library ordered "{suggestion.title}", which you suggested.',
            suggestion_id=suggestion.id,
        )
    return purchase_order


def process(db: Session, now: datetime.datetime, actor: User) -> ProcessOut:
    """LIB-SUG-34."""
    submitted = db.scalars(
        sa.select(Suggestion)
        .where(
            Suggestion.status == "submitted",
            Suggestion.submitted_at < now - datetime.timedelta(days=rules.SUBMITTED_EXPIRY_DAYS),
        )
        .order_by(Suggestion.id)
    ).all()
    approved = db.scalars(
        sa.select(Suggestion)
        .where(
            Suggestion.status == "approved",
            Suggestion.reviewed_at < now - datetime.timedelta(days=rules.APPROVED_EXPIRY_DAYS),
        )
        .order_by(Suggestion.id)
    ).all()
    for suggestion in [*submitted, *approved]:
        suggestion.status = "expired"
        notify_suggestion(
            db,
            now,
            suggestion.member_id,
            "suggestion_expired",
            f'Your suggestion "{suggestion.title}" expired.',
            suggestion_id=suggestion.id,
        )
    result = ProcessOut(expired_submitted=len(submitted), expired_approved=len(approved))
    record(
        db,
        at=now,
        event="suggestions_processed",
        actor_user_id=actor.id,
        entity_type="suggestion",
        entity_id=None,
        details=result.model_dump() | {"suggestion_ids": [s.id for s in [*submitted, *approved]]},
    )
    return result
