"""Cards: issue, report, expiry (LIB-ACC-01 to LIB-ACC-09)."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.access.models import Card
from lms.access.rules import (
    CARD_FEES,
    REPEAT_FEE,
    REPEAT_REPLACEMENTS,
    REPEAT_WINDOW_DAYS,
)
from lms.access.usage import active_card, find_card, latest_card
from lms.audit.service import record
from lms.auth.models import User
from lms.core.errors import Conflict, NotFound
from lms.core.money import format_amount
from lms.fines.service import create_fee
from lms.members.models import Member
from lms.notifications.service import notify_access


def get_card_or_404(db: Session, card_no: str) -> Card:
    card = find_card(db, card_no)
    if card is None:
        raise NotFound(f"Card {card_no} does not exist", details={"resource": "card", "card_no": card_no})
    return card


def issue_card(db: Session, now: datetime.datetime, actor: User, member: Member) -> Card:
    """LIB-ACC-01 to LIB-ACC-04."""
    today = now.date()
    if member.status == "passive":
        raise Conflict("The member is passive", code="MEMBER_PASSIVE")
    if today > member.valid_until:
        raise Conflict("The membership has expired", code="MEMBERSHIP_EXPIRED")
    current = active_card(db, member.id)
    if current is not None:
        raise Conflict(
            "The member already has an active card",
            code="CARD_ALREADY_ACTIVE",
            details={"card_no": current.card_no},
        )

    previous = latest_card(db, member.id)
    replaces = previous if previous is not None and previous.status in CARD_FEES else None
    card = Card(
        member_id=member.id,
        status="active",
        issued_on=today,
        expires_on=member.valid_until,
        replaces_id=replaces.id if replaces is not None else None,
    )
    db.add(card)
    db.flush()
    if replaces is not None:
        first = today - datetime.timedelta(days=REPEAT_WINDOW_DAYS - 1)
        earlier = db.scalar(
            sa.select(sa.func.count())
            .select_from(Card)
            .where(Card.member_id == member.id, Card.replaces_id.is_not(None), Card.issued_on >= first, Card.id != card.id)
        )
        amount = REPEAT_FEE if (earlier or 0) + 1 >= REPEAT_REPLACEMENTS else CARD_FEES[replaces.status]
        fee = create_fee(
            db, now, actor, member_id=member.id, loan_id=None, kind="card_replacement", amount=amount, card_id=card.id
        )
        card.fee_id = fee.id
    record(
        db,
        at=now,
        event="card_issued",
        actor_user_id=actor.id,
        entity_type="card",
        entity_id=card.id,
        details={
            "member_id": member.id,
            "card_no": card.card_no,
            "expires_on": card.expires_on.isoformat(),
            "replaces_id": card.replaces_id,
            "fee_id": card.fee_id,
            "fee_amount": format_amount(amount) if replaces is not None else None,
        },
    )
    notify_access(
        db, now, member.id, "card_issued", f"Your library card {card.card_no} was issued.", card_id=card.id
    )
    return card


def report_card(db: Session, now: datetime.datetime, actor: User, card: Card, reason: str) -> Card:
    """LIB-ACC-05."""
    if card.status != "active":
        raise Conflict("The card is not active", code="CARD_NOT_ACTIVE", details={"status": card.status})
    card.status = reason
    card.ended_on = now.date()
    record(
        db,
        at=now,
        event="card_reported",
        actor_user_id=actor.id,
        entity_type="card",
        entity_id=card.id,
        details={"member_id": card.member_id, "card_no": card.card_no, "reason": reason},
    )
    return card


def expire_cards(db: Session, today: datetime.date) -> int:
    """LIB-ACC-08: ``active`` cards with ``expires_on`` before today become ``expired``."""
    cards = db.scalars(sa.select(Card).where(Card.status == "active", Card.expires_on < today)).all()
    for card in cards:
        card.status = "expired"
        card.ended_on = today
    db.flush()
    return len(cards)
