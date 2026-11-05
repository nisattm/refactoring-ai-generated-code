"""Module 3 endpoints for members (section 7.3, LIB-MEM-01 to LIB-MEM-13)."""

import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query

from lms.api.deps import AuthDep, MemberAccountDep, SessionDep, SettingsDep, StaffDep
from lms.api.member_schemas import (
    MemberOut,
    MembershipType,
    MemberStatus,
    RegisterMemberIn,
    UpdateMemberIn,
)
from lms.branches.service import branch_reference
from lms.core.errors import ApiError
from lms.core.localtime import to_local
from lms.core.pagination import page_body
from lms.members import rules, service
from lms.members.models import Member

router = APIRouter(prefix="/api/v1/members", tags=["members"])

MemberId = Annotated[int, Path(gt=0)]


def _out(member: Member, day: datetime.date) -> MemberOut:
    return MemberOut.from_member(
        member, rules.membership_valid_on(member.status, member.valid_until, day)
    )


@router.post("", status_code=201, response_model=MemberOut)
def register_member(
    body: RegisterMemberIn, staff: StaffDep, session: SessionDep, settings: SettingsDep
) -> MemberOut:
    now = settings.clock.now()
    day = to_local(now).date()
    member = service.register_member(
        session,
        actor=staff.user,
        now=now,
        today=day,
        full_name=body.full_name,
        email=body.email,
        phone=body.phone,
        membership_type=body.membership_type,
        university_id=body.university_id,
        home_branch_id=body.home_branch_id,
        password=body.password,
    )
    return _out(member, day)


@router.get("")
def list_members(
    staff: StaffDep,
    session: SessionDep,
    settings: SettingsDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    q: str | None = None,
    membership_type: MembershipType | None = None,
    status: MemberStatus | None = None,
    home_branch_id: Annotated[int | None, Query(gt=0)] = None,
    membership_valid: Literal["true", "false"] | None = None,
) -> dict:
    day = to_local(settings.clock.now()).date()
    if home_branch_id is not None:
        branch_reference(session, home_branch_id, "home_branch_id")
    statement = service.member_list_statement(
        membership_type=membership_type,
        status=status,
        home_branch_id=home_branch_id,
        membership_valid=None if membership_valid is None else membership_valid == "true",
        today=day,
    )
    found = list(session.scalars(statement))
    if q is not None and q.strip():
        found = [member for member in found if service.member_matches(member, q)]
    start = (page - 1) * page_size
    items = [
        _out(member, day).model_dump(mode="json") for member in found[start : start + page_size]
    ]
    return page_body(items, page=page, page_size=page_size, total=len(found))


# Declared before /{member_id} so that "me" is not read as a member id.
@router.get("/me", response_model=MemberOut)
def my_member(auth: MemberAccountDep, session: SessionDep, settings: SettingsDep) -> MemberOut:
    day = to_local(settings.clock.now()).date()
    return _out(service.own_member(session, auth.user), day)


@router.get("/{member_id}", response_model=MemberOut)
def get_member(
    member_id: MemberId, auth: AuthDep, session: SessionDep, settings: SettingsDep
) -> MemberOut:
    member = service.get_member(session, member_id)
    # LIB-AUTH-25: an existing member that is not the caller's own is 403, not 404.
    if auth.user.role == "member" and auth.user.member_id != member.id:
        raise ApiError(403, "FORBIDDEN", "You may read only your own member record.")
    return _out(member, to_local(settings.clock.now()).date())


@router.patch("/{member_id}", response_model=MemberOut)
def update_member(
    member_id: MemberId,
    body: UpdateMemberIn,
    staff: StaffDep,
    session: SessionDep,
    settings: SettingsDep,
) -> MemberOut:
    member = service.get_member(session, member_id)
    now = settings.clock.now()
    service.update_member(
        session,
        actor=staff.user,
        now=now,
        member=member,
        values={field: getattr(body, field) for field in body.model_fields_set},
    )
    return _out(member, to_local(now).date())


@router.post("/{member_id}/renew-membership", response_model=MemberOut)
def renew_membership(
    member_id: MemberId, staff: StaffDep, session: SessionDep, settings: SettingsDep
) -> MemberOut:
    member = service.get_member(session, member_id)
    now = settings.clock.now()
    service.renew_membership(
        session,
        actor=staff.user,
        now=now,
        today=to_local(now).date(),
        member=member,
    )
    return _out(member, to_local(now).date())


@router.post("/{member_id}/deactivate", response_model=MemberOut)
def deactivate_member(
    member_id: MemberId, staff: StaffDep, session: SessionDep, settings: SettingsDep
) -> MemberOut:
    member = service.get_member(session, member_id)
    now = settings.clock.now()
    service.deactivate_member(session, actor=staff.user, now=now, member=member)
    return _out(member, to_local(now).date())


@router.post("/{member_id}/activate", response_model=MemberOut)
def activate_member(
    member_id: MemberId, staff: StaffDep, session: SessionDep, settings: SettingsDep
) -> MemberOut:
    member = service.get_member(session, member_id)
    now = settings.clock.now()
    service.activate_member(session, actor=staff.user, now=now, member=member)
    return _out(member, to_local(now).date())
