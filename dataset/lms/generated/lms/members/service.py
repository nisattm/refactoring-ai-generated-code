"""Business logic of module 3: members (LIB-MEM-01 to LIB-MEM-13)."""

from __future__ import annotations

import dataclasses
import datetime
from collections.abc import Container
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import changes, record
from lms.auth.models import User
from lms.auth.passwords import hash_password
from lms.branches.service import require_active_branch
from lms.core.errors import Conflict, NotFound, ValidationFailed
from lms.core.money import ZERO
from lms.core.text import normalize
from lms.fines import service as fines
from lms.fines.schemas import BLOCKING_DEBT
from lms.loans.models import Loan
from lms.members.models import Member
from lms.members.types import MEMBERSHIP_TYPES, initial_valid_until
from lms.notifications.service import notify_member_deactivated, notify_membership_renewed
from lms.reservations import service as reservations


def get_member_or_404(db: Session, member_id: int) -> Member:
    member = db.get(Member, member_id)
    if member is None:
        raise NotFound(f"Member {member_id} does not exist", details={"resource": "member", "id": member_id})
    return member


def type_field_problems(membership_type: str, phone: str | None, university_id: str | None) -> list[dict[str, str]]:
    """LIB-MEM-02: the fields that break the type-specific rules."""
    problems: list[dict[str, str]] = []
    if membership_type == "guest":
        if phone is None:
            problems.append({"field": "phone", "problem": "phone is required for guests"})
        if university_id is not None:
            problems.append({"field": "university_id", "problem": "university_id must be null for guests"})
    elif university_id is None:
        problems.append({"field": "university_id", "problem": "university_id is required for this membership type"})
    return problems


def _check_unique_email(db: Session, email: str, *, own_user_id: int | None = None) -> None:
    stmt = sa.select(User.id).where(User.email_key == normalize(email))
    if own_user_id is not None:
        stmt = stmt.where(User.id != own_user_id)
    if db.scalar(stmt) is not None:
        raise Conflict("A user with this e-mail address already exists", details={"field": "email"})


def _check_unique_university_id(db: Session, university_id: str | None, *, own_member_id: int | None = None) -> None:
    if university_id is None:
        return
    stmt = sa.select(Member.id).where(Member.university_id_key == normalize(university_id))
    if own_member_id is not None:
        stmt = stmt.where(Member.id != own_member_id)
    if db.scalar(stmt) is not None:
        raise Conflict("A member with this university_id already exists", details={"field": "university_id"})


# --- registration and update ------------------------------------------------


def register_member(
    db: Session,
    now: datetime.datetime,
    actor: User,
    *,
    full_name: str,
    email: str,
    phone: str | None,
    membership_type: str,
    university_id: str | None,
    home_branch_id: int,
    password: str,
) -> Member:
    """LIB-MEM-01 to LIB-MEM-05. The member and its user account are created in one transaction."""
    problems = type_field_problems(membership_type, phone, university_id)
    if problems:
        raise ValidationFailed(problems)
    require_active_branch(db, "home_branch_id", home_branch_id)
    _check_unique_email(db, email)
    _check_unique_university_id(db, university_id)

    today = now.date()
    user = User(
        email=email,
        email_key=normalize(email),
        full_name=full_name,
        role="member",
        password_hash=hash_password(password),
        is_active=True,
        failed_login_count=0,
        created_at=now,
    )
    db.add(user)
    db.flush()
    member = Member(
        full_name=full_name,
        email=email,
        phone=phone,
        membership_type=membership_type,
        university_id=university_id,
        university_id_key=normalize(university_id) if university_id is not None else None,
        home_branch_id=home_branch_id,
        status="active",
        membership_start=today,
        valid_until=initial_valid_until(membership_type, today),
        user_id=user.id,
        created_at=now,
    )
    db.add(member)
    db.flush()
    user.member_id = member.id
    record(
        db,
        at=now,
        event="user_created",
        actor_user_id=actor.id,
        entity_type="user",
        entity_id=user.id,
        details={"email": email, "full_name": full_name, "role": "member", "member_id": member.id},
    )
    record(
        db,
        at=now,
        event="member_registered",
        actor_user_id=actor.id,
        entity_type="member",
        entity_id=member.id,
        details={
            "member_no": member.member_no,
            "full_name": full_name,
            "email": email,
            "phone": phone,
            "membership_type": membership_type,
            "university_id": university_id,
            "home_branch_id": home_branch_id,
            "user_id": user.id,
            "valid_until": member.valid_until.isoformat(),
        },
    )
    return member


def update_member(db: Session, now: datetime.datetime, actor: User, member: Member, fields: dict[str, Any]) -> Member:
    """LIB-MEM-07, LIB-MEM-08. ``fields`` holds only the fields present in the request."""
    if "home_branch_id" in fields:
        require_active_branch(db, "home_branch_id", fields["home_branch_id"])

    new = {name: fields.get(name, getattr(member, name)) for name in
           ("full_name", "email", "phone", "membership_type", "university_id", "home_branch_id")}
    if new["membership_type"] == "guest" and member.membership_type != "guest":
        new["university_id"] = None  # LIB-MEM-08
    problems = type_field_problems(new["membership_type"], new["phone"], new["university_id"])
    if problems:
        raise Conflict("The resulting member data is invalid", code="MEMBER_FIELDS_INVALID", details={"fields": problems})

    user = db.get(User, member.user_id)
    assert user is not None
    if new["email"] != member.email:
        _check_unique_email(db, new["email"], own_user_id=user.id)
    if new["university_id"] != member.university_id:
        _check_unique_university_id(db, new["university_id"], own_member_id=member.id)

    diff = changes({name: getattr(member, name) for name in new}, new)
    for name, value in new.items():
        setattr(member, name, value)
    member.university_id_key = normalize(member.university_id) if member.university_id is not None else None

    account = changes({"email": user.email, "full_name": user.full_name}, {"email": new["email"], "full_name": new["full_name"]})
    if account:
        user.email = new["email"]
        user.email_key = normalize(new["email"])
        user.full_name = new["full_name"]
        record(
            db, at=now, event="user_updated", actor_user_id=actor.id, entity_type="user", entity_id=user.id, details=account
        )
    if diff:
        record(
            db, at=now, event="member_updated", actor_user_id=actor.id, entity_type="member", entity_id=member.id, details=diff
        )
    return member


# --- membership lifecycle ---------------------------------------------------


def renew_membership(db: Session, now: datetime.datetime, actor: User, member: Member) -> Member:
    """LIB-MEM-09."""
    today = now.date()
    if member.status == "passive":
        raise Conflict("The member is passive", code="MEMBER_PASSIVE")
    old_valid_until = member.valid_until
    if member.valid_until >= today:
        member.valid_until += datetime.timedelta(days=MEMBERSHIP_TYPES[member.membership_type].validity_days)
    else:
        member.valid_until = initial_valid_until(member.membership_type, today)
    record(
        db,
        at=now,
        event="membership_renewed",
        actor_user_id=actor.id,
        entity_type="member",
        entity_id=member.id,
        details={"valid_until": {"old": old_valid_until.isoformat(), "new": member.valid_until.isoformat()}},
    )
    notify_membership_renewed(db, now, member.id, member.valid_until)
    return member


def deactivate_member(
    db: Session, now: datetime.datetime, actor: User, holidays: Container[datetime.date], member: Member
) -> Member:
    """LIB-MEM-10."""
    if member.status == "passive":
        raise Conflict("The member is already passive", code="MEMBER_PASSIVE")
    if db.scalar(sa.select(Loan.id).where(Loan.member_id == member.id, Loan.status == "open").limit(1)) is not None:
        raise Conflict("The member has open loans", code="MEMBER_HAS_OPEN_LOANS")
    member.status = "passive"
    record(
        db,
        at=now,
        event="member_deactivated",
        actor_user_id=actor.id,
        entity_type="member",
        entity_id=member.id,
        details={"status": {"old": "active", "new": "passive"}},
    )
    notify_member_deactivated(db, now, member.id)
    reservations.cancel_for_deactivation(db, now, actor, holidays, member)
    return member


def activate_member(db: Session, now: datetime.datetime, actor: User, member: Member) -> Member:
    """LIB-MEM-11."""
    if member.status == "active":
        raise Conflict("The member is already active", code="MEMBER_ALREADY_ACTIVE")
    member.status = "active"
    record(
        db,
        at=now,
        event="member_activated",
        actor_user_id=actor.id,
        entity_type="member",
        entity_id=member.id,
        details={"status": {"old": "passive", "new": "active"}},
    )
    return member


# --- summary ----------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class MemberActivity:
    """Loan, reservation and fee figures of a member, supplied by modules 5 to 7."""

    open_loans: int = 0
    overdue_loans: int = 0
    active_reservations: int = 0
    outstanding_fees: Decimal = ZERO
    accrued_late_fees: Decimal = ZERO


def member_activity(
    db: Session, member: Member, today: datetime.date, holidays: Container[datetime.date]
) -> MemberActivity:
    open_loans = db.scalars(sa.select(Loan).where(Loan.member_id == member.id, Loan.status == "open")).all()
    return MemberActivity(
        open_loans=len(open_loans),
        overdue_loans=sum(1 for loan in open_loans if today > loan.due_date),
        active_reservations=reservations.count_active(db, member.id),
        outstanding_fees=fines.outstanding_fees(db, member.id),
        accrued_late_fees=fines.accrued_late_fees(db, member.id, today, holidays),
    )


def borrowing_blockers(member: Member, activity: MemberActivity, today: datetime.date) -> list[str]:
    """LIB-MEM-12: the codes of LIB-LOAN-05 steps 1 to 5 that currently apply, in order."""
    reasons: list[str] = []
    if member.status == "passive":
        reasons.append("MEMBER_PASSIVE")
    if today > member.valid_until:
        reasons.append("MEMBERSHIP_EXPIRED")
    if activity.overdue_loans > 0:
        reasons.append("MEMBER_HAS_OVERDUE")
    if activity.outstanding_fees + activity.accrued_late_fees >= BLOCKING_DEBT:
        reasons.append("MEMBER_BLOCKED_BY_DEBT")
    if activity.open_loans >= MEMBERSHIP_TYPES[member.membership_type].loan_limit:
        reasons.append("LOAN_LIMIT_REACHED")
    return reasons
