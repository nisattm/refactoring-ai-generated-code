"""Rules of module 3 shared by its endpoints: type-specific fields, validity and output (7.1, LIB-MEM-02 to LIB-MEM-04)."""

import datetime

from lms.core.text import normalize_text
from lms.members.models import Member
from lms.members.schemas import MemberOut

# Days from today to the end of a new membership, counting today (LIB-MEM-03: 365 or 90 calendar days).
TERM_DAYS = {"guest": 90}
DEFAULT_TERM_DAYS = 365

# Length of a renewal (LIB-MEM-09).
RENEWAL_DAYS = {"guest": 90}
DEFAULT_RENEWAL_DAYS = 365


def term_days(membership_type: str) -> int:
    return TERM_DAYS.get(membership_type, DEFAULT_TERM_DAYS)


def renewal_days(membership_type: str) -> int:
    return RENEWAL_DAYS.get(membership_type, DEFAULT_RENEWAL_DAYS)


def member_number(member_id: int) -> str:
    return f"M{member_id:06d}"


def university_key(university_id: str) -> str:
    return normalize_text(university_id)


def type_violations(
    membership_type: str, phone: str | None, university_id: str | None
) -> list[dict[str, str]]:
    """Problems of the type-specific fields (LIB-MEM-02); an empty list when they are valid."""
    problems = []
    if membership_type == "guest":
        if phone is None:
            problems.append({"field": "phone", "problem": "is required for guest members"})
        if university_id is not None:
            problems.append({"field": "university_id", "problem": "must be absent for guest members"})
    elif university_id is None:
        problems.append({"field": "university_id", "problem": "is required for this membership type"})
    return problems


def is_valid_on(member: Member, day: datetime.date) -> bool:
    """A membership is valid on d when it is active and d ≤ valid_until (LIB-MEM-04)."""
    return member.status == "active" and day <= member.valid_until


def member_out(member: Member, today: datetime.date) -> MemberOut:
    return MemberOut(
        id=member.id,
        member_no=member.member_no,
        full_name=member.full_name,
        email=member.email,
        phone=member.phone,
        membership_type=member.membership_type,
        university_id=member.university_id,
        home_branch_id=member.home_branch_id,
        status=member.status,
        membership_start=member.membership_start,
        valid_until=member.valid_until,
        created_at=member.created_at,
        membership_valid=is_valid_on(member, today),
    )
