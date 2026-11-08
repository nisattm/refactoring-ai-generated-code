"""The interlibrary figures of the member summary (LIB-ILL-34) and the activity report (LIB-ILL-38)."""

from __future__ import annotations

import datetime
from collections import defaultdict
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.core.money import ZERO, format_amount
from lms.ill.accrual import count_overdue
from lms.ill.models import OPEN_STATUSES, IllOutgoing, IllPartner, IllRequest, IllRequestAction
from lms.ill.schemas import IllActivityOut, IllSummaryOut


def member_summary(db: Session, today: datetime.date, member_id: int) -> IllSummaryOut:
    def count(*statuses: str) -> int:
        stmt = sa.select(sa.func.count()).select_from(IllRequest).where(
            IllRequest.member_id == member_id, IllRequest.status.in_(statuses)
        )
        return db.scalar(stmt) or 0

    return IllSummaryOut(
        open_requests=count(*OPEN_STATUSES),
        on_loan=count("on_loan"),
        overdue=count_overdue(db, member_id, today),
    )


def ill_activity(db: Session, first: datetime.date, last: datetime.date) -> list[IllActivityOut]:
    """One item per partner, ordered by code."""

    def in_range(day: datetime.date | None) -> bool:
        return day is not None and first <= day <= last

    counts: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    amounts: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for action in db.scalars(sa.select(IllRequestAction)):
        if in_range(action.on_date):
            counts[action.partner_id][action.action] += 1
    for request in db.scalars(sa.select(IllRequest).where(IllRequest.partner_id.is_not(None))):
        assert request.partner_id is not None
        c = counts[request.partner_id]
        if in_range(request.received_on):
            c["received"] += 1
        if (
            in_range(request.returned_on)
            and request.due_on is not None
            and request.returned_on is not None
            and request.returned_on > request.due_on
        ):
            c["late_returns"] += 1
    for outgoing in db.scalars(sa.select(IllOutgoing)):
        c = counts[outgoing.partner_id]
        if in_range(outgoing.shipped_on):
            c["outgoing_shipped"] += 1
        if in_range(outgoing.returned_on):
            c["outgoing_returned"] += 1
        if outgoing.status == "lost" and in_range(outgoing.lost_on):
            c["outgoing_lost"] += 1
            amounts[outgoing.partner_id] += outgoing.amount_due or ZERO

    return [
        IllActivityOut(
            partner_id=p.id,
            partner_code=p.code,
            sent=counts[p.id]["sent"],
            rejected=counts[p.id]["rejected"],
            received=counts[p.id]["received"],
            late_returns=counts[p.id]["late_returns"],
            outgoing_shipped=counts[p.id]["outgoing_shipped"],
            outgoing_returned=counts[p.id]["outgoing_returned"],
            outgoing_lost=counts[p.id]["outgoing_lost"],
            amount_due=format_amount(amounts[p.id]),
        )
        for p in db.scalars(sa.select(IllPartner).order_by(IllPartner.code, IllPartner.id))
    ]
