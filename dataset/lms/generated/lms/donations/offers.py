"""Offers, changes, cancellation and reading of donations (LIB-DON-08 to LIB-DON-13, LIB-DON-45)."""

from __future__ import annotations

import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.branches.models import Branch
from lms.core.clock import LOCAL_TZ
from lms.core.db import get_or_404, get_reference
from lms.core.errors import Conflict, ValidationFailed
from lms.core.money import format_amount
from lms.core.timeutil import format_datetime
from lms.donations import donors, usage
from lms.donations.models import Donation, DonationItem, Donor
from lms.donations.rules import OFFER_LIMIT
from lms.donations.schemas import DonationOut, ItemIn, ItemOut
from lms.members.models import Member

MIN_YEAR = 1450


def get_donation_or_404(db: Session, donation_id: int) -> Donation:
    return get_or_404(db, Donation, donation_id, "Donation", "donation")


def items_of(db: Session, donation_id: int) -> list[DonationItem]:
    return list(
        db.scalars(sa.select(DonationItem).where(DonationItem.donation_id == donation_id).order_by(DonationItem.id))
    )


def item_out(item: DonationItem) -> ItemOut:
    return ItemOut(
        id=item.id,
        title=item.title,
        author_text=item.author_text,
        isbn=item.isbn,
        publication_year=item.publication_year,
        condition=item.condition,
        quantity=item.quantity,
        decision=item.decision,
        decline_reason=item.decline_reason,
        book_id=item.book_id,
        accepted_quantity=item.accepted_quantity,
        estimated_value=format_amount(item.estimated_value) if item.estimated_value is not None else None,
        received_quantity=item.received_quantity,
    )


def to_out(db: Session, donation: Donation) -> DonationOut:
    items = items_of(db, donation.id)
    return DonationOut(
        id=donation.id,
        donor_id=donation.donor_id,
        branch_id=donation.branch_id,
        status=donation.status,
        note=donation.note,
        items=[item_out(i) for i in items],
        items_count=len(items),
        copies_offered=sum(i.quantity for i in items),
        offered_at=format_datetime(donation.offered_at),
        reviewed_at=format_datetime(donation.reviewed_at) if donation.reviewed_at is not None else None,
        received_at=format_datetime(donation.received_at) if donation.received_at is not None else None,
        expected_by=donation.expected_by.isoformat() if donation.expected_by is not None else None,
        cancel_reason=donation.cancel_reason,
        receipt_no=donation.receipt_no,
    )


def invalid_status(donation: Donation, action: str) -> Conflict:
    return Conflict(
        f"Donation {donation.id} has status {donation.status}: {action} is not allowed",
        code="INVALID_DONATION_STATUS",
        details={"id": donation.id, "status": donation.status},
    )


def _check_years(items: list[ItemIn], year: int) -> None:
    problems = [
        {"field": f"items.{index}.publication_year", "problem": f"publication_year must be between {MIN_YEAR} and {year}"}
        for index, item in enumerate(items)
        if item.publication_year > year
    ]
    if problems:
        raise ValidationFailed(problems)


def _add_items(db: Session, donation: Donation, items: list[ItemIn]) -> None:
    for item in items:
        db.add(
            DonationItem(
                donation_id=donation.id,
                title=item.title,
                author_text=item.author_text,
                isbn=item.isbn,
                publication_year=item.publication_year,
                condition=item.condition,
                quantity=item.quantity,
            )
        )
    db.flush()


def _item_summary(item: DonationItem | ItemIn) -> dict[str, Any]:
    return {
        "title": item.title,
        "author_text": item.author_text,
        "isbn": item.isbn,
        "publication_year": item.publication_year,
        "condition": item.condition,
        "quantity": item.quantity,
    }


def _inactive_branch(branch: Branch, field: str) -> Conflict:
    return Conflict(
        f"Branch {branch.code} is inactive", code="BRANCH_INACTIVE", details={"field": field, "id": branch.id}
    )


# --- offers ---------------------------------------------------------------------------------


def offer(
    db: Session,
    now: datetime.datetime,
    actor: User,
    *,
    member: Member | None,
    donor_id: int | None,
    branch_id: int,
    note: str,
    items: list[ItemIn],
) -> Donation:
    """LIB-DON-08 to LIB-DON-10. ``member`` is the offering member (LIB-DON-09), ``None`` for staff."""
    _check_years(items, now.year)
    branch = get_reference(db, Branch, "branch_id", branch_id)
    if member is None:
        assert donor_id is not None
        donor = get_reference(db, Donor, "donor_id", donor_id)
    else:
        donor = donors.member_donor(db, now, actor, member)
    if not branch.is_active:
        raise _inactive_branch(branch, "branch_id")
    if not donor.is_active:
        raise Conflict("The donor is inactive", code="DONOR_INACTIVE", details={"id": donor.id})
    if member is not None and member.status == "passive":
        raise Conflict("The member is passive", code="MEMBER_PASSIVE")
    if len(usage.open_donation_ids(db, donor.id)) >= OFFER_LIMIT:
        raise Conflict(
            "The donor has too many open donations", code="DONOR_OFFER_LIMIT", details={"limit": OFFER_LIMIT}
        )
    donation = Donation(donor_id=donor.id, branch_id=branch.id, status="offered", note=note, offered_at=now)
    db.add(donation)
    db.flush()
    _add_items(db, donation, items)
    record(
        db,
        at=now,
        event="donation_offered",
        actor_user_id=actor.id,
        entity_type="donation",
        entity_id=donation.id,
        details={
            "donor_id": donor.id,
            "branch_id": branch.id,
            "note": note,
            "items": [_item_summary(i) for i in items],
        },
    )
    return donation


def update_offer(
    db: Session, now: datetime.datetime, actor: User, donation: Donation, fields: dict[str, Any]
) -> Donation:
    """LIB-DON-11."""
    if "items" in fields:
        _check_years(fields["items"], now.year)
    if "branch_id" in fields:
        branch = get_reference(db, Branch, "branch_id", fields["branch_id"])
        if not branch.is_active:
            raise _inactive_branch(branch, "branch_id")
    if donation.status != "offered":
        raise invalid_status(donation, "change")
    diff: dict[str, Any] = {}
    for name in ("branch_id", "note"):
        if name in fields and fields[name] != getattr(donation, name):
            diff[name] = {"old": getattr(donation, name), "new": fields[name]}
            setattr(donation, name, fields[name])
    if "items" in fields:
        old_items = [_item_summary(i) for i in items_of(db, donation.id)]
        db.execute(sa.delete(DonationItem).where(DonationItem.donation_id == donation.id))
        _add_items(db, donation, fields["items"])
        diff["items"] = {"old": old_items, "new": [_item_summary(i) for i in fields["items"]]}
    record(
        db,
        at=now,
        event="donation_updated",
        actor_user_id=actor.id,
        entity_type="donation",
        entity_id=donation.id,
        details=diff,
    )
    return donation


def cancel(db: Session, now: datetime.datetime, actor: User, donation: Donation, *, by_member: bool) -> Donation:
    """LIB-DON-12, LIB-DON-45."""
    allowed = ("offered",) if by_member else ("offered", "accepted")
    if donation.status not in allowed:
        raise invalid_status(donation, "cancel")
    old = donation.status
    donation.status = "cancelled"
    donation.cancel_reason = "donor_request" if by_member else "staff_request"
    record(
        db,
        at=now,
        event="donation_cancelled",
        actor_user_id=actor.id,
        entity_type="donation",
        entity_id=donation.id,
        details={"status": {"old": old, "new": "cancelled"}, "cancel_reason": donation.cancel_reason},
    )
    return donation


# --- reading ----------------------------------------------------------------------------------


def _day_start(day: datetime.date) -> datetime.datetime:
    return datetime.datetime.combine(day, datetime.time.min, LOCAL_TZ)


def list_stmt(
    *,
    status: str | None = None,
    donor_id: int | None = None,
    branch_id: int | None = None,
    first: datetime.date | None = None,
    last: datetime.date | None = None,
    member_id: int | None = None,
) -> sa.Select[tuple[Donation]]:
    """LIB-DON-13: newest first."""
    stmt = sa.select(Donation).order_by(Donation.id.desc())
    if status is not None:
        stmt = stmt.where(Donation.status == status)
    if donor_id is not None:
        stmt = stmt.where(Donation.donor_id == donor_id)
    if branch_id is not None:
        stmt = stmt.where(Donation.branch_id == branch_id)
    if first is not None:
        stmt = stmt.where(Donation.offered_at >= _day_start(first))
    if last is not None and last < datetime.date.max:
        stmt = stmt.where(Donation.offered_at < _day_start(last + datetime.timedelta(days=1)))
    if member_id is not None:
        stmt = stmt.where(Donation.donor_id.in_(sa.select(Donor.id).where(Donor.member_id == member_id)))
    return stmt


def is_own(db: Session, donation: Donation, member_id: int | None) -> bool:
    if member_id is None:
        return False
    donor = db.get(Donor, donation.donor_id)
    return donor is not None and donor.member_id == member_id
