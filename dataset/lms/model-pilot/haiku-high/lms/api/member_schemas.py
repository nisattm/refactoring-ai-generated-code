"""Request and response schemas of module 3 (section 7). Unknown fields are rejected (LIB-COM-23)."""

import datetime
import re
import typing
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from lms.api.auth_schemas import RequestModel, check_email, check_name
from lms.auth.credentials import check_password_policy
from lms.members.models import Member

MembershipType = Literal["student", "academic", "staff", "guest"]
MemberStatus = Literal["active", "passive"]

# Digits and spaces with an optional leading "+", and 10 to 15 digits (section 7.2).
PHONE_RE = re.compile(r"\+?[0-9 ]+")
UNIVERSITY_ID_RE = re.compile(r"[A-Za-z0-9]{4,20}")


def check_phone(value: str) -> str:
    phone = value.strip()
    digits = sum(1 for char in phone if "0" <= char <= "9")
    if not PHONE_RE.fullmatch(phone) or not 10 <= digits <= 15:
        raise ValueError("must be 10 to 15 digits, optionally with spaces and a leading '+'")
    return phone


def check_university_id(value: str) -> str:
    university_id = value.strip()
    if not UNIVERSITY_ID_RE.fullmatch(university_id):
        raise ValueError("must be 4 to 20 letters or digits")
    return university_id


class MemberOut(BaseModel):
    """MemberOut (section 7.2): the member fields and the validity for today (LIB-MEM-04). No user id."""

    id: int
    member_no: str
    full_name: str
    email: str
    phone: str | None
    membership_type: str
    university_id: str | None
    home_branch_id: int
    status: str
    membership_start: datetime.date
    valid_until: datetime.date
    membership_valid: bool
    created_at: datetime.datetime

    @classmethod
    def from_member(cls, member: Member, membership_valid: bool) -> typing.Self:
        return cls(
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
            membership_valid=membership_valid,
            created_at=member.created_at,
        )


class RegisterMemberIn(RequestModel):
    full_name: str
    email: str
    # Which of phone and university_id are required depends on the type (LIB-MEM-02, checked by the service).
    phone: str | None = None
    membership_type: MembershipType
    university_id: str | None = None
    home_branch_id: int = Field(gt=0)
    password: str

    @field_validator("full_name")
    @classmethod
    def _name(cls, value: str) -> str:
        return check_name(value)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return check_email(value)

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        return check_phone(value) if value is not None else None

    @field_validator("university_id")
    @classmethod
    def _university_id(cls, value: str | None) -> str | None:
        return check_university_id(value) if value is not None else None

    @field_validator("password")
    @classmethod
    def _policy(cls, value: str) -> str:
        return check_password_policy(value)


class UpdateMemberIn(RequestModel):
    """Any subset of the updatable fields. Only phone and university_id may be set to null."""

    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    membership_type: MembershipType | None = None
    university_id: str | None = None
    home_branch_id: int | None = Field(default=None, gt=0)

    @field_validator("full_name", "email", "membership_type", "home_branch_id", mode="before")
    @classmethod
    def _not_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("must not be null")
        return value

    @field_validator("full_name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return check_name(value) if value is not None else None

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        return check_email(value) if value is not None else None

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        return check_phone(value) if value is not None else None

    @field_validator("university_id")
    @classmethod
    def _university_id(cls, value: str | None) -> str | None:
        return check_university_id(value) if value is not None else None
