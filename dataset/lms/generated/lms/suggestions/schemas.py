"""Request and response schemas of module 25 (section 33)."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StrictBool, StrictInt, field_validator, model_validator

from lms.catalog.isbn import normalize_isbn
from lms.core.money import Money
from lms.core.schemas import RequestModel
from lms.suggestions.rules import MIN_YEAR

SuggestionStatus = Literal["submitted", "approved", "ordered", "available", "rejected", "withdrawn", "merged", "expired"]
RejectReason = Literal["already_owned", "out_of_scope", "too_expensive", "not_available", "other"]
REJECT_REASONS = ("already_owned", "out_of_scope", "too_expensive", "not_available", "other")

MIN_PRICE = Decimal("0.01")
MAX_PRICE = Decimal("5000.00")

Title = Annotated[str, Field(min_length=1, max_length=300)]
AuthorText = Annotated[str, Field(max_length=200)]
Reason = Annotated[str, Field(max_length=500)]
Year = Annotated[StrictInt, Field(ge=MIN_YEAR)]
Quantity = Annotated[StrictInt, Field(ge=1, le=10)]
ReviewNote = Annotated[str, Field(max_length=500)]


def _check_price(value: Decimal) -> Decimal:
    if not MIN_PRICE <= value <= MAX_PRICE:
        raise ValueError("estimated_price must be between 0.01 and 5000.00")
    return value


class _IsbnCheck:
    @field_validator("isbn", check_fields=False)
    @classmethod
    def _isbn(cls, value: str | None) -> str | None:
        return None if value is None else normalize_isbn(value)


class SuggestIn(_IsbnCheck, RequestModel):
    member_id: StrictInt | None = None
    title: Title
    author_text: AuthorText = ""
    isbn: str | None = None
    publication_year: Year | None = None
    reason: Reason = ""
    branch_id: StrictInt


class SuggestPatchIn(_IsbnCheck, RequestModel):
    """Any subset of the fields. Only ``isbn`` and ``publication_year`` may be ``null``."""

    title: Title = None  # type: ignore[assignment]
    author_text: AuthorText = None  # type: ignore[assignment]
    isbn: str | None = None
    publication_year: Year | None = None
    reason: Reason = None  # type: ignore[assignment]
    branch_id: StrictInt = None  # type: ignore[assignment]


class SupportIn(RequestModel):
    reserve_on_arrival: StrictBool = True


class ApproveIn(RequestModel):
    book_id: StrictInt
    quantity: Quantity
    estimated_price: Money
    review_note: ReviewNote = ""

    @field_validator("estimated_price")
    @classmethod
    def _price(cls, value: Decimal) -> Decimal:
        return _check_price(value)


class ApprovalPatchIn(RequestModel):
    quantity: Quantity = None  # type: ignore[assignment]
    estimated_price: Money = None  # type: ignore[assignment]
    review_note: ReviewNote = None  # type: ignore[assignment]

    @field_validator("estimated_price")
    @classmethod
    def _price(cls, value: Decimal) -> Decimal:
        return _check_price(value)


class RejectIn(RequestModel):
    reject_reason: RejectReason
    review_note: ReviewNote = ""
    book_id: StrictInt | None = None


class MergeIn(RequestModel):
    into_suggestion_id: StrictInt


class OrderIn(RequestModel):
    supplier_id: StrictInt
    branch_id: StrictInt
    suggestion_ids: Annotated[list[StrictInt], Field(min_length=1, max_length=50)]

    @model_validator(mode="after")
    def _distinct(self) -> OrderIn:
        if len(set(self.suggestion_ids)) != len(self.suggestion_ids):
            raise ValueError("suggestion_ids must be distinct")
        return self


class SuggestionOut(BaseModel):
    """Fields a reader must not see are left unset and dropped from the response (LIB-SUG-02, LIB-SUG-12)."""

    id: int
    member_id: int | None = None
    title: str
    author_text: str
    isbn: str | None
    publication_year: int | None
    reason: str
    branch_id: int
    status: str
    reject_reason: str | None
    review_note: str
    book_id: int | None
    quantity: int | None
    estimated_price: str | None
    purchase_order_id: int | None
    merged_into_id: int | None
    withdraw_reason: str | None
    submitted_at: str
    reviewed_at: str | None
    ordered_at: str | None
    available_at: str | None
    score: int
    supporters: int
    supported_by_me: bool | None = None
    mine: bool | None = None


class SupporterOut(BaseModel):
    member_id: int
    full_name: str
    membership_type: str
    reserve_on_arrival: bool
    created_at: str


class MemberSuggestionsOut(BaseModel):
    own: list[SuggestionOut]
    supported: list[SuggestionOut]


class ProcessOut(BaseModel):
    expired_submitted: int
    expired_approved: int


class RejectedCountsOut(BaseModel):
    already_owned: int
    out_of_scope: int
    too_expensive: int
    not_available: int
    other: int


class TopOut(BaseModel):
    suggestion_id: int
    title: str
    score: int


class SuggestionReportOut(BaseModel):
    submitted: int
    approved: int
    rejected: RejectedCountsOut
    ordered: int
    available: int
    withdrawn: int
    merged: int
    expired: int
    average_days_to_available: str | None
    top: list[TopOut]


class SuggestionSummaryOut(BaseModel):
    open: int
    supported: int
    available_this_year: int
