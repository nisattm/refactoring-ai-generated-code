"""Request and response bodies of module 3 (section 7)."""

import datetime
import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, field_validator

from lms.auth.passwords import check_password_policy
from lms.core.text import clean_email, clean_name

MembershipType = Literal["student", "academic", "staff", "guest"]
MemberStatus = Literal["active", "passive"]

_PHONE = re.compile(r"\+?[0-9 ]+")
_UNIVERSITY_ID = re.compile(r"[A-Za-z0-9]{4,20}")


def _trim(value: object) -> object:
    # Text is trimmed before validation (LIB-COM-15); other types fail validation as usual.
    return value.strip() if isinstance(value, str) else value


def clean_phone(value: str) -> str:
    """Digits and spaces with an optional leading +, 10 to 15 digits (7.2)."""
    if not _PHONE.fullmatch(value):
        raise ValueError("may contain only digits, spaces and a leading +")
    if not 10 <= sum(1 for char in value if char in "0123456789") <= 15:
        raise ValueError("must contain 10 to 15 digits")
    return value


def clean_university_id(value: str) -> str:
    if not _UNIVERSITY_ID.fullmatch(value):
        raise ValueError("must be 4 to 20 letters or digits")
    return value


Name = Annotated[str, BeforeValidator(_trim), AfterValidator(clean_name)]
Email = Annotated[str, BeforeValidator(_trim), AfterValidator(clean_email)]
Phone = Annotated[str, BeforeValidator(_trim), AfterValidator(clean_phone)]
UniversityId = Annotated[str, BeforeValidator(_trim), AfterValidator(clean_university_id)]
NewPassword = Annotated[str, AfterValidator(check_password_policy)]
BranchId = Annotated[int, Field(gt=0)]


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")  # unknown fields are rejected (LIB-COM-23)


class MemberCreate(StrictBody):
    full_name: Name
    email: Email
    phone: Phone | None = None  # required for guests (LIB-MEM-02, checked by the service)
    membership_type: MembershipType
    university_id: UniversityId | None = None  # required for non-guests, absent for guests
    home_branch_id: BranchId
    password: NewPassword


class MemberUpdate(StrictBody):
    full_name: Name | None = None
    email: Email | None = None
    phone: Phone | None = None  # explicit null clears the phone
    membership_type: MembershipType | None = None
    university_id: UniversityId | None = None  # explicit null clears the university id
    home_branch_id: BranchId | None = None

    @field_validator("full_name", "email", "membership_type", "home_branch_id", mode="before")
    @classmethod
    def _not_null(cls, value: object) -> object:
        # Absent fields are left alone; these fields cannot be cleared.
        if value is None:
            raise ValueError("must not be null")
        return value


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
    membership_start: datetime.date
    valid_until: datetime.date
    created_at: datetime.datetime
    membership_valid: bool  # LIB-MEM-04, for today
