"""Suggestions and review of donations (LIB-DON-14 to LIB-DON-18)."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.branches.models import Branch
from lms.catalog.models import Book, Copy
from lms.core.errors import Conflict, ValidationFailed
from lms.donations import offers
from lms.donations.models import Donation, Donor
from lms.donations.rules import DUPLICATE_COPIES, EXPECTED_DAYS, TOO_OLD_YEARS
from lms.donations.schemas import ReviewItemIn, SuggestionOut, SuggestionsOut
from lms.notifications.service import notify_donation


def _book_by_isbn(db: Session, isbn: str | None) -> Book | None:
    if isbn is None:
        return None
    return db.scalar(sa.select(Book).where(Book.isbn == isbn))


def _copies_at_branch(db: Session, book_id: int, branch_id: int) -> int:
    stmt = (
        sa.select(sa.func.count())
        .select_from(Copy)
        .where(Copy.book_id == book_id, Copy.home_branch_id == branch_id, Copy.status.not_in(("lost", "withdrawn")))
    )
    return db.scalar(stmt) or 0


def suggestions(db: Session, now: datetime.datetime, donation: Donation) -> SuggestionsOut:
    """LIB-DON-14."""
    result: list[SuggestionOut] = []
    for item in offers.items_of(db, donation.id):
        if item.decision != "pending":
            continue
        decision: str | None = None
        reason: str | None = None
        book_id: int | None = None
        book = _book_by_isbn(db, item.isbn)
        if item.condition == "poor":
            decision, reason = "declined", "poor_condition"
        elif item.publication_year < now.year - TOO_OLD_YEARS:
            decision, reason = "declined", "too_old"
        elif book is not None and _copies_at_branch(db, book.id, donation.branch_id) >= DUPLICATE_COPIES:
            decision, reason, book_id = "declined", "duplicate", book.id
        elif book is not None:
            decision, book_id = "accepted", book.id
        result.append(SuggestionOut(item_id=item.id, decision=decision, decline_reason=reason, book_id=book_id))
    return SuggestionsOut(items=result)


def review(
    db: Session, now: datetime.datetime, actor: User, donation: Donation, entries: list[ReviewItemIn]
) -> Donation:
    """LIB-DON-16 to LIB-DON-18."""
    items = {i.id: i for i in offers.items_of(db, donation.id)}
    problems: list[dict[str, str]] = []
    seen: set[int] = set()
    for index, entry in enumerate(entries):
        field = f"items.{index}"
        item = items.get(entry.item_id)
        if item is None:
            problems.append({"field": f"{field}.item_id", "problem": "not an item of this donation"})
            continue
        if entry.item_id in seen:
            problems.append({"field": f"{field}.item_id", "problem": "item decided more than once"})
        seen.add(entry.item_id)
        if entry.decision == "accepted":
            assert entry.book_id is not None and entry.accepted_quantity is not None
            if entry.accepted_quantity > item.quantity:
                problems.append(
                    {"field": f"{field}.accepted_quantity", "problem": "accepted_quantity must not exceed quantity"}
                )
            if db.get(Book, entry.book_id) is None:
                problems.append({"field": f"{field}.book_id", "problem": f"book {entry.book_id} does not exist"})
    if not problems and seen != set(items):
        problems.append({"field": "items", "problem": "every item of the donation must be decided"})
    if problems:
        raise ValidationFailed(problems)

    if donation.status != "offered":
        raise offers.invalid_status(donation, "review")
    for entry in entries:
        item = items[entry.item_id]
        if entry.decision != "accepted" or item.isbn is None:
            continue
        book = db.get(Book, entry.book_id)
        assert book is not None
        if book.isbn != item.isbn:
            raise Conflict(
                f"The ISBN of item {item.id} differs from the ISBN of book {book.id}",
                code="ISBN_MISMATCH",
                details={"item_id": item.id},
            )
    branch = db.get(Branch, donation.branch_id)
    assert branch is not None
    if not branch.is_active:
        raise Conflict(
            f"Branch {branch.code} is inactive",
            code="BRANCH_INACTIVE",
            details={"field": "branch_id", "id": branch.id},
        )

    for entry in entries:
        item = items[entry.item_id]
        item.decision = entry.decision
        if entry.decision == "accepted":
            item.book_id = entry.book_id
            item.accepted_quantity = entry.accepted_quantity
            item.estimated_value = entry.estimated_value
            item.decline_reason = None
        else:
            item.decline_reason = entry.decline_reason
    accepted = sum(1 for i in items.values() if i.decision == "accepted")
    declined = len(items) - accepted
    donation.reviewed_at = now
    if accepted == 0:
        donation.status = "rejected"
    else:
        donation.status = "accepted"
        donation.expected_by = now.date() + datetime.timedelta(days=EXPECTED_DAYS)
    record(
        db,
        at=now,
        event="donation_reviewed",
        actor_user_id=actor.id,
        entity_type="donation",
        entity_id=donation.id,
        details={
            "status": donation.status,
            "accepted": accepted,
            "declined": declined,
            "expected_by": donation.expected_by.isoformat() if donation.expected_by is not None else None,
        },
    )
    donor = db.get(Donor, donation.donor_id)
    if donor is not None and donor.member_id is not None:
        notify_donation(
            db,
            now,
            donor.member_id,
            "donation_reviewed",
            f"Your donation {donation.id} was reviewed: {accepted} item(s) accepted, {declined} item(s) declined.",
            donation_id=donation.id,
        )
    return donation

