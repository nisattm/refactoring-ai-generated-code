"""Record schemas of the JSON dataset (section 22.1), used to validate an import."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator

from lms.catalog.schemas import (
    MAX_PRICE,
    MIN_PRICE,
    AuthorIds,
    DateField,
    ShelfLocation,
    Subtitle,
    _BookChecks,
    check_barcode,
)
from lms.core.money import Money
from lms.members.schemas import MembershipTypeName, _MemberFieldChecks

FORMAT_VERSION = 1
LISTS = ("branches", "authors", "publishers", "books", "copies", "members", "loans")

Id = Annotated[StrictInt, Field(ge=1)]
Name = Annotated[str, Field(min_length=1, max_length=200)]


class _Record(BaseModel):
    """Unknown fields are rejected (LIB-IO-10); text is trimmed (LIB-COM-15)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BranchRecord(_Record):
    id: Id
    code: str
    name: Name
    address: Annotated[str, Field(max_length=300)] = ""
    is_active: StrictBool = True

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        from lms.branches.schemas import _CODE_RE

        value = value.upper()
        if not _CODE_RE.match(value):
            raise ValueError("code must be 2-10 characters from A-Z and 0-9")
        return value


class AuthorRecord(_Record):
    id: Id
    name: Name


class PublisherRecord(_Record):
    id: Id
    name: Name


class BookRecord(_BookChecks, _Record):
    id: Id
    isbn: str
    title: Name
    subtitle: Subtitle | None = None
    author_ids: AuthorIds
    publisher_id: Id
    publication_year: Annotated[StrictInt, Field(ge=1450)]
    language: str
    classification: str


class CopyRecord(_Record):
    id: Id
    book_id: Id
    barcode: str
    home_branch_id: Id
    current_branch_id: Id | None
    price: Money
    status: Literal["available", "on_loan", "damaged", "lost", "withdrawn"]
    acquired_on: DateField
    shelf_location: ShelfLocation | None = None

    @field_validator("barcode")
    @classmethod
    def _barcode(cls, value: str) -> str:
        return check_barcode(value)

    @field_validator("price")
    @classmethod
    def _price(cls, value: Decimal) -> Decimal:
        if not MIN_PRICE <= value <= MAX_PRICE:
            raise ValueError("price must be between 0.01 and 100000.00")
        return value


class MemberRecord(_MemberFieldChecks, _Record):
    id: Id
    full_name: Name
    email: str
    phone: str | None = None
    membership_type: MembershipTypeName
    university_id: str | None = None
    home_branch_id: Id
    status: Literal["active", "passive"] = "active"
    membership_start: DateField
    valid_until: DateField


class LoanRecord(_Record):
    id: Id
    copy_id: Id
    member_id: Id
    branch_id: Id
    loan_date: DateField
    due_date: DateField
    renewal_count: Annotated[StrictInt, Field(ge=0)] = 0
    status: Literal["open", "returned", "lost"]
    returned_on: DateField | None = None
    return_branch_id: Id | None = None


RECORD_MODELS: dict[str, type[_Record]] = {
    "branches": BranchRecord,
    "authors": AuthorRecord,
    "publishers": PublisherRecord,
    "books": BookRecord,
    "copies": CopyRecord,
    "members": MemberRecord,
    "loans": LoanRecord,
}

assert tuple(RECORD_MODELS) == LISTS
