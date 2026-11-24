"""Visits report (LIB-ACC-44, LIB-ACC-46)."""

from __future__ import annotations

import datetime
from decimal import ROUND_HALF_UP, Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.access.models import DayPass, DeniedScan, Visit
from lms.access.schemas import VisitsReportOut
from lms.branches.models import Branch
from lms.core.clock import LOCAL_TZ
from lms.core.money import ZERO, format_amount


def peak_occupancy(visits: list[Visit]) -> int:
    """The most visits open at the same time; a visit ending at ``t`` is not open at ``t``."""
    events: list[tuple[datetime.datetime, int]] = []
    for visit in visits:
        events.append((visit.entered_at, 1))
        if visit.left_at is not None:
            events.append((visit.left_at, -1))
    events.sort(key=lambda e: (e[0], e[1]))  # an end (-1) sorts before a start (+1) at the same time
    peak = current = 0
    for _, delta in events:
        current += delta
        peak = max(peak, current)
    return peak


def _mean_minutes(visits: list[Visit]) -> str | None:
    ended = [(v.left_at - v.entered_at).total_seconds() for v in visits if v.left_at is not None]
    if not ended:
        return None
    mean = (Decimal(sum(ended)) / Decimal(len(ended)) / Decimal(60)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return format(mean, "f")


def visits_report(
    db: Session, first: datetime.date, last: datetime.date, branch_id: int | None
) -> list[VisitsReportOut]:
    start = datetime.datetime.combine(first, datetime.time.min, LOCAL_TZ)
    end = datetime.datetime.combine(last + datetime.timedelta(days=1), datetime.time.min, LOCAL_TZ)
    stmt = sa.select(Visit).where(Visit.entered_at >= start, Visit.entered_at < end).order_by(Visit.id)
    if branch_id is not None:
        stmt = stmt.where(Visit.branch_id == branch_id)
    by_branch: dict[int, list[Visit]] = {}
    for visit in db.scalars(stmt):
        by_branch.setdefault(visit.branch_id, []).append(visit)
    codes = dict(db.execute(sa.select(Branch.id, Branch.code).where(Branch.id.in_(by_branch or [0]))).all())

    rows: list[VisitsReportOut] = []
    for bid in sorted(by_branch, key=lambda b: (codes[b], b)):
        visits = by_branch[bid]
        members = [v for v in visits if v.member_id is not None]
        revenue = sum(
            (
                p.price
                for p in db.scalars(
                    sa.select(DayPass).where(
                        DayPass.branch_id == bid,
                        DayPass.status.in_(("used", "unused")),
                        DayPass.sold_at >= start,
                        DayPass.sold_at < end,
                    )
                )
            ),
            ZERO,
        )
        denied = db.scalar(
            sa.select(sa.func.count())
            .select_from(DeniedScan)
            .where(DeniedScan.branch_id == bid, DeniedScan.at >= start, DeniedScan.at < end)
        )
        rows.append(
            VisitsReportOut(
                branch_id=bid,
                visits=len(visits),
                member_visits=len(members),
                unique_members=len({v.member_id for v in members}),
                pass_visits=len(visits) - len(members),
                average_minutes=_mean_minutes(visits),
                peak_occupancy=peak_occupancy(visits),
                pass_revenue=format_amount(revenue),
                denied=denied or 0,
            )
        )
    return rows
