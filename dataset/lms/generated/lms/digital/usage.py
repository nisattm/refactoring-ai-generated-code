"""Member summary (LIB-DIG-36) and usage report (LIB-DIG-39)."""

from __future__ import annotations

import datetime
from collections import defaultdict
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.core.money import ZERO, format_amount
from lms.digital import state
from lms.digital.models import DigitalHold, DigitalLicense, DigitalLoan, DigitalResource, DigitalSession
from lms.digital.schemas import DigitalSummaryOut, DigitalUsageOut


def member_summary(db: Session, now: datetime.datetime, member_id: int) -> DigitalSummaryOut:
    waiting = db.scalar(
        sa.select(sa.func.count()).select_from(DigitalHold).where(
            DigitalHold.member_id == member_id, DigitalHold.status == "waiting"
        )
    )
    ready = db.scalar(
        sa.select(sa.func.count()).select_from(DigitalHold).where(
            DigitalHold.member_id == member_id, DigitalHold.status == "ready", DigitalHold.ready_until >= now
        )
    )
    return DigitalSummaryOut(
        open_loans=state.member_active_loans(db, member_id, now), waiting_holds=waiting or 0, ready_holds=ready or 0
    )


def digital_usage(
    db: Session, first: datetime.date, last: datetime.date, *, kind: str | None = None
) -> list[DigitalUsageOut]:
    """One item per resource, ordered by title then id."""

    def in_range(moment: datetime.datetime | None) -> bool:
        return moment is not None and first <= moment.date() <= last

    counts: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for loan in db.scalars(sa.select(DigitalLoan)):
        c = counts[loan.resource_id]
        if in_range(loan.borrowed_at):
            c["loans"] += 1
        if in_range(loan.renewed_at):
            c["renewals"] += 1
    for hold in db.scalars(sa.select(DigitalHold)):
        c = counts[hold.resource_id]
        if in_range(hold.created_at):
            c["holds_placed"] += 1
        if hold.status == "expired" and in_range(hold.closed_at):
            c["holds_expired"] += 1
    for session in db.scalars(sa.select(DigitalSession)):
        if in_range(session.started_at):
            counts[session.resource_id]["sessions"] += 1
    cost: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for lic in db.scalars(sa.select(DigitalLicense)):
        if first <= lic.starts_on <= last:
            cost[lic.resource_id] += lic.cost

    stmt = sa.select(DigitalResource).order_by(DigitalResource.title_key, DigitalResource.id)
    if kind is not None:
        stmt = stmt.where(DigitalResource.kind == kind)
    items = []
    for resource in db.scalars(stmt):
        c = counts[resource.id]
        items.append(
            DigitalUsageOut(
                resource_id=resource.id,
                kind=resource.kind,
                title=resource.title,
                loans=c["loans"],
                renewals=c["renewals"],
                holds_placed=c["holds_placed"],
                holds_expired=c["holds_expired"],
                sessions=c["sessions"],
                license_cost=format_amount(cost[resource.id]),
            )
        )
    return items
