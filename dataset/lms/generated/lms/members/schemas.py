"""Request and response schemas of module 3 (section 7)."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

from lms.auth.passwords import password_problem
from lms.auth.schemas import RawPassword
from lms.core.schemas import RequestModel
from lms.core.text import is_valid_email
from lms.core.timeutil import format_datetime
from lms.fines.schemas import BalanceOut
from lms.members.models import Member

MembershipTypeName = Literal["student", "academic", "staff", "guest"]
MemberStatus = Literal["active", "passive"]

_PHONE_RE = re.compile(r"^\+?[0-9 ]+$")
_UNIVERSITY_ID_RE = re.compile(r"^[A-Za-z0-9]{4,20}$")

FullName = Annotated[str, Field(min_length=1, max_length=200)]


def check_email(value: str) -> str:
    value = value.lower()
    if len(value) > 254:
        raise ValueError("e-mail must be at most 254 characters")
    if not is_valid_email(value):
        raise ValueError("invalid e-mail address")
    return value


def check_phone(value: str | None) -> str | None:
    if value is None:
        return None
    digits = sum(c.isdigit() for c in value)
    if not _PHONE_RE.match(value) or not 10 <= digits <= 15:
        raise ValueError("phone must contain 10-15 digits, spaces and an optional leading +")
    return value


def check_university_id(value: str | None) -> str | None:
    if value is None:
        return None
    if not _UNIVERSITY_ID_RE.match(value):
        raise ValueError("university_id must be 4-20 characters from A-Z, a-z and 0-9")
    return value


class _MemberFieldChecks:
    @field_validator("email", check_fields=False)
    @classmethod
    def _email(cls, value: str) -> str:
        return check_email(value)

    @field_validator("phone", check_fields=False)
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        return check_phone(value)

    @field_validator("university_id", check_fields=False)
    @classmethod
    def _university_id(cls, value: str | None) -> str | None:
        return check_university_id(value)


class MemberCreateIn(_MemberFieldChecks, RequestModel):
    full_name: FullName
    email: str
    phone: str | None = None
    membership_type: MembershipTypeName
    university_id: str | None = None
    home_branch_id: int
    password: RawPassword

    @field_validator("password")
    @classmethod
    def _policy(cls, value: str) -> str:
        problem = password_problem(value)
        if problem is not None:
            raise ValueError(problem)
        return value


class MemberPatchIn(_MemberFieldChecks, RequestModel):
    """Any subset of the fields. ``phone`` and ``university_id`` may be ``null``; the others may not."""

    full_name: FullName = None  # type: ignore[assignment]
    email: str = None  # type: ignore[assignment]
    phone: str | None = None
    membership_type: MembershipTypeName = None  # type: ignore[assignment]
    university_id: str | None = None
    home_branch_id: int = None  # type: ignore[assignment]


class MemberOut(BaseModel):
    id: int
    member_no: str
    full_name: str
    email: str
    phone: str | None
    membership_type: str
    university_id: str | None
    home_branch_id: int
    status: str
    membership_start: str
    valid_until: str
    created_at: str
    membership_valid: bool


def member_out(member: Member, today) -> MemberOut:  # noqa: ANN001
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
        membership_start=member.membership_start.isoformat(),
        valid_until=member.valid_until.isoformat(),
        created_at=format_datetime(member.created_at),
        membership_valid=member.is_valid_on(today),
    )


class BorrowingOut(BaseModel):
    eligible: bool
    reasons: list[str]


class MemberSummaryOut(BaseModel):
    member: MemberOut
    open_loans: int
    overdue_loans: int
    active_reservations: int
    balance: BalanceOut
    borrowing: BorrowingOut
