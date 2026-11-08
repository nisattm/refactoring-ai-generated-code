"""Late fees and overdue state of incoming requests (LIB-ILL-15, LIB-ILL-18, LIB-ILL-19).

Kept free of imports from other business modules so that module 7 (fines) can use it.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.core.money import ZERO, quantize
from lms.ill.models import IllRequest


def is_overdue(request: IllRequest, today: datetime.date) -> bool:
    return request.status == "on_loan" and request.due_on is not None and today > request.due_on


def late_fee_on(request: IllRequest, returned_on: datetime.date) -> Decimal:
    """LIB-ILL-18: days late × the stored daily fee, at most the replacement cost; zero when not late."""
    if request.due_on is None or returned_on <= request.due_on:
        return ZERO
    days = (returned_on - request.due_on).days
    fee = quantize(days * (request.stored_daily_late_fee or ZERO))
    if request.replacement_cost is not None:
        fee = min(fee, request.replacement_cost)
    return fee


def overdue_requests(db: Session, member_id: int, today: datetime.date) -> list[IllRequest]:
    stmt = (
        sa.select(IllRequest)
        .where(IllRequest.member_id == member_id, IllRequest.status == "on_loan", IllRequest.due_on < today)
        .order_by(IllRequest.id)
    )
    return list(db.scalars(stmt))


def accrued_ill_late_fees(db: Session, member_id: int, today: datetime.date) -> Decimal:
    """Sum of the late fees the member's overdue incoming requests would get if returned today (LIB-ILL-19)."""
    return sum((late_fee_on(r, today) for r in overdue_requests(db, member_id, today)), ZERO)


def count_overdue(db: Session, member_id: int, today: datetime.date) -> int:
    stmt = sa.select(sa.func.count()).select_from(IllRequest).where(
        IllRequest.member_id == member_id, IllRequest.status == "on_loan", IllRequest.due_on < today
    )
    return db.scalar(stmt) or 0
