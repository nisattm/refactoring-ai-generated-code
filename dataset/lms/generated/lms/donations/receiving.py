"""Receiving, receipts, expiry and recognition levels (LIB-DON-19 to LIB-DON-33)."""

from __future__ import annotations

import datetime
from collections.abc import Container

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.branches.models import Branch
from lms.catalog.models import Book, Copy
from lms.catalog.service import add_copy
from lms.core.errors import Conflict, NotFound
from lms.core.money import ZERO, format_amount
from lms.donations import offers, usage
from lms.donations.models import Donation, Donor, Receiving
from lms.donations.rules import LEVEL_RANK, level_of
from lms.donations.schemas import (
    ReceiptDonorOut,
    ReceiptLineOut,
    ReceiptOut,
    ReceiveItemIn,
)
from lms.notifications.service import notify_donation


def _next_receipt_no(db: Session, year: int) -> str:
    prefix = f"DN-{year}-"
    count = db.scalar(sa.select(sa.func.count()).select_from(Donation).where(Donation.receipt_no.like(f"{prefix}%")))
    return f"{prefix}{(count or 0) + 1:04d}"


def receive(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    donation: Donation,
    entries: list[ReceiveItemIn],
) -> Donation:
    """LIB-DON-19 to LIB-DON-22, LIB-DON-28, LIB-DON-33."""
    items = {i.id: i for i in offers.items_of(db, donation.id)}
    for index, entry in enumerate(entries):
        if entry.item_id not in items:
            raise NotFound(
                f"item_id {entry.item_id} is not an item of this donation",
                details={"field": f"items.{index}.item_id", "id": entry.item_id},
            )
    branch = db.get(Branch, donation.branch_id)
    assert branch is not None
    if not branch.is_active:  # LIB-BR-04
        raise Conflict(
            f"Branch {branch.code} is inactive",
            code="BRANCH_INACTIVE",
            details={"field": "branch_id", "id": branch.id},
        )
    if donation.status not in ("accepted", "partially_received"):
        raise offers.invalid_status(donation, "receive")
    for entry in entries:
        item = items[entry.item_id]
        if item.decision != "accepted":
            raise Conflict(f"Item {item.id} is not accepted", code="ITEM_NOT_ACCEPTED", details={"item_id": item.id})
    for entry in entries:
        item = items[entry.item_id]
        assert item.accepted_quantity is not None
        if item.received_quantity + len(entry.barcodes) > item.accepted_quantity:
            raise Conflict(
                f"Item {item.id} would receive more than the accepted quantity",
                code="RECEIVE_EXCEEDS_ACCEPTED",
                details={
                    "item_id": item.id,
                    "accepted_quantity": item.accepted_quantity,
                    "received_quantity": item.received_quantity,
                    "requested": len(entry.barcodes),
                },
            )
    barcodes = [b for entry in entries for b in entry.barcodes]
    if len(set(barcodes)) != len(barcodes):
        raise Conflict("A barcode is repeated in the request", details={"field": "barcodes"})
    stored = db.scalars(sa.select(Copy.barcode).where(Copy.barcode.in_(barcodes))).first()
    if stored is not None:
        raise Conflict("A copy with this barcode already exists", details={"field": "barcodes", "value": stored})

    donor = db.get(Donor, donation.donor_id)
    assert donor is not None
    today = now.date()
    level_before = level_of(usage.donor_year_value(db, donor.id, today.year))
    copies_total = 0
    value_total = ZERO
    created: list[dict[str, object]] = []
    for entry in entries:
        item = items[entry.item_id]
        assert item.estimated_value is not None
        book = db.get(Book, item.book_id)
        assert book is not None
        for barcode in entry.barcodes:
            copy = add_copy(
                db,
                now,
                actor,
                book,
                barcode=barcode,
                home_branch_id=donation.branch_id,
                price=item.estimated_value,
                acquired_on=today,
                shelf_location=None,
                holidays=holidays,
                donation_id=donation.id,
            )
            created.append({"item_id": item.id, "copy_id": copy.id, "barcode": barcode})
        count = len(entry.barcodes)
        value = item.estimated_value * count
        item.received_quantity += count
        db.add(Receiving(donation_id=donation.id, item_id=item.id, copies=count, value=value, received_on=today))
        copies_total += count
        value_total += value
    db.flush()

    donation.received_at = now
    first_receiving = donation.receipt_no is None
    if first_receiving:
        donation.receipt_no = _next_receipt_no(db, today.year)
    old = donation.status
    done = all(i.received_quantity == i.accepted_quantity for i in items.values() if i.decision == "accepted")
    donation.status = "received" if done else "partially_received"
    record(
        db,
        at=now,
        event="donation_received",
        actor_user_id=actor.id,
        entity_type="donation",
        entity_id=donation.id,
        details={
            "copies": created,
            "value": format_amount(value_total),
            "status": {"old": old, "new": donation.status},
            "receipt_no": donation.receipt_no,
        },
    )
    if donor.member_id is not None:
        notify_donation(
            db,
            now,
            donor.member_id,
            "donation_received",
            f"Your donation {donation.id}: {copies_total} copy(ies) received. Thank you!",
            donation_id=donation.id,
        )
        level_after = level_of(usage.donor_year_value(db, donor.id, today.year))
        if LEVEL_RANK[level_after] > LEVEL_RANK[level_before]:
            notify_donation(
                db,
                now,
                donor.member_id,
                "donor_level_reached",
                f"Thank you! You reached the {level_after} donor level for {today.year}.",
                donation_id=donation.id,
            )
    return donation


def receipt(db: Session, donation: Donation) -> ReceiptOut:
    """LIB-DON-29."""
    receivings = list(
        db.scalars(sa.select(Receiving).where(Receiving.donation_id == donation.id).order_by(Receiving.id))
    )
    if not receivings:
        raise Conflict(
            "The donation has no received copies", code="RECEIPT_NOT_AVAILABLE", details={"id": donation.id}
        )
    donor = db.get(Donor, donation.donor_id)
    assert donor is not None
    lines: list[ReceiptLineOut] = []
    for item in offers.items_of(db, donation.id):
        mine = [r for r in receivings if r.item_id == item.id]
        if not mine:
            continue
        assert item.estimated_value is not None
        lines.append(
            ReceiptLineOut(
                item_id=item.id,
                title=item.title,
                copies=sum(r.copies for r in mine),
                value_per_copy=format_amount(item.estimated_value),
                value=format_amount(sum((r.value for r in mine), ZERO)),
            )
        )
    days = [r.received_on for r in receivings]
    return ReceiptOut(
        receipt_no=donation.receipt_no,
        donor=ReceiptDonorOut(id=donor.id, name=donor.name, kind=donor.kind),
        branch_id=donation.branch_id,
        first_received_on=min(days).isoformat(),
        last_received_on=max(days).isoformat(),
        lines=lines,
        total_copies=sum(r.copies for r in receivings),
        total_value=format_amount(sum((r.value for r in receivings), ZERO)),
    )


def process(db: Session, now: datetime.datetime, actor: User) -> int:
    """LIB-DON-27."""
    late = db.scalars(
        sa.select(Donation)
        .where(Donation.status.in_(usage.PENDING_RECEIVE_STATUSES), Donation.expected_by < now.date())
        .order_by(Donation.id)
    ).all()
    for donation in late:
        donation.status = "expired"
        donor = db.get(Donor, donation.donor_id)
        if donor is not None and donor.member_id is not None:
            notify_donation(
                db,
                now,
                donor.member_id,
                "donation_expired",
                f"Your donation {donation.id} expired because it was not received by "
                f"{donation.expected_by.isoformat() if donation.expected_by is not None else 'the expected date'}.",
                donation_id=donation.id,
            )
    record(
        db,
        at=now,
        event="donations_processed",
        actor_user_id=actor.id,
        entity_type="donation",
        entity_id=None,
        details={"expired": len(late), "donation_ids": [d.id for d in late]},
    )
    return len(late)
