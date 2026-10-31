"""Business logic of module 5: loans and returns (LIB-LOAN-01 to LIB-LOAN-14)."""

from __future__ import annotations

import datetime
from collections.abc import Container
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.branches.models import Branch
from lms.catalog.models import Copy
from lms.catalog.release import release_copy
from lms.catalog.status import set_status
from lms.core.calendar import next_working_day
from lms.core.errors import Conflict, NotFound, reference_not_found
from lms.core.money import format_amount
from lms.fines.service import (
    LOST_PROCESSING_FEE,
    create_fee,
    late_days_between,
    late_fee_amount,
)
from lms.loans.models import Loan
from lms.members import service as members
from lms.members.models import Member
from lms.members.types import MEMBERSHIP_TYPES
from lms.reservations import service as reservations


def get_loan_or_404(db: Session, loan_id: int) -> Loan:
    loan = db.get(Loan, loan_id)
    if loan is None:
        raise NotFound(f"Loan {loan_id} does not exist", details={"resource": "loan", "id": loan_id})
    return loan


def due_date_after(start: datetime.date, loan_period_days: int, holidays: Container[datetime.date]) -> datetime.date:
    """LIB-LOAN-03, LIB-LOAN-08: the next working day on or after ``start`` + the loan period."""
    return next_working_day(start + datetime.timedelta(days=loan_period_days), holidays)


# --- lending -------------------------------------------------------------------


def _find_copy(db: Session, copy_id: int | None, barcode: str | None) -> Copy:
    if copy_id is not None:
        copy = db.get(Copy, copy_id)
        if copy is None:
            raise reference_not_found("copy_id", copy_id)
        return copy
    assert barcode is not None
    copy = db.scalar(sa.select(Copy).where(Copy.barcode == barcode.upper()))
    if copy is None:
        raise NotFound(f"No copy has barcode {barcode}", details={"field": "barcode", "value": barcode})
    return copy


def lend(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    *,
    member_id: int,
    copy_id: int | None,
    barcode: str | None,
) -> Loan:
    """LIB-LOAN-01, LIB-LOAN-03 to LIB-LOAN-06."""
    member = db.get(Member, member_id)
    if member is None:
        raise reference_not_found("member_id", member_id)
    copy = _find_copy(db, copy_id, barcode)

    today = now.date()
    activity = members.member_activity(db, member, today, holidays)
    reasons = members.borrowing_blockers(member, activity, today)
    if reasons:
        details: dict[str, object] = {}
        if reasons[0] == "MEMBER_BLOCKED_BY_DEBT":
            details["total_debt"] = format_amount(activity.outstanding_fees + activity.accrued_late_fees)
        raise Conflict(f"The member cannot borrow: {reasons[0]}", code=reasons[0], details=details)

    reservations.expire_stale_hold(db, now, copy, holidays, actor.id)  # LIB-RES-11
    if copy.status == "on_hold":
        if not reservations.hold_belongs_to_member(db, now, copy, member):
            raise Conflict("The copy is held for a reservation", code="COPY_ON_HOLD", details={"status": copy.status})
    elif copy.status != "available":
        raise Conflict(
            f"The copy has status {copy.status}", code="COPY_NOT_AVAILABLE", details={"status": copy.status}
        )
    assert copy.current_branch_id is not None

    terms = MEMBERSHIP_TYPES[member.membership_type]
    loan = Loan(
        copy_id=copy.id,
        member_id=member.id,
        branch_id=copy.current_branch_id,
        loan_date=today,
        due_date=due_date_after(today, terms.loan_period_days, holidays),
        loan_period_days=terms.loan_period_days,
        max_renewals=terms.max_renewals,
        daily_fee=terms.daily_fee,
        renewal_count=0,
        status="open",
        created_by=actor.id,
    )
    db.add(loan)
    reservations.fulfil_for_loan(db, now, member, copy, holidays, actor.id)
    set_status(copy, "on_loan")
    db.flush()
    record(
        db,
        at=now,
        event="loan_created",
        actor_user_id=actor.id,
        entity_type="loan",
        entity_id=loan.id,
        details={
            "member_id": member.id,
            "copy_id": copy.id,
            "book_id": copy.book_id,
            "branch_id": loan.branch_id,
            "due_date": loan.due_date.isoformat(),
        },
    )
    return loan


# --- renewal -------------------------------------------------------------------


def renew(
    db: Session, now: datetime.datetime, actor: User, holidays: Container[datetime.date], loan: Loan
) -> Loan:
    """LIB-LOAN-07, LIB-LOAN-08."""
    today = now.date()
    member = db.get(Member, loan.member_id)
    copy = db.get(Copy, loan.copy_id)
    assert member is not None and copy is not None
    if loan.status != "open":
        raise Conflict("The loan is not open", code="LOAN_NOT_OPEN", details={"status": loan.status})
    if member.status == "passive":
        raise Conflict("The member is passive", code="MEMBER_PASSIVE")
    if today > member.valid_until:
        raise Conflict("The membership has expired", code="MEMBERSHIP_EXPIRED")
    if today > loan.due_date:
        raise Conflict("The loan is overdue", code="LOAN_OVERDUE", details={"due_date": loan.due_date.isoformat()})
    if loan.renewal_count >= loan.max_renewals:
        raise Conflict(
            "The renewal limit is reached", code="RENEWAL_LIMIT_REACHED", details={"max_renewals": loan.max_renewals}
        )
    if reservations.book_has_active_reservation(db, copy.book_id):
        raise Conflict("The book is reserved", code="BOOK_RESERVED", details={"book_id": copy.book_id})

    old_due = loan.due_date
    loan.due_date = due_date_after(today, loan.loan_period_days, holidays)
    loan.renewal_count += 1
    record(
        db,
        at=now,
        event="loan_renewed",
        actor_user_id=actor.id,
        entity_type="loan",
        entity_id=loan.id,
        details={
            "member_id": loan.member_id,
            "copy_id": loan.copy_id,
            "due_date": {"old": old_due.isoformat(), "new": loan.due_date.isoformat()},
            "renewal_count": loan.renewal_count,
        },
    )
    return loan


# --- return and loss -----------------------------------------------------------


def return_loan(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    loan: Loan,
    *,
    branch_id: int,
    condition: str,
    damage_fee: Decimal | None,
) -> Loan:
    """LIB-LOAN-09 to LIB-LOAN-12."""
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise reference_not_found("branch_id", branch_id)
    if loan.status != "open":
        raise Conflict("The loan is not open", code="LOAN_NOT_OPEN", details={"status": loan.status})
    if not branch.is_active:
        raise Conflict(
            f"Branch {branch.code} is inactive", code="BRANCH_INACTIVE", details={"field": "branch_id", "id": branch_id}
        )
    copy = db.get(Copy, loan.copy_id)
    assert copy is not None
    if damage_fee is not None and damage_fee > copy.price:
        raise Conflict(
            "The damage fee exceeds the price of the copy",
            code="DAMAGE_FEE_EXCEEDS_PRICE",
            details={"price": format_amount(copy.price)},
        )

    today = now.date()
    loan.status = "returned"
    loan.returned_on = today
    loan.return_branch_id = branch_id
    loan.condition_on_return = condition
    loan.late_days = late_days_between(loan.due_date, today, holidays)
    record(
        db,
        at=now,
        event="loan_returned",
        actor_user_id=actor.id,
        entity_type="loan",
        entity_id=loan.id,
        details={
            "member_id": loan.member_id,
            "copy_id": loan.copy_id,
            "branch_id": branch_id,
            "condition": condition,
            "late_days": loan.late_days,
            "damage_fee": format_amount(damage_fee) if damage_fee is not None else None,
        },
    )
    if loan.late_days > 0:
        create_fee(
            db, now, actor, member_id=loan.member_id, loan_id=loan.id, kind="late_fee",
            amount=late_fee_amount(loan.late_days, loan.daily_fee),
        )
    copy.current_branch_id = branch_id
    if condition == "damaged":
        assert damage_fee is not None
        create_fee(db, now, actor, member_id=loan.member_id, loan_id=loan.id, kind="damage_fee", amount=damage_fee)
        set_status(copy, "damaged")
    else:
        release_copy(db, copy, now, holidays, actor.id)
    return loan


def report_lost(
    db: Session, now: datetime.datetime, actor: User, holidays: Container[datetime.date], loan: Loan
) -> Loan:
    """LIB-LOAN-13, LIB-FEE-04."""
    if loan.status != "open":
        raise Conflict("The loan is not open", code="LOAN_NOT_OPEN", details={"status": loan.status})
    copy = db.get(Copy, loan.copy_id)
    assert copy is not None
    today = now.date()
    loan.status = "lost"
    loan.late_days = late_days_between(loan.due_date, today, holidays)
    set_status(copy, "lost")
    copy.current_branch_id = None
    record(
        db,
        at=now,
        event="loan_lost",
        actor_user_id=actor.id,
        entity_type="loan",
        entity_id=loan.id,
        details={"member_id": loan.member_id, "copy_id": loan.copy_id, "late_days": loan.late_days},
    )
    if loan.late_days > 0:
        create_fee(
            db, now, actor, member_id=loan.member_id, loan_id=loan.id, kind="late_fee",
            amount=late_fee_amount(loan.late_days, loan.daily_fee),
        )
    create_fee(db, now, actor, member_id=loan.member_id, loan_id=loan.id, kind="lost_book", amount=copy.price)
    create_fee(
        db, now, actor, member_id=loan.member_id, loan_id=loan.id, kind="lost_processing", amount=LOST_PROCESSING_FEE
    )
    return loan


# --- queries -------------------------------------------------------------------


def loan_list_stmt(
    today: datetime.date,
    *,
    member_id: int | None = None,
    copy_id: int | None = None,
    book_id: int | None = None,
    branch_id: int | None = None,
    status: str | None = None,
    overdue: bool | None = None,
    due_before: datetime.date | None = None,
) -> sa.Select[tuple[Loan]]:
    """LIB-LOAN-14: filtered loans, newest first."""
    stmt = sa.select(Loan).order_by(Loan.id.desc())
    if member_id is not None:
        stmt = stmt.where(Loan.member_id == member_id)
    if copy_id is not None:
        stmt = stmt.where(Loan.copy_id == copy_id)
    if book_id is not None:
        stmt = stmt.where(Loan.copy_id.in_(sa.select(Copy.id).where(Copy.book_id == book_id)))
    if branch_id is not None:
        stmt = stmt.where(Loan.branch_id == branch_id)
    if status is not None:
        stmt = stmt.where(Loan.status == status)
    if overdue is not None:
        is_overdue = sa.and_(Loan.status == "open", Loan.due_date < today)
        stmt = stmt.where(is_overdue if overdue else sa.not_(is_overdue))
    if due_before is not None:
        stmt = stmt.where(Loan.due_date <= due_before)
    return stmt
