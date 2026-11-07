"""Shared lookups, counts and checks of module 17 (25.1, LIB-DIG-16)."""

from __future__ import annotations

import datetime
from collections.abc import Container
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.core.errors import Conflict, NotFound
from lms.core.money import format_amount
from lms.digital.models import DigitalHold, DigitalLicense, DigitalLoan, DigitalResource, DigitalSession
from lms.digital.rules import DEBT_BLOCK
from lms.fines import service as fines
from lms.members.models import Member


def error(code: str, message: str, **details: Any) -> Conflict:
    return Conflict(message, code=code, details=details)


def get_resource_or_404(db: Session, resource_id: int) -> DigitalResource:
    resource = db.get(DigitalResource, resource_id)
    if resource is None:
        raise NotFound(
            f"Digital resource {resource_id} does not exist", details={"resource": "digital_resource", "id": resource_id}
        )
    return resource


def audit(
    db: Session, now: datetime.datetime, actor_id: int | None, event: str, entity_type: str, entity_id: int | None, **details: Any
) -> None:
    record(
        db, at=now, event=event, actor_user_id=actor_id, entity_type=entity_type, entity_id=entity_id, details=details
    )


# --- capacity and counts ---------------------------------------------------------------------


def licenses_of(db: Session, resource_id: int) -> list[DigitalLicense]:
    stmt = sa.select(DigitalLicense).where(DigitalLicense.resource_id == resource_id)
    return list(db.scalars(stmt.order_by(DigitalLicense.starts_on, DigitalLicense.id)))


def capacity_on(db: Session, resource_id: int, day: datetime.date) -> int:
    return sum(lic.copies for lic in licenses_of(db, resource_id) if lic.counts_on(day))


def capacity_at(db: Session, resource_id: int, now: datetime.datetime) -> int:
    return capacity_on(db, resource_id, now.date())


def _count(db: Session, stmt: sa.Select[Any]) -> int:
    return db.scalar(sa.select(sa.func.count()).select_from(stmt.subquery())) or 0


def active_loan_count(db: Session, resource_id: int, now: datetime.datetime) -> int:
    return _count(
        db,
        sa.select(DigitalLoan.id).where(
            DigitalLoan.resource_id == resource_id, DigitalLoan.status == "open", DigitalLoan.due_at > now
        ),
    )


def kept_copy_count(db: Session, resource_id: int, now: datetime.datetime) -> int:
    return _count(
        db,
        sa.select(DigitalHold.id).where(
            DigitalHold.resource_id == resource_id, DigitalHold.status == "ready", DigitalHold.ready_until >= now
        ),
    )


def waiting_count(db: Session, resource_id: int) -> int:
    return _count(db, sa.select(DigitalHold.id).where(DigitalHold.resource_id == resource_id, DigitalHold.status == "waiting"))


def free_copies(db: Session, resource_id: int, now: datetime.datetime) -> int:
    return max(
        capacity_at(db, resource_id, now)
        - active_loan_count(db, resource_id, now)
        - kept_copy_count(db, resource_id, now)
        - waiting_count(db, resource_id),
        0,
    )


def open_sessions(db: Session, resource_id: int, now: datetime.datetime) -> list[DigitalSession]:
    stmt = sa.select(DigitalSession).where(
        DigitalSession.resource_id == resource_id, DigitalSession.closed_at.is_(None), DigitalSession.expires_at > now
    )
    return list(db.scalars(stmt.order_by(DigitalSession.expires_at, DigitalSession.id)))


def free_seats(db: Session, resource_id: int, now: datetime.datetime) -> int:
    return max(capacity_at(db, resource_id, now) - len(open_sessions(db, resource_id, now)), 0)


def member_active_loans(db: Session, member_id: int, now: datetime.datetime) -> int:
    return _count(
        db,
        sa.select(DigitalLoan.id).where(
            DigitalLoan.member_id == member_id, DigitalLoan.status == "open", DigitalLoan.due_at > now
        ),
    )


def member_open_sessions(db: Session, member_id: int, now: datetime.datetime) -> int:
    return _count(
        db,
        sa.select(DigitalSession.id).where(
            DigitalSession.member_id == member_id, DigitalSession.closed_at.is_(None), DigitalSession.expires_at > now
        ),
    )


def member_holds(db: Session, member_id: int, now: datetime.datetime) -> int:
    """``waiting`` holds and ``ready`` holds that are not lapsed."""
    return _count(
        db,
        sa.select(DigitalHold.id).where(
            DigitalHold.member_id == member_id,
            sa.or_(
                DigitalHold.status == "waiting",
                sa.and_(DigitalHold.status == "ready", DigitalHold.ready_until >= now),
            ),
        ),
    )


def current_hold(db: Session, member_id: int, resource_id: int, now: datetime.datetime) -> DigitalHold | None:
    """The member's ``waiting`` hold or not lapsed ``ready`` hold of the resource."""
    stmt = sa.select(DigitalHold).where(
        DigitalHold.member_id == member_id,
        DigitalHold.resource_id == resource_id,
        sa.or_(DigitalHold.status == "waiting", sa.and_(DigitalHold.status == "ready", DigitalHold.ready_until >= now)),
    )
    return db.scalars(stmt.order_by(DigitalHold.id)).first()


def usable_ready_hold(db: Session, member_id: int, resource_id: int, now: datetime.datetime) -> DigitalHold | None:
    stmt = sa.select(DigitalHold).where(
        DigitalHold.member_id == member_id,
        DigitalHold.resource_id == resource_id,
        DigitalHold.status == "ready",
        DigitalHold.ready_until >= now,
    )
    return db.scalars(stmt.order_by(DigitalHold.id)).first()


def hold_position(db: Session, hold: DigitalHold) -> int | None:
    """``position`` of a ``waiting`` hold (25.1)."""
    if hold.status != "waiting":
        return None
    earlier = _count(
        db,
        sa.select(DigitalHold.id).where(
            DigitalHold.resource_id == hold.resource_id,
            DigitalHold.status == "waiting",
            sa.or_(
                DigitalHold.created_at < hold.created_at,
                sa.and_(DigitalHold.created_at == hold.created_at, DigitalHold.id < hold.id),
            ),
        ),
    )
    return 1 + earlier


def total_debt(db: Session, member_id: int, now: datetime.datetime, holidays: Container[datetime.date]) -> Decimal:
    """LIB-FEE-09."""
    return fines.outstanding_fees(db, member_id) + fines.accrued_late_fees(db, member_id, now, holidays)


def check_member_and_resource(
    db: Session, now: datetime.datetime, holidays: Container[datetime.date], resource: DigitalResource, member: Member
) -> None:
    """LIB-DIG-16 (2) to (6)."""
    if not resource.is_active:
        raise error("RESOURCE_INACTIVE", "The digital resource is inactive", resource_id=resource.id)
    if member.status == "passive":
        raise error("MEMBER_PASSIVE", "The member is passive")
    if now.date() > member.valid_until:
        raise error("MEMBERSHIP_EXPIRED", "The membership has expired")
    if member.membership_type == "guest":
        raise error("DIGITAL_NOT_ALLOWED_FOR_TYPE", "Guests cannot use digital resources")
    debt = total_debt(db, member.id, now, holidays)
    if debt >= DEBT_BLOCK:
        raise error("MEMBER_BLOCKED_BY_DEBT", "The member's debt blocks digital resources", total_debt=format_amount(debt))
