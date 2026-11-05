"""Request and response schemas of module 11 (section 17)."""

import datetime
import re

from pydantic import BaseModel, ConfigDict, field_validator

from lms.api.auth_schemas import RequestModel, check_name
from lms.core.text import clean_text

CODE_RE = re.compile(r"[A-Z0-9]{2,10}")
ADDRESS_MAX_LENGTH = 300


def check_code(value: str) -> str:
    """LIB-BR-01 and section 17.1: 2-10 characters [A-Z0-9], stored in upper case."""
    code = value.strip().upper()
    if not CODE_RE.fullmatch(code):
        raise ValueError("must be 2 to 10 characters of A-Z and 0-9")
    return code


def check_address(value: str) -> str:
    return clean_text(value, max_length=ADDRESS_MAX_LENGTH)


class BranchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    address: str
    is_active: bool
    created_at: datetime.datetime


class CreateBranchIn(RequestModel):
    code: str
    name: str
    address: str

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        return check_code(value)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return check_name(value)

    @field_validator("address")
    @classmethod
    def _address(cls, value: str) -> str:
        return check_address(value)


class UpdateBranchIn(RequestModel):
    """Any subset of name, address and active state. `code` cannot be changed. An explicit null is rejected."""

    name: str | None = None
    address: str | None = None
    is_active: bool | None = None

    @field_validator("name", "address", "is_active", mode="before")
    @classmethod
    def _not_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("must not be null")
        return value

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return check_name(value) if value is not None else None

    @field_validator("address")
    @classmethod
    def _address(cls, value: str | None) -> str | None:
        return check_address(value) if value is not None else None
