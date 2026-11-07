"""Processing (LIB-DIG-34, LIB-DIG-35) and member deactivation (LIB-DIG-37)."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.auth.models import User
from lms.core.timeutil import format_datetime
from lms.digital import state
from lms.digital.lending import end_loan
from lms.digital.models import DigitalHold, DigitalLoan, DigitalResource, DigitalSession
from lms.digital.queue import cancel_hold, move_queue
from lms.digital.rules import DUE_SOON_WINDOW
from lms.notifications.service import digital_due_soon_sent, notify_digital


def _title(db: Session, resource_id: int) -> str:
    return state.get_resource_or_404(db, resource_id).title


def process(db: Session, now: datetime.datetime, actor: User) -> tuple[int, int, int, int]:
    """LIB-DIG-35: returns ``(expired_loans, expired_holds, holds_ready, due_soon_notices)``."""
    finished = db.scalars(
        sa.select(DigitalLoan)
        .where(DigitalLoan.status == "open", DigitalLoan.due_at <= now)
        .order_by(DigitalLoan.due_at, DigitalLoan.id)
    )
    expired_loans = 0
    for loan in list(finished):
        loan.status = "expired"
        loan.ended_at = loan.due_at
        state.audit(
            db, now, actor.id, "digital_loan_expired", "digital_loan", loan.id,
            resource_id=loan.resource_id, member_id=loan.member_id,
        )
        notify_digital(
            db,
            now,
            loan.member_id,
            "digital_loan_expired",
            f'Your loan of "{_title(db, loan.resource_id)}" ended on {format_datetime(loan.due_at)}.',
            digital_loan_id=loan.id,
        )
        expired_loans += 1

    lapsed = db.scalars(
        sa.select(DigitalHold)
        .where(DigitalHold.status == "ready", DigitalHold.ready_until < now)
        .order_by(DigitalHold.ready_until, DigitalHold.id)
    )
    expired_holds = 0
    for hold in list(lapsed):
        hold.status = "expired"
        hold.closed_at = now
        state.audit(
            db, now, actor.id, "digital_hold_expired", "digital_hold", hold.id,
            resource_id=hold.resource_id, member_id=hold.member_id,
        )
        notify_digital(
            db,
            now,
            hold.member_id,
            "digital_hold_expired",
            f'Your hold on "{_title(db, hold.resource_id)}" expired because the e-book was not borrowed in time.',
            digital_hold_id=hold.id,
        )
        expired_holds += 1

    holds_ready = 0
    for resource in list(db.scalars(sa.select(DigitalResource).where(DigitalResource.is_active.is_(True)).order_by(DigitalResource.id))):
        holds_ready += move_queue(db, now, actor.id, resource)

    due_soon = 0
    soon = db.scalars(
        sa.select(DigitalLoan)
        .where(DigitalLoan.status == "open", DigitalLoan.due_at > now, DigitalLoan.due_at <= now + DUE_SOON_WINDOW)
        .order_by(DigitalLoan.due_at, DigitalLoan.id)
    )
    for loan in list(soon):
        if digital_due_soon_sent(db, loan.id):
            continue
        notify_digital(
            db,
            now,
            loan.member_id,
            "digital_loan_due_soon",
            f'Your loan of "{_title(db, loan.resource_id)}" is due at {format_datetime(loan.due_at)}.',
            digital_loan_id=loan.id,
        )
        due_soon += 1

    state.audit(
        db, now, actor.id, "digital_processed", "digital", None,
        expired_loans=expired_loans, expired_holds=expired_holds, holds_ready=holds_ready, due_soon_notices=due_soon,
    )
    return expired_loans, expired_holds, holds_ready, due_soon


def on_member_deactivated(db: Session, now: datetime.datetime, actor_id: int | None, member_id: int) -> None:
    """LIB-DIG-37."""
    affected: set[int] = set()
    loans = db.scalars(
        sa.select(DigitalLoan)
        .where(DigitalLoan.member_id == member_id, DigitalLoan.status == "open", DigitalLoan.due_at > now)
        .order_by(DigitalLoan.id)
    )
    for loan in list(loans):
        end_loan(db, now, actor_id, loan)
        affected.add(loan.resource_id)
    holds = db.scalars(
        sa.select(DigitalHold)
        .where(DigitalHold.member_id == member_id, DigitalHold.status.in_(("waiting", "ready")))
        .order_by(DigitalHold.created_at, DigitalHold.id)
    )
    for hold in list(holds):
        cancel_hold(db, now, actor_id, hold, "member_deactivated")
        affected.add(hold.resource_id)
    for session in db.scalars(
        sa.select(DigitalSession).where(
            DigitalSession.member_id == member_id, DigitalSession.closed_at.is_(None), DigitalSession.expires_at > now
        )
    ):
        session.closed_at = now
    for resource_id in sorted(affected):
        move_queue(db, now, actor_id, state.get_resource_or_404(db, resource_id))
