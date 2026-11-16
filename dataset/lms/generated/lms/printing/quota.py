"""Free pages, packs, daily pages and the payment of a job (LIB-PRT-08, LIB-PRT-17, LIB-PRT-29, LIB-PRT-30).

Imports only models and the member model, so that other modules can use it without import cycles."""

from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.core.clock import LOCAL_TZ
from lms.core.money import ZERO, quantize
from lms.fines.models import Fee
from lms.printing.models import PrintJob, PrintPack
from lms.printing.rules import PRICE_BW, PRICE_COLOR, free_pages_of


def month_bounds(first: datetime.date) -> tuple[datetime.datetime, datetime.datetime]:
    """The local month starting on ``first`` (its first day) as a half-open interval."""
    following = (first + datetime.timedelta(days=32)).replace(day=1)
    return (
        datetime.datetime.combine(first, datetime.time.min, LOCAL_TZ),
        datetime.datetime.combine(following, datetime.time.min, LOCAL_TZ),
    )


def day_bounds(day: datetime.date) -> tuple[datetime.datetime, datetime.datetime]:
    start = datetime.datetime.combine(day, datetime.time.min, LOCAL_TZ)
    return start, start + datetime.timedelta(days=1)


def _released_between(
    db: Session, member_id: int, start: datetime.datetime, end: datetime.datetime, *columns: sa.ColumnElement[int]
) -> sa.Select:
    return sa.select(*columns).where(
        PrintJob.member_id == member_id,
        PrintJob.status == "printed",
        PrintJob.released_at >= start,
        PrintJob.released_at < end,
    )


def free_pages_used(db: Session, member_id: int, first: datetime.date) -> int:
    """Free pages taken by the printed jobs released in the month starting on ``first``."""
    start, end = month_bounds(first)
    stmt = _released_between(db, member_id, start, end, sa.func.coalesce(sa.func.sum(PrintJob.free_pages), 0))
    return int(db.scalar(stmt) or 0)


def free_pages_left(db: Session, member_id: int, membership_type: str, first: datetime.date) -> int:
    """LIB-PRT-30: never below 0."""
    return max(0, free_pages_of(membership_type) - free_pages_used(db, member_id, first))


def pages_printed(db: Session, member_id: int, start: datetime.datetime, end: datetime.datetime) -> int:
    stmt = _released_between(db, member_id, start, end, sa.func.coalesce(sa.func.sum(PrintJob.pages * PrintJob.copies), 0))
    return int(db.scalar(stmt) or 0)


def queued_pages(db: Session, member_id: int) -> int:
    stmt = sa.select(sa.func.coalesce(sa.func.sum(PrintJob.pages * PrintJob.copies), 0)).where(
        PrintJob.member_id == member_id, PrintJob.status == "queued"
    )
    return int(db.scalar(stmt) or 0)


def queued_count(db: Session, member_id: int) -> int:
    stmt = sa.select(sa.func.count()).select_from(PrintJob).where(PrintJob.member_id == member_id, PrintJob.status == "queued")
    return int(db.scalar(stmt) or 0)


def packs_with_pages(db: Session, member_id: int) -> list[PrintPack]:
    """Packs with pages left, in the order they are used: ``bought_on``, then ``id``."""
    stmt = (
        sa.select(PrintPack)
        .where(PrintPack.member_id == member_id, PrintPack.pages_left > 0)
        .order_by(PrintPack.bought_on, PrintPack.id)
    )
    return list(db.scalars(stmt))


def pack_pages_left(db: Session, member_id: int) -> int:
    stmt = sa.select(sa.func.coalesce(sa.func.sum(PrintPack.pages_left), 0)).where(PrintPack.member_id == member_id)
    return int(db.scalar(stmt) or 0)


def amount_charged(db: Session, member_id: int, first: datetime.date) -> Decimal:
    """Printing fees of the printed jobs released in the month."""
    start, end = month_bounds(first)
    stmt = (
        sa.select(Fee.amount)
        .join(PrintJob, PrintJob.fee_id == Fee.id)
        .where(
            PrintJob.member_id == member_id,
            PrintJob.status == "printed",
            PrintJob.released_at >= start,
            PrintJob.released_at < end,
        )
    )
    return sum(db.scalars(stmt), ZERO)


@dataclasses.dataclass(frozen=True)
class Payment:
    """How the pages of a job are paid (LIB-PRT-17)."""

    free_pages: int
    pack_pages: int
    charged_pages: int
    amount: Decimal
    packs: tuple[tuple[int, int], ...]  # (pack id, pages taken)


def plan_payment(
    db: Session, member_id: int, membership_type: str, first: datetime.date, pages: int, copies: int, color: bool
) -> Payment:
    """LIB-PRT-17: black-and-white pages are paid from the free pages left, then from the packs, then charged;
    color pages are always charged."""
    printed = pages * copies
    if color:
        return Payment(0, 0, printed, quantize(PRICE_COLOR * printed), ())
    free = min(printed, free_pages_left(db, member_id, membership_type, first))
    rest = printed - free
    taken: list[tuple[int, int]] = []
    for pack in packs_with_pages(db, member_id):
        if rest == 0:
            break
        part = min(rest, pack.pages_left)
        taken.append((pack.id, part))
        rest -= part
    return Payment(free, printed - free - rest, rest, quantize(PRICE_BW * rest), tuple(taken))
