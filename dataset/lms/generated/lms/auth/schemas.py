"""Request and response schemas of module 2 (section 6)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StrictBool, StringConstraints, field_validator

from lms.auth.models import User
from lms.auth.passwords import password_problem
from lms.core.schemas import RequestModel
from lms.core.text import is_valid_email
from lms.core.timeutil import format_datetime

Role = Literal["member", "librarian", "admin"]
StaffRole = Literal["librarian", "admin"]

# Passwords are kept exactly as sent: no trimming.
RawPassword = Annotated[str, StringConstraints(strip_whitespace=False)]
FullName = Annotated[str, Field(min_length=1, max_length=200)]


def _check_policy(value: str) -> str:
    problem = password_problem(value)
    if problem is not None:
        raise ValueError(problem)
    return value


def _check_email(value: str) -> str:
    value = value.lower()
    if len(value) > 254:
        raise ValueError("e-mail must be at most 254 characters")
    if not is_valid_email(value):
        raise ValueError("invalid e-mail address")
    return value


class LoginIn(RequestModel):
    # No format check on the e-mail: an unknown address is just invalid credentials (LIB-AUTH-08).
    email: Annotated[str, Field(min_length=1)]
    password: Annotated[RawPassword, Field(min_length=1)]


class ChangePasswordIn(RequestModel):
    current_password: Annotated[RawPassword, Field(min_length=1)]
    new_password: RawPassword

    @field_validator("new_password")
    @classmethod
    def _policy(cls, value: str) -> str:
        return _check_policy(value)


class ResetPasswordIn(RequestModel):
    new_password: RawPassword

    @field_validator("new_password")
    @classmethod
    def _policy(cls, value: str) -> str:
        return _check_policy(value)


class UserCreateIn(RequestModel):
    email: str
    full_name: FullName
    role: StaffRole
    password: RawPassword

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return _check_email(value)

    @field_validator("password")
    @classmethod
    def _policy(cls, value: str) -> str:
        return _check_policy(value)


class UserPatchIn(RequestModel):
    """Any subset of the fields; ``null`` is not accepted for any of them."""

    full_name: FullName = None  # type: ignore[assignment]
    role: StaffRole = None  # type: ignore[assignment]
    is_active: StrictBool = None  # type: ignore[assignment]


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    member_id: int | None
    created_at: str
    last_login_at: str | None


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        member_id=user.member_id,
        created_at=format_datetime(user.created_at),
        last_login_at=format_datetime(user.last_login_at) if user.last_login_at else None,
    )


class LoginOut(BaseModel):
    access_token: str
    token_type: str
    expires_at: str
    user: UserOut
