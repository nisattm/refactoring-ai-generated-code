"""Request and response schemas of module 22 (section 30)."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StrictInt, field_validator, model_validator

from lms.catalog.isbn import normalize_isbn
from lms.catalog.schemas import check_barcode
from lms.core.money import Money
from lms.core.schemas import RequestModel
from lms.donations.rules import MAX_ITEMS, MAX_TOTAL_QUANTITY
from lms.members.schemas import check_email, check_phone

DonorKind = Literal["person", "organization"]
DonationStatus = Literal["offered", "accepted", "rejected", "partially_received", "received", "expired", "cancelled"]
Condition = Literal["new", "good", "fair", "poor"]
Decision = Literal["pending", "accepted", "declined"]
DeclineReason = Literal["duplicate", "poor_condition", "out_of_scope", "too_old", "other"]
DECLINE_REASONS = ("duplicate", "poor_condition", "out_of_scope", "too_old", "other")

DonorName = Annotated[str, Field(min_length=1, max_length=200)]
MIN_ESTIMATED = Decimal("0.01")
MAX_ESTIMATED = Decimal("5000.00")


# --- donors -------------------------------------------------------------------------------


class _DonorChecks:
    @field_validator("email", check_fields=False)
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        return None if value is None else check_email(value)

    @field_validator("phone", check_fields=False)
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        return check_phone(value)


class DonorCreateIn(_DonorChecks, RequestModel):
    kind: DonorKind
    name: DonorName
    email: str | None = None
    phone: str | None = None
    member_id: StrictInt | None = None
    anonymous: bool = False


class DonorPatchIn(_DonorChecks, RequestModel):
    """Any subset of the fields; ``email`` and ``phone`` may be ``null``."""

    name: DonorName = None  # type: ignore[assignment]
    email: str | None = None
    phone: str | None = None
    anonymous: bool = None  # type: ignore[assignment]
    is_active: bool = None  # type: ignore[assignment]


class MergeIn(RequestModel):
    into_donor_id: StrictInt


class DonorOut(BaseModel):
    id: int
    kind: str
    name: str
    email: str | None
    phone: str | None
    member_id: int | None
    anonymous: bool
    is_active: bool
    merged_into_id: int | None
    created_at: str
    level: str
    value_this_year: str


class YearOut(BaseModel):
    year: int
    value: str
    level: str


class HistoryOut(BaseModel):
    donor_id: int
    donations: int
    open_donations: int
    copies_received: int
    value_received: str
    first_received_on: str | None
    last_received_on: str | None
    years: list[YearOut]


class WallDonorOut(BaseModel):
    name: str
    level: str


class WallOut(BaseModel):
    year: int
    donors: list[WallDonorOut]
    anonymous_count: int


# --- offers ---------------------------------------------------------------------------------


class ItemIn(RequestModel):
    title: Annotated[str, Field(min_length=1, max_length=300)]
    author_text: Annotated[str, Field(max_length=200)] = ""
    isbn: str | None = None
    publication_year: Annotated[StrictInt, Field(ge=1450)]
    condition: Condition
    quantity: Annotated[StrictInt, Field(ge=1, le=20)]

    @field_validator("isbn")
    @classmethod
    def _isbn(cls, value: str | None) -> str | None:
        return None if value is None else normalize_isbn(value)


def _check_items(items: list[ItemIn]) -> list[ItemIn]:
    isbns = [i.isbn for i in items if i.isbn is not None]
    if len(set(isbns)) != len(isbns):
        raise ValueError("two items must not have the same ISBN")
    if sum(i.quantity for i in items) > MAX_TOTAL_QUANTITY:
        raise ValueError(f"the total quantity must be at most {MAX_TOTAL_QUANTITY}")
    return items


Items = Annotated[list[ItemIn], Field(min_length=1, max_length=MAX_ITEMS)]


class DonationCreateIn(RequestModel):
    donor_id: StrictInt | None = None
    branch_id: StrictInt
    note: Annotated[str, Field(max_length=500)] = ""
    items: Items

    @field_validator("items")
    @classmethod
    def _items(cls, value: list[ItemIn]) -> list[ItemIn]:
        return _check_items(value)


class DonationPatchIn(RequestModel):
    branch_id: StrictInt = None  # type: ignore[assignment]
    note: Annotated[str, Field(max_length=500)] = None  # type: ignore[assignment]
    items: Items = None  # type: ignore[assignment]

    @field_validator("items")
    @classmethod
    def _items(cls, value: list[ItemIn]) -> list[ItemIn]:
        return _check_items(value)


class ItemOut(BaseModel):
    id: int
    title: str
    author_text: str
    isbn: str | None
    publication_year: int
    condition: str
    quantity: int
    decision: str
    decline_reason: str | None
    book_id: int | None
    accepted_quantity: int | None
    estimated_value: str | None
    received_quantity: int


class DonationOut(BaseModel):
    id: int
    donor_id: int
    branch_id: int
    status: str
    note: str
    items: list[ItemOut]
    items_count: int
    copies_offered: int
    offered_at: str
    reviewed_at: str | None
    received_at: str | None
    expected_by: str | None
    cancel_reason: str | None
    receipt_no: str | None


# --- review -----------------------------------------------------------------------------------


class SuggestionOut(BaseModel):
    item_id: int
    decision: str | None
    decline_reason: str | None
    book_id: int | None


class SuggestionsOut(BaseModel):
    items: list[SuggestionOut]


class ReviewItemIn(RequestModel):
    item_id: StrictInt
    decision: Literal["accepted", "declined"]
    decline_reason: DeclineReason | None = None
    book_id: StrictInt | None = None
    accepted_quantity: Annotated[StrictInt, Field(ge=1)] | None = None
    estimated_value: Money | None = None

    @model_validator(mode="after")
    def _by_decision(self) -> ReviewItemIn:
        accepted_fields = (self.book_id, self.accepted_quantity, self.estimated_value)
        if self.decision == "accepted":
            if any(v is None for v in accepted_fields):
                raise ValueError("an accepted item needs book_id, accepted_quantity and estimated_value")
            if self.decline_reason is not None:
                raise ValueError("an accepted item must not have a decline_reason")
            if not MIN_ESTIMATED <= self.estimated_value <= MAX_ESTIMATED:  # type: ignore[operator]
                raise ValueError("estimated_value must be between 0.01 and 5000.00")
        else:
            if self.decline_reason is None:
                raise ValueError("a declined item needs a decline_reason")
            if any(v is not None for v in accepted_fields):
                raise ValueError("a declined item must not have book_id, accepted_quantity or estimated_value")
        return self


class ReviewIn(RequestModel):
    items: Annotated[list[ReviewItemIn], Field(min_length=1)]


# --- receiving -----------------------------------------------------------------------------------


class ReceiveItemIn(RequestModel):
    item_id: StrictInt
    barcodes: Annotated[list[str], Field(min_length=1)]

    @field_validator("barcodes")
    @classmethod
    def _barcodes(cls, value: list[str]) -> list[str]:
        return [check_barcode(v) for v in value]


class ReceiveIn(RequestModel):
    items: Annotated[list[ReceiveItemIn], Field(min_length=1)]

    @field_validator("items")
    @classmethod
    def _unique(cls, value: list[ReceiveItemIn]) -> list[ReceiveItemIn]:
        ids = [i.item_id for i in value]
        if len(set(ids)) != len(ids):
            raise ValueError("an item_id must not be repeated")
        return value


class ReceiptDonorOut(BaseModel):
    id: int
    name: str
    kind: str


class ReceiptLineOut(BaseModel):
    item_id: int
    title: str
    copies: int
    value_per_copy: str
    value: str


class ReceiptOut(BaseModel):
    receipt_no: str | None
    donor: ReceiptDonorOut
    branch_id: int
    first_received_on: str | None
    last_received_on: str | None
    lines: list[ReceiptLineOut]
    total_copies: int
    total_value: str


class ProcessOut(BaseModel):
    expired: int


# --- reports ------------------------------------------------------------------------------------


class DeclinedOut(BaseModel):
    duplicate: int
    poor_condition: int
    out_of_scope: int
    too_old: int
    other: int


class DonationReportOut(BaseModel):
    branch_id: int
    donations: int
    copies_offered: int
    copies_accepted: int
    copies_received: int
    value_received: str
    declined: DeclinedOut


class DonorReportOut(BaseModel):
    donor_id: int
    name: str
    kind: str
    value: str
    level: str
    copies: int
