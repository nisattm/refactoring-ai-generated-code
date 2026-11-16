"""Hooks and figures of module 28 used by other modules (members, branches).

Imports only models, schemas and the audit log, so that the other modules can use it without import cycles."""

from __future__ import annotations

import datetime
import re

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.access.models import Card, DayPass, Visit
from lms.access.schemas import AccessSummaryOut
from lms.core.clock import LOCAL_TZ

_CARD_NO = re.compile(r"LC([0-9]{8})")


def find_card(db: Session, card_no: str) -> Card | None:
    """The card with this number, or ``None`` for an unknown or malformed number."""
    match = _CARD_NO.fullmatch(card_no)
    if match is None:
        return None
    return db.get(Card, int(match.group(1)))


def active_card(db: Session, member_id: int) -> Card | None:
    stmt = sa.select(Card).where(Card.member_id == member_id, Card.status == "active").order_by(Card.id.desc())
    return db.scalar(stmt.limit(1))


def latest_card(db: Session, member_id: int) -> Card | None:
    stmt = sa.select(Card).where(Card.member_id == member_id).order_by(Card.id.desc())
    return db.scalar(stmt.limit(1))


def open_visit_of_member(db: Session, member_id: int) -> Visit | None:
    stmt = sa.select(Visit).where(Visit.member_id == member_id, Visit.left_at.is_(None)).order_by(Visit.id.desc())
    return db.scalar(stmt.limit(1))


def on_membership_renewed(db: Session, member_id: int, valid_until: datetime.date) -> None:
    """LIB-ACC-07: the active card follows the renewal."""
    card = active_card(db, member_id)
    if card is not None:
        card.expires_on = valid_until


def on_member_deactivated(db: Session, now: datetime.datetime, member_id: int) -> None:
    """LIB-ACC-36: the active card is revoked and an open visit is ended."""
    card = active_card(db, member_id)
    if card is not None:
        card.status = "revoked"
        card.ended_on = now.date()
    visit = open_visit_of_member(db, member_id)
    if visit is not None:
        visit.left_at = now
        visit.closed_by = "staff"
    db.flush()


def branch_in_use(db: Session, branch_id: int, today: datetime.date) -> bool:
    """LIB-ACC-40: someone is inside or an ``unused`` day pass for today or later exists."""
    if db.scalar(sa.select(Visit.id).where(Visit.branch_id == branch_id, Visit.left_at.is_(None)).limit(1)):
        return True
    unused = sa.select(DayPass.id).where(
        DayPass.branch_id == branch_id, DayPass.status == "unused", DayPass.valid_on >= today
    )
    return db.scalar(unused.limit(1)) is not None


def member_summary(db: Session, now: datetime.datetime, member_id: int) -> AccessSummaryOut:
    """LIB-ACC-38."""
    card = latest_card(db, member_id)
    visit = open_visit_of_member(db, member_id)
    first = now.date().replace(day=1)
    following = (first + datetime.timedelta(days=32)).replace(day=1)
    start = datetime.datetime.combine(first, datetime.time.min, LOCAL_TZ)
    end = datetime.datetime.combine(following, datetime.time.min, LOCAL_TZ)
    visits = db.scalar(
        sa.select(sa.func.count())
        .select_from(Visit)
        .where(Visit.member_id == member_id, Visit.entered_at >= start, Visit.entered_at < end)
    )
    return AccessSummaryOut(
        card_no=card.card_no if card is not None else None,
        card_status=card.status if card is not None else None,
        inside_branch_id=visit.branch_id if visit is not None else None,
        visits_this_month=visits or 0,
    )
