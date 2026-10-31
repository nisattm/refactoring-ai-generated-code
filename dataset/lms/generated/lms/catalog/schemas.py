"""Request and response schemas of module 4 (section 8)."""

from __future__ import annotations

import datetime
import re
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field, StrictInt, field_validator

from lms.catalog.isbn import normalize_isbn
from lms.catalog.models import Copy
from lms.core.money import Money, format_amount
from lms.core.schemas import RequestModel
from lms.core.timeutil import format_datetime, parse_date

_LANGUAGE_RE = re.compile(r"^[a-z]{2}$")
_CLASSIFICATION_RE = re.compile(r"^[0-9]{3}(\.[0-9]{1,6})?$")
_BARCODE_RE = re.compile(r"^[A-Z0-9-]{6,20}$")

MIN_PUBLICATION_YEAR = 1450
MIN_PRICE = Decimal("0.01")
MAX_PRICE = Decimal("100000.00")

Name = Annotated[str, Field(min_length=1, max_length=200)]
Subtitle = Annotated[str, Field(max_length=200)]
ShelfLocation = Annotated[str, Field(max_length=50)]


def _date(value: object) -> object:
    if isinstance(value, str):
        return parse_date(value.strip())
    raise ValueError("expected a date in the form YYYY-MM-DD")


DateField = Annotated[datetime.date, BeforeValidator(_date)]


def _isbn(value: str) -> str:
    return normalize_isbn(value)


def _unique_authors(value: list[int]) -> list[int]:
    if len(set(value)) != len(value):
        raise ValueError("author_ids must not contain duplicates")
    return value


def _language(value: str) -> str:
    if not _LANGUAGE_RE.match(value):
        raise ValueError("language must be two lower-case letters")
    return value


def _classification(value: str) -> str:
    if not _CLASSIFICATION_RE.match(value):
        raise ValueError("classification must be three digits, optionally a dot and 1-6 digits")
    return value


def _price(value: Decimal) -> Decimal:
    if not MIN_PRICE <= value <= MAX_PRICE:
        raise ValueError("price must be between 0.01 and 100000.00")
    return value


AuthorIds = Annotated[list[StrictInt], Field(min_length=1, max_length=10)]


# --- authors and publishers ---------------------------------------------------


class NameIn(RequestModel):
    name: Name


class NamePatchIn(RequestModel):
    name: Name = None  # type: ignore[assignment]


class AuthorOut(BaseModel):
    id: int
    name: str


class PublisherOut(BaseModel):
    id: int
    name: str


# --- books ------------------------------------------------------------------------


class _BookChecks:
    @field_validator("isbn", check_fields=False)
    @classmethod
    def _isbn(cls, value: str) -> str:
        return _isbn(value)

    @field_validator("author_ids", check_fields=False)
    @classmethod
    def _authors(cls, value: list[int]) -> list[int]:
        return _unique_authors(value)

    @field_validator("language", check_fields=False)
    @classmethod
    def _language(cls, value: str) -> str:
        return _language(value)

    @field_validator("classification", check_fields=False)
    @classmethod
    def _classification(cls, value: str) -> str:
        return _classification(value)


class BookCreateIn(_BookChecks, RequestModel):
    isbn: str
    title: Name
    subtitle: Subtitle | None = None
    author_ids: AuthorIds
    publisher_id: StrictInt
    publication_year: Annotated[StrictInt, Field(ge=MIN_PUBLICATION_YEAR)]
    language: str
    classification: str


class BookPatchIn(_BookChecks, RequestModel):
    """Any subset of the create fields. Only ``subtitle`` may be ``null``."""

    isbn: str = None  # type: ignore[assignment]
    title: Name = None  # type: ignore[assignment]
    subtitle: Subtitle | None = None
    author_ids: AuthorIds = None  # type: ignore[assignment]
    publisher_id: StrictInt = None  # type: ignore[assignment]
    publication_year: Annotated[StrictInt, Field(ge=MIN_PUBLICATION_YEAR)] = None  # type: ignore[assignment]
    language: str = None  # type: ignore[assignment]
    classification: str = None  # type: ignore[assignment]


class AvailabilityOut(BaseModel):
    branch_id: int
    available: int
    total: int


class BookOut(BaseModel):
    id: int
    isbn: str
    title: str
    subtitle: str | None
    authors: list[AuthorOut]
    publisher: PublisherOut
    publication_year: int
    language: str
    classification: str
    created_at: str
    availability: list[AvailabilityOut]


# --- copies -----------------------------------------------------------------------


class CopyCreateIn(RequestModel):
    barcode: str
    home_branch_id: StrictInt
    price: Money
    acquired_on: DateField | None = None
    shelf_location: ShelfLocation | None = None

    @field_validator("barcode")
    @classmethod
    def _barcode(cls, value: str) -> str:
        return check_barcode(value)

    @field_validator("price")
    @classmethod
    def _price(cls, value: Decimal) -> Decimal:
        return _price(value)


class CopyPatchIn(RequestModel):
    """Any subset of the fields. Only ``shelf_location`` may be ``null``."""

    price: Money = None  # type: ignore[assignment]
    shelf_location: ShelfLocation | None = None
    home_branch_id: StrictInt = None  # type: ignore[assignment]

    @field_validator("price")
    @classmethod
    def _price(cls, value: Decimal) -> Decimal:
        return _price(value)


class WithdrawIn(RequestModel):
    reason: Annotated[str, Field(min_length=5, max_length=500)]


def check_barcode(value: str) -> str:
    value = value.upper()
    if not _BARCODE_RE.match(value):
        raise ValueError("barcode must be 6-20 characters from A-Z, 0-9 and -")
    return value


class CopyOut(BaseModel):
    id: int
    book_id: int
    barcode: str
    home_branch_id: int
    current_branch_id: int | None
    price: str
    status: str
    acquired_on: str
    shelf_location: str | None
    withdrawn_reason: str | None


def copy_out(copy: Copy) -> CopyOut:
    return CopyOut(
        id=copy.id,
        book_id=copy.book_id,
        barcode=copy.barcode,
        home_branch_id=copy.home_branch_id,
        current_branch_id=copy.current_branch_id,
        price=format_amount(copy.price),
        status=copy.status,
        acquired_on=copy.acquired_on.isoformat(),
        shelf_location=copy.shelf_location,
        withdrawn_reason=copy.withdrawn_reason,
    )


