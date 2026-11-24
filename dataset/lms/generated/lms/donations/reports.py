"""Donation reports (LIB-DON-43, LIB-DON-44)."""

from __future__ import annotations

import datetime
from collections import defaultdict
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.branches.models import Branch
from lms.core.clock import LOCAL_TZ
from lms.core.money import ZERO, format_amount
from lms.donations import usage
from lms.donations.models import Donation, DonationItem, Donor, Receiving
from lms.donations.rules import level_of
from lms.donations.schemas import (
    DECLINE_REASONS,
    DeclinedOut,
    DonationReportOut,
    DonorReportOut,
)


def donation_report(db: Session, first: datetime.date, last: datetime.date) -> list[DonationReportOut]:
    """LIB-DON-43: one row per branch with a donation offered in the range, ordered by branch code."""
    start = datetime.datetime.combine(first, datetime.time.min, LOCAL_TZ)
    end = datetime.datetime.combine(last + datetime.timedelta(days=1), datetime.time.min, LOCAL_TZ)
    rows = db.execute(
        sa.select(Donation.id, Donation.branch_id, Branch.code)
        .join(Branch, Branch.id == Donation.branch_id)
        .where(Donation.offered_at >= start, Donation.offered_at < end)
    ).all()
    codes = {branch_id: code for _, branch_id, code in rows}
    branch_of = {donation_id: branch_id for donation_id, branch_id, _ in rows}
    donations: dict[int, int] = defaultdict(int)
    offered: dict[int, int] = defaultdict(int)
    accepted: dict[int, int] = defaultdict(int)
    received: dict[int, int] = defaultdict(int)
    value: dict[int, Decimal] = defaultdict(lambda: ZERO)
    declined: dict[int, dict[str, int]] = defaultdict(lambda: dict.fromkeys(DECLINE_REASONS, 0))
    for donation_id, branch_id in branch_of.items():
        donations[branch_id] += 1
    ids = list(branch_of)
    for item in db.scalars(sa.select(DonationItem).where(DonationItem.donation_id.in_(ids))):
        branch_id = branch_of[item.donation_id]
        offered[branch_id] += item.quantity
        received[branch_id] += item.received_quantity
        if item.decision == "accepted":
            accepted[branch_id] += item.accepted_quantity or 0
        elif item.decision == "declined" and item.decline_reason in DECLINE_REASONS:
            declined[branch_id][item.decline_reason] += 1
    for donation_id, amount in db.execute(
        sa.select(Receiving.donation_id, Receiving.value).where(Receiving.donation_id.in_(ids))
    ):
        value[branch_of[donation_id]] += amount
    return [
        DonationReportOut(
            branch_id=branch_id,
            donations=donations[branch_id],
            copies_offered=offered[branch_id],
            copies_accepted=accepted[branch_id],
            copies_received=received[branch_id],
            value_received=format_amount(value[branch_id]),
            declined=DeclinedOut(**declined[branch_id]),
        )
        for branch_id in sorted(codes, key=lambda b: (codes[b], b))
    ]


def donor_report(db: Session, year: int) -> list[DonorReportOut]:
    """LIB-DON-44: the donors with a value in the year, by value descending, then name."""
    values = usage.year_values(db, year)
    if not values:
        return []
    copies: dict[int, int] = defaultdict(int)
    for donor_id, count in db.execute(
        sa.select(Donation.donor_id, Receiving.copies)
        .join(Donation, Donation.id == Receiving.donation_id)
        .where(Receiving.received_on >= datetime.date(year, 1, 1), Receiving.received_on <= datetime.date(year, 12, 31))
    ):
        copies[donor_id] += count
    donors = db.scalars(sa.select(Donor).where(Donor.id.in_(list(values)))).all()
    donors = [d for d in donors if values[d.id] > ZERO]
    donors.sort(key=lambda d: (-values[d.id], d.name_key, d.id))
    return [
        DonorReportOut(
            donor_id=d.id,
            name=d.name,
            kind=d.kind,
            value=format_amount(values[d.id]),
            level=level_of(values[d.id]),
            copies=copies[d.id],
        )
        for d in donors
    ]
