"""Light-weight lookups of module 22 used by other modules (members, branches, purchasing, catalog) and by
module 22 itself.

Imports only models, rules and the audit log, so that the other modules can use it without import cycles."""

from __future__ import annotations

import datetime
from collections import defaultdict
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.core.money import ZERO, format_amount
from lms.donations.models import OPEN_STATUSES, Donation, DonationItem, Donor, Receiving
from lms.donations.rules import level_of
from lms.donations.summary import DonationSummaryOut

PENDING_RECEIVE_STATUSES = ("accepted", "partially_received")


# --- values and levels ----------------------------------------------------------------------


def year_values(db: Session, year: int, donor_ids: list[int] | None = None) -> dict[int, Decimal]:
    """LIB-DON-30: the value per donor of the receivings with ``received_on`` in ``year``."""
    stmt = (
        sa.select(Donation.donor_id, Receiving.value)
        .join(Donation, Donation.id == Receiving.donation_id)
        .where(Receiving.received_on >= datetime.date(year, 1, 1), Receiving.received_on <= datetime.date(year, 12, 31))
    )
    if donor_ids is not None:
        stmt = stmt.where(Donation.donor_id.in_(donor_ids))
    totals: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for donor_id, value in db.execute(stmt):
        totals[donor_id] += value
    return dict(totals)


def donor_year_value(db: Session, donor_id: int, year: int) -> Decimal:
    return year_values(db, year, [donor_id]).get(donor_id, ZERO)


def donor_copies_received(db: Session, donor_id: int) -> int:
    stmt = (
        sa.select(sa.func.coalesce(sa.func.sum(Receiving.copies), 0))
        .join(Donation, Donation.id == Receiving.donation_id)
        .where(Donation.donor_id == donor_id)
    )
    return int(db.scalar(stmt) or 0)


def open_donation_ids(db: Session, donor_id: int) -> list[int]:
    stmt = (
        sa.select(Donation.id).where(Donation.donor_id == donor_id, Donation.status.in_(OPEN_STATUSES)).order_by(Donation.id)
    )
    return list(db.scalars(stmt))


def donor_of_member(db: Session, member_id: int) -> Donor | None:
    return db.scalar(sa.select(Donor).where(Donor.member_id == member_id))


# --- effects on other modules ---------------------------------------------------------------


def branch_has_open_donations(db: Session, branch_id: int) -> bool:
    """LIB-DON-36."""
    stmt = sa.select(Donation.id).where(Donation.branch_id == branch_id, Donation.status.in_(OPEN_STATUSES)).limit(1)
    return db.scalar(stmt) is not None


def book_has_items(db: Session, book_id: int) -> bool:
    """LIB-DON-39."""
    return db.scalar(sa.select(DonationItem.id).where(DonationItem.book_id == book_id).limit(1)) is not None


def pending_book_ids(db: Session, branch_id: int, book_ids: list[int]) -> list[int]:
    """LIB-DON-35: the books (ascending) with an accepted item that is not fully received in an ``accepted`` or
    ``partially_received`` donation for the branch."""
    if not book_ids:
        return []
    stmt = (
        sa.select(DonationItem.book_id)
        .join(Donation, Donation.id == DonationItem.donation_id)
        .where(
            Donation.branch_id == branch_id,
            Donation.status.in_(PENDING_RECEIVE_STATUSES),
            DonationItem.decision == "accepted",
            DonationItem.book_id.in_(book_ids),
            DonationItem.received_quantity < DonationItem.accepted_quantity,
        )
        .distinct()
        .order_by(DonationItem.book_id)
    )
    return list(db.scalars(stmt))


def on_member_deactivated(db: Session, now: datetime.datetime, actor_user_id: int | None, member_id: int) -> None:
    """LIB-DON-37: the ``offered`` donations of the member's donor are cancelled; nobody is notified."""
    donor = donor_of_member(db, member_id)
    if donor is None:
        return
    offered = db.scalars(
        sa.select(Donation).where(Donation.donor_id == donor.id, Donation.status == "offered").order_by(Donation.id)
    )
    for donation in offered:
        donation.status = "cancelled"
        donation.cancel_reason = "member_deactivated"
        record(
            db,
            at=now,
            event="donation_cancelled",
            actor_user_id=actor_user_id,
            entity_type="donation",
            entity_id=donation.id,
            details={"cancel_reason": "member_deactivated"},
        )


def member_summary(db: Session, now: datetime.datetime, member_id: int) -> DonationSummaryOut:
    """LIB-DON-38."""
    donor = donor_of_member(db, member_id)
    if donor is None:
        return DonationSummaryOut(open=0, copies_received=0, value_this_year="0.00", level="none")
    value = donor_year_value(db, donor.id, now.year)
    return DonationSummaryOut(
        open=len(open_donation_ids(db, donor.id)),
        copies_received=donor_copies_received(db, donor.id),
        value_this_year=format_amount(value),
        level=level_of(value),
    )
