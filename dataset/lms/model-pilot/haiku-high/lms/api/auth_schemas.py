"""Request and response schemas of module 2 (section 6). Unknown fields are rejected (LIB-COM-23)."""

import datetime
import typing

from pydantic import BaseModel, ConfigDict, field_validator

from lms.auth.credentials import check_password_policy
from lms.core.text import clean_email, clean_text

EMAIL_MAX_LENGTH = 254
NAME_MAX_LENGTH = 200

Role = typing.Literal["member", "librarian", "admin"]
StaffRole = typing.Literal["librarian", "admin"]


def check_email(value: str) -> str:
    """LIB-COM-17 and the 254-character limit of section 6.1. Returns the address trimmed, not lower-cased."""
    stored = clean_email(value)
    if len(stored) > EMAIL_MAX_LENGTH:
        raise ValueError(f"must be at most {EMAIL_MAX_LENGTH} characters")
    return value.strip()


def check_name(value: str) -> str:
    return clean_text(value, min_length=1, max_length=NAME_MAX_LENGTH)


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UserOut(BaseModel):
    """UserOut (section 6.1). The password hash is never part of it."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    member_id: int | None
    created_at: datetime.datetime
    last_login_at: datetime.datetime | None


class LoginIn(RequestModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return check_email(value)


class LoginOut(BaseModel):
    access_token: str
    token_type: typing.Literal["bearer"] = "bearer"
    expires_at: datetime.datetime
    user: UserOut


class ChangePasswordIn(RequestModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _policy(cls, value: str) -> str:
        return check_password_policy(value)


class CreateUserIn(RequestModel):
    email: str
    full_name: str
    role: StaffRole
    password: str

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return check_email(value)

    @field_validator("full_name")
    @classmethod
    def _name(cls, value: str) -> str:
        return check_name(value)

    @field_validator("password")
    @classmethod
    def _policy(cls, value: str) -> str:
        return check_password_policy(value)


class UpdateUserIn(RequestModel):
    """Any subset of the fields. An explicit null is rejected rather than read as "unchanged"."""

    full_name: str | None = None
    role: StaffRole | None = None
    is_active: bool | None = None

    @field_validator("full_name", "role", "is_active", mode="before")
    @classmethod
    def _not_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("must not be null")
        return value

    @field_validator("full_name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return check_name(value) if value is not None else None


class ResetPasswordIn(RequestModel):
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _policy(cls, value: str) -> str:
        return check_password_policy(value)
