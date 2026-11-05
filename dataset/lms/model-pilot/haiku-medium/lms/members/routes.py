"""Module 3 endpoints: members (section 7.3, LIB-MEM-01 to LIB-MEM-13 except 12)."""

import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import orm, select

from lms.api.deps import get_db, get_settings
from lms.api.errors import ApiError
from lms.audit.log import record_event
from lms.auth.deps import current_user, require_roles
from lms.auth.models import User
from lms.auth.passwords import hash_password
from lms.branches.service import ensure_active, reference_branch
from lms.core.clock import today
from lms.core.pagination import Page, PageParams, paginate
from lms.core.settings import Settings
from lms.core.text import normalize_text
from lms.members.models import Member
from lms.members.schemas import MemberCreate, MemberOut, MemberUpdate, MembershipType, MemberStatus
from lms.members.service import (
    is_valid_on,
    member_number,
    member_out,
    renewal_days,
    term_days,
    type_violations,
    university_key,
)

router = APIRouter(prefix="/api/v1/members", tags=["members"])

staff_only = require_roles("librarian", "admin")


def _not_found() -> ApiError:
    return ApiError(404, "NOT_FOUND", "The member does not exist.")


def _load(db: orm.Session, member_id: int) -> Member:
    member = db.get(Member, member_id)
    if member is None:
        raise _not_found()
    return member


def _load_for_reader(db: orm.Session, member_id: int, user: User) -> Member:
    """A member may read only their own record; a missing record is 404 before the ownership check (LIB-COM-28)."""
    member = _load(db, member_id)
    if user.role == "member" and user.member_id != member.id:
        raise ApiError(403, "FORBIDDEN", "You may only read your own member record.")
    return member


def _fields_error(problems: list[dict[str, str]]) -> ApiError:
    return ApiError(422, "VALIDATION_ERROR", "The request is invalid.", {"fields": problems})


# --- Registration and lists ----------------------------------------------------------------


@router.post("", status_code=201, response_model=MemberOut)
def register_member(
    body: MemberCreate,
    staff: User = Depends(staff_only),
    db: orm.Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MemberOut:
    problems = type_violations(body.membership_type, body.phone, body.university_id)
    if problems:
        raise _fields_error(problems)

    branch = reference_branch(db, "home_branch_id", body.home_branch_id)
    ensure_active(branch)

    if db.scalar(select(User.id).where(User.email_key == normalize_text(body.email))) is not None:
        raise ApiError(409, "CONFLICT", "An account with this e-mail address already exists.", {"field": "email"})
    university_key_value = university_key(body.university_id) if body.university_id is not None else None
    if university_key_value is not None and db.scalar(
        select(Member.id).where(Member.university_id_key == university_key_value)
    ) is not None:
        raise ApiError(409, "CONFLICT", "A member with this university id already exists.", {"field": "university_id"})

    now = settings.clock.now()
    day = today(settings.clock)
    user = User(
        email=body.email,
        email_key=normalize_text(body.email),
        full_name=body.full_name,
        role="member",
        password_hash=hash_password(body.password),
        is_active=True,
        failed_login_count=0,
        locked_until=None,
        member_id=None,
        created_at=now,
        last_login_at=None,
    )
    db.add(user)
    db.flush()

    member = Member(
        member_no="",  # set from the id below, in the same transaction
        full_name=body.full_name,
        email=body.email,
        phone=body.phone,
        membership_type=body.membership_type,
        university_id=body.university_id,
        university_id_key=university_key_value,
        home_branch_id=body.home_branch_id,
        status="active",
        membership_start=day,
        valid_until=day + datetime.timedelta(days=term_days(body.membership_type) - 1),  # LIB-MEM-03
        user_id=user.id,
        created_at=now,
    )
    db.add(member)
    db.flush()
    member.member_no = member_number(member.id)
    user.member_id = member.id

    record_event(
        db, settings.clock, "user_created",
        actor_user_id=staff.id, entity_type="user", entity_id=user.id,
        details={"email": user.email, "full_name": user.full_name, "role": user.role},
    )
    record_event(
        db, settings.clock, "member_registered",
        actor_user_id=staff.id, entity_type="member", entity_id=member.id,
        details={
            "member_no": member.member_no,
            "full_name": member.full_name,
            "email": member.email,
            "membership_type": member.membership_type,
            "university_id": member.university_id,
            "home_branch_id": member.home_branch_id,
        },
    )
    db.commit()
    return member_out(member, day)


@router.get("", response_model=Page[MemberOut])
def list_members(
    q: str | None = Query(default=None),
    membership_type: MembershipType | None = Query(default=None),
    status: MemberStatus | None = Query(default=None),
    home_branch_id: int | None = Query(default=None, gt=0),
    membership_valid: Literal["true", "false"] | None = Query(default=None),
    params: PageParams = Depends(),
    _staff: User = Depends(staff_only),
    db: orm.Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Page[MemberOut]:
    statement = select(Member).order_by(Member.id)
    if membership_type is not None:
        statement = statement.where(Member.membership_type == membership_type)
    if status is not None:
        statement = statement.where(Member.status == status)
    if home_branch_id is not None:
        reference_branch(db, "home_branch_id", home_branch_id)
        statement = statement.where(Member.home_branch_id == home_branch_id)
    members = list(db.scalars(statement))

    day = today(settings.clock)
    if membership_valid is not None:
        members = [m for m in members if is_valid_on(m, day) == (membership_valid == "true")]
    # Substring match on the normalized text, which SQL lower() cannot do for Turkish letters (LIB-SRCH-01).
    needle = normalize_text((q or "").strip())
    if needle:
        members = [
            m for m in members
            if any(
                needle in normalize_text(value)
                for value in (m.full_name, m.email, m.member_no, m.university_id or "")
            )
        ]
    return paginate(members, params, lambda m: member_out(m, day))


# --- Own record and single record (declared before /{member_id}) ----------------------------


@router.get("/me", response_model=MemberOut)
def my_member(
    user: User = Depends(require_roles("member")),
    db: orm.Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MemberOut:
    if user.member_id is None:
        raise ApiError(404, "NOT_FOUND", "No member record is linked to this account.")
    return member_out(_load(db, user.member_id), today(settings.clock))


@router.get("/{member_id}", response_model=MemberOut)
def get_member(
    member_id: int = Path(gt=0),
    user: User = Depends(current_user),
    db: orm.Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MemberOut:
    return member_out(_load_for_reader(db, member_id, user), today(settings.clock))


@router.patch("/{member_id}", response_model=MemberOut)
def update_member(
    body: MemberUpdate,
    member_id: int = Path(gt=0),
    staff: User = Depends(staff_only),
    db: orm.Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MemberOut:
    member = _load(db, member_id)
    fields = body.model_fields_set

    if "home_branch_id" in fields:
        ensure_active(reference_branch(db, "home_branch_id", body.home_branch_id))  # BRANCH_INACTIVE first (LIB-BR-04)

    new_type = body.membership_type if "membership_type" in fields else member.membership_type
    new_phone = body.phone if "phone" in fields else member.phone
    new_university_id = body.university_id if "university_id" in fields else member.university_id
    if new_type == "guest" and new_type != member.membership_type and "university_id" not in fields:
        new_university_id = None  # a change to guest clears the university id (LIB-MEM-08)

    problems = type_violations(new_type, new_phone, new_university_id)
    if problems:
        raise ApiError(409, "MEMBER_FIELDS_INVALID", "The resulting member breaks the rules for its type.", {"fields": problems})

    if "email" in fields and db.scalar(
        select(User.id).where(User.email_key == normalize_text(body.email), User.id != member.user_id)
    ) is not None:
        raise ApiError(409, "CONFLICT", "An account with this e-mail address already exists.", {"field": "email"})
    new_university_key = university_key(new_university_id) if new_university_id is not None else None
    if new_university_key is not None and db.scalar(
        select(Member.id).where(Member.university_id_key == new_university_key, Member.id != member.id)
    ) is not None:
        raise ApiError(409, "CONFLICT", "A member with this university id already exists.", {"field": "university_id"})

    new_values = {
        "full_name": body.full_name if "full_name" in fields else member.full_name,
        "email": body.email if "email" in fields else member.email,
        "phone": new_phone,
        "membership_type": new_type,
        "university_id": new_university_id,
        "home_branch_id": body.home_branch_id if "home_branch_id" in fields else member.home_branch_id,
    }
    changes: dict[str, dict] = {}
    for name, new in new_values.items():
        old = getattr(member, name)
        if old != new:
            changes[name] = {"old": old, "new": new}
            setattr(member, name, new)
    member.university_id_key = new_university_key

    # A changed name or e-mail is also changed on the user account (LIB-MEM-07).
    user = db.get(User, member.user_id)
    if "full_name" in changes:
        user.full_name = member.full_name
    if "email" in changes:
        user.email = member.email
        user.email_key = normalize_text(member.email)

    if changes:
        record_event(
            db, settings.clock, "member_updated",
            actor_user_id=staff.id, entity_type="member", entity_id=member.id, details=changes,
        )
    db.commit()
    return member_out(member, today(settings.clock))


@router.post("/{member_id}/renew-membership", response_model=MemberOut)
def renew_membership(
    member_id: int = Path(gt=0),
    staff: User = Depends(staff_only),
    db: orm.Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MemberOut:
    member = _load(db, member_id)
    if member.status == "passive":
        raise ApiError(409, "MEMBER_PASSIVE", "A passive member cannot renew the membership.")

    day = today(settings.clock)
    old_valid_until = member.valid_until
    if old_valid_until >= day:
        member.valid_until = old_valid_until + datetime.timedelta(days=renewal_days(member.membership_type))
    else:
        member.valid_until = day + datetime.timedelta(days=renewal_days(member.membership_type) - 1)

    record_event(
        db, settings.clock, "membership_renewed",
        actor_user_id=staff.id, entity_type="member", entity_id=member.id,
        details={"valid_until": {"old": old_valid_until.isoformat(), "new": member.valid_until.isoformat()}},
    )
    db.commit()
    return member_out(member, day)


@router.post("/{member_id}/deactivate", response_model=MemberOut)
def deactivate_member(
    member_id: int = Path(gt=0),
    staff: User = Depends(staff_only),
    db: orm.Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MemberOut:
    member = _load(db, member_id)
    if member.status == "passive":
        raise ApiError(409, "MEMBER_PASSIVE", "The member is already passive.")
    # Open loans (MEMBER_HAS_OPEN_LOANS) and cancelled reservations come with modules 5 and 6.

    member.status = "passive"
    record_event(
        db, settings.clock, "member_deactivated",
        actor_user_id=staff.id, entity_type="member", entity_id=member.id,
        details={"status": {"old": "active", "new": "passive"}},
    )
    db.commit()
    return member_out(member, today(settings.clock))


@router.post("/{member_id}/activate", response_model=MemberOut)
def activate_member(
    member_id: int = Path(gt=0),
    staff: User = Depends(staff_only),
    db: orm.Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MemberOut:
    member = _load(db, member_id)
    if member.status == "active":
        raise ApiError(409, "MEMBER_ALREADY_ACTIVE", "The member is already active.")

    member.status = "active"
    record_event(
        db, settings.clock, "member_activated",
        actor_user_id=staff.id, entity_type="member", entity_id=member.id,
        details={"status": {"old": "passive", "new": "active"}},
    )
    db.commit()
    return member_out(member, today(settings.clock))
