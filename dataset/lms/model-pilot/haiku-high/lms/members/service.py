"""Member rules (section 7.4, LIB-MEM-01 to LIB-MEM-11, LIB-MEM-13)."""

import datetime
import typing

from sqlalchemy import and_, not_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from lms.audit.service import record_event
from lms.auth.credentials import hash_password
from lms.auth.models import User
from lms.branches.service import branch_reference, require_active
from lms.core.errors import ApiError, validation_error
from lms.core.text import clean_email, email_key, normalize
from lms.members import rules
from lms.members.models import Member


def get_member(session: Session, member_id: int) -> Member:
    member = session.get(Member, member_id)
    if member is None:
        raise ApiError(404, "NOT_FOUND", "The member does not exist.")
    return member


def own_member(session: Session, user: User) -> Member:
    """LIB-MEM-13: the member linked to the authenticated user."""
    member = session.get(Member, user.member_id) if user.member_id is not None else None
    if member is None:
        raise ApiError(404, "NOT_FOUND", "No member is linked to this account.")
    return member


def _email_taken(session: Session, email: str, *, except_user_id: int | None = None) -> bool:
    """LIB-AUTH-05 / LIB-MEM-05: the address is used by any user account."""
    statement = select(User.id).where(User.email_key == email_key(email))
    if except_user_id is not None:
        statement = statement.where(User.id != except_user_id)
    return session.scalar(statement) is not None


def _university_id_taken(
    session: Session, key: str, *, except_member_id: int | None = None
) -> bool:
    statement = select(Member.id).where(Member.university_id_key == key)
    if except_member_id is not None:
        statement = statement.where(Member.id != except_member_id)
    return session.scalar(statement) is not None


def register_member(
    session: Session,
    *,
    actor: User,
    now: datetime.datetime,
    today: datetime.date,
    full_name: str,
    email: str,
    phone: str | None,
    membership_type: str,
    university_id: str | None,
    home_branch_id: int,
    password: str,
) -> Member:
    """LIB-MEM-01 to LIB-MEM-03. The member and its user account are created in one transaction.

    The request schema has already checked the formats and the password policy.
    """
    problems = rules.type_problems(membership_type, phone, university_id)
    if problems:
        raise validation_error(*problems)

    branch = branch_reference(session, home_branch_id, "home_branch_id")
    require_active(branch)

    if _email_taken(session, email):
        raise ApiError(
            409,
            "CONFLICT",
            "An account with this e-mail address already exists.",
            {"field": "email"},
        )
    university_key = normalize(university_id) if university_id is not None else None
    if university_key is not None and _university_id_taken(session, university_key):
        raise ApiError(
            409,
            "CONFLICT",
            "A member with this university ID already exists.",
            {"field": "university_id"},
        )

    stored_email = clean_email(email)
    user = User(
        email=stored_email,
        email_key=email_key(email),
        full_name=full_name,
        role="member",
        password_hash=hash_password(password),
        is_active=True,
        failed_login_count=0,
        locked_until=None,
        member_id=None,
        created_at=now,
        last_login_at=None,
    )
    session.add(user)
    session.flush()

    member = Member(
        # Replaced below: the number depends on the id that the first flush assigns.
        member_no="",
        full_name=full_name,
        email=stored_email,
        phone=phone,
        membership_type=membership_type,
        university_id=university_id,
        university_id_key=university_key,
        home_branch_id=branch.id,
        status="active",
        membership_start=today,
        valid_until=rules.first_valid_until(today, membership_type),
        user_id=user.id,
        created_at=now,
    )
    session.add(member)
    session.flush()
    member.member_no = rules.format_member_no(member.id)
    user.member_id = member.id
    session.flush()

    record_event(
        session,
        at=now,
        event="member_registered",
        entity_type="member",
        entity_id=member.id,
        actor_user_id=actor.id,
        details={
            "member_no": member.member_no,
            "full_name": full_name,
            "email": stored_email,
            "membership_type": membership_type,
            "home_branch_id": branch.id,
            "valid_until": member.valid_until.isoformat(),
        },
    )
    return member


def update_member(
    session: Session,
    *,
    actor: User,
    now: datetime.datetime,
    member: Member,
    values: typing.Mapping[str, typing.Any],
) -> Member:
    """LIB-MEM-07 and LIB-MEM-08. `values` holds only the fields that the request sent."""
    user = session.get(User, member.user_id)  # present: members.user_id is a foreign key

    if "home_branch_id" in values:
        require_active(branch_reference(session, values["home_branch_id"], "home_branch_id"))

    membership_type = values.get("membership_type", member.membership_type)
    phone = values.get("phone", member.phone)
    if "university_id" in values:
        university_id = values["university_id"]
    elif membership_type == rules.GUEST:
        # LIB-MEM-08: a change to guest sets university_id to null.
        university_id = None
    else:
        university_id = member.university_id

    # The values the member will have after the update.
    candidate: dict[str, typing.Any] = {
        "full_name": values.get("full_name", member.full_name),
        "email": clean_email(values["email"]) if "email" in values else member.email,
        "phone": phone,
        "membership_type": membership_type,
        "university_id": university_id,
        "home_branch_id": values.get("home_branch_id", member.home_branch_id),
    }
    changes = {field: new for field, new in candidate.items() if getattr(member, field) != new}

    # LIB-MEM-07: a result that breaks LIB-MEM-02 is a business-rule failure (409), not a request error.
    problems = rules.type_problems(membership_type, phone, university_id)
    if problems:
        raise ApiError(
            409,
            "MEMBER_FIELDS_INVALID",
            "The member's fields do not match the membership type.",
            {"fields": problems},
        )

    if "email" in changes and _email_taken(session, values["email"], except_user_id=user.id):
        raise ApiError(
            409,
            "CONFLICT",
            "An account with this e-mail address already exists.",
            {"field": "email"},
        )
    university_key = normalize(university_id) if university_id is not None else None
    if (
        "university_id" in changes
        and university_key is not None
        and _university_id_taken(session, university_key, except_member_id=member.id)
    ):
        raise ApiError(
            409,
            "CONFLICT",
            "A member with this university ID already exists.",
            {"field": "university_id"},
        )

    if not changes:
        return member

    audit_details: dict[str, typing.Any] = {}
    for field, new in changes.items():
        audit_details[field] = {"old": getattr(member, field), "new": new}
        setattr(member, field, new)
    member.university_id_key = university_key

    # LIB-MEM-07: a changed e-mail address or name is also changed on the user account.
    if "email" in changes:
        user.email = member.email
        user.email_key = email_key(values["email"])
    if "full_name" in changes:
        user.full_name = member.full_name

    record_event(
        session,
        at=now,
        event="member_updated",
        entity_type="member",
        entity_id=member.id,
        actor_user_id=actor.id,
        details=audit_details,
    )
    return member


def renew_membership(
    session: Session,
    *,
    actor: User,
    now: datetime.datetime,
    today: datetime.date,
    member: Member,
) -> Member:
    """LIB-MEM-09."""
    if member.status == "passive":
        raise ApiError(409, "MEMBER_PASSIVE", "The member is passive.")
    old = member.valid_until
    member.valid_until = rules.renewed_valid_until(old, today, member.membership_type)
    record_event(
        session,
        at=now,
        event="membership_renewed",
        entity_type="member",
        entity_id=member.id,
        actor_user_id=actor.id,
        details={"valid_until": {"old": old.isoformat(), "new": member.valid_until.isoformat()}},
    )
    return member


def deactivate_member(
    session: Session, *, actor: User, now: datetime.datetime, member: Member
) -> Member:
    """LIB-MEM-10. The open-loan check and the reservation cancellation are added with modules 5 and 6."""
    if member.status == "passive":
        raise ApiError(409, "MEMBER_PASSIVE", "The member is already passive.")
    member.status = "passive"
    record_event(
        session,
        at=now,
        event="member_deactivated",
        entity_type="member",
        entity_id=member.id,
        actor_user_id=actor.id,
        details={"status": {"old": "active", "new": "passive"}},
    )
    return member


def activate_member(
    session: Session, *, actor: User, now: datetime.datetime, member: Member
) -> Member:
    """LIB-MEM-11."""
    if member.status == "active":
        raise ApiError(409, "MEMBER_ALREADY_ACTIVE", "The member is already active.")
    member.status = "active"
    record_event(
        session,
        at=now,
        event="member_activated",
        entity_type="member",
        entity_id=member.id,
        actor_user_id=actor.id,
        details={"status": {"old": "passive", "new": "active"}},
    )
    return member


def member_list_statement(
    *,
    membership_type: str | None,
    status: str | None,
    home_branch_id: int | None,
    membership_valid: bool | None,
    today: datetime.date,
) -> Select:
    """LIB-MEM-06 filters that the database can apply. The text filter is applied by member_matches."""
    statement = select(Member).order_by(Member.id)
    if membership_type is not None:
        statement = statement.where(Member.membership_type == membership_type)
    if status is not None:
        statement = statement.where(Member.status == status)
    if home_branch_id is not None:
        statement = statement.where(Member.home_branch_id == home_branch_id)
    if membership_valid is not None:
        valid = and_(Member.status == "active", Member.valid_until >= today)
        statement = statement.where(valid if membership_valid else not_(valid))
    return statement


def member_matches(member: Member, q: str) -> bool:
    """LIB-MEM-06: case-insensitive substring of full name, e-mail, member number or university ID."""
    needle = normalize(q.strip())
    fields = (member.full_name, member.email, member.member_no, member.university_id or "")
    return any(needle in normalize(field) for field in fields)
