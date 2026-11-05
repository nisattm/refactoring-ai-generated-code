"""Request and response bodies of module 2 (section 6)."""

import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, field_validator

from lms.auth.passwords import check_password_policy
from lms.core.text import clean_email, clean_name


def _trim(value: object) -> object:
    # Text is trimmed before validation (LIB-COM-15); other types fail validation as usual.
    return value.strip() if isinstance(value, str) else value


Name = Annotated[str, BeforeValidator(_trim), AfterValidator(clean_name)]
Email = Annotated[str, BeforeValidator(_trim), AfterValidator(clean_email)]
NewPassword = Annotated[str, AfterValidator(check_password_policy)]
Role = Literal["member", "librarian", "admin"]
StaffRole = Literal["librarian", "admin"]


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")  # unknown fields are rejected (LIB-COM-23)


class LoginIn(StrictBody):
    email: Email
    password: str = Field(min_length=1)


class ChangePasswordIn(StrictBody):
    current_password: str = Field(min_length=1)
    new_password: NewPassword


class ResetPasswordIn(StrictBody):
    new_password: NewPassword


class UserCreate(StrictBody):
    email: Email
    full_name: Name
    role: StaffRole  # "member" is rejected here (LIB-AUTH-04)
    password: NewPassword


class UserUpdate(StrictBody):
    full_name: Name | None = None
    role: StaffRole | None = None  # "member" is rejected here (LIB-AUTH-20)
    is_active: bool | None = None

    @field_validator("full_name", "role", "is_active", mode="before")
    @classmethod
    def _not_null(cls, value: object) -> object:
        # Absent fields are left alone; an explicit null is not a value.
        if value is None:
            raise ValueError("must not be null")
        return value


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    member_id: int | None
    created_at: datetime.datetime
    last_login_at: datetime.datetime | None


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime.datetime
    user: UserOut
