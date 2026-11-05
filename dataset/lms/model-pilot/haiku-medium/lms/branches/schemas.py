"""Request and response bodies of module 11 (section 17)."""

import datetime
import re
from typing import Annotated

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, field_validator

from lms.core.text import clean_name

_CODE = re.compile(r"[A-Z0-9]{2,10}")
_MAX_ADDRESS = 300


def _trim(value: object) -> object:
    # Text is trimmed before validation (LIB-COM-15); other types fail validation as usual.
    return value.strip() if isinstance(value, str) else value


def clean_code(value: str) -> str:
    """Branch code: 2-10 characters [A-Z0-9], stored in upper case (LIB-BR-01)."""
    value = value.upper()
    if not _CODE.fullmatch(value):
        raise ValueError("must be 2 to 10 characters, letters A-Z and digits 0-9")
    return value


def clean_address(value: str) -> str:
    if len(value) > _MAX_ADDRESS:
        raise ValueError("must be at most 300 characters")
    return value


Code = Annotated[str, BeforeValidator(_trim), AfterValidator(clean_code)]
Name = Annotated[str, BeforeValidator(_trim), AfterValidator(clean_name)]
Address = Annotated[str, BeforeValidator(_trim), AfterValidator(clean_address)]


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")  # unknown fields are rejected (LIB-COM-23)


class BranchCreate(StrictBody):
    code: Code
    name: Name
    address: Address


class BranchUpdate(StrictBody):
    name: Name | None = None
    address: Address | None = None
    is_active: bool | None = None

    @field_validator("name", "address", "is_active", mode="before")
    @classmethod
    def _not_null(cls, value: object) -> object:
        # Absent fields are left alone; an explicit null is not a value.
        if value is None:
            raise ValueError("must not be null")
        return value


class BranchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    address: str
    is_active: bool
    created_at: datetime.datetime
