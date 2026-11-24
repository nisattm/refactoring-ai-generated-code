"""Request and response schemas of module 23 (section 31)."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StrictInt, field_validator, model_validator

from lms.core.limits import MAX_REPORT_YEAR, MIN_REPORT_YEAR
from lms.core.money import Money
from lms.core.schemas import RequestModel

Condition = Literal["good", "worn", "fragile"]
JobKind = Literal["repair", "rebinding", "conservation"]
Provider = Literal["in_house", "supplier"]
Priority = Literal["normal", "urgent"]
JobStatus = Literal["requested", "approved", "sent", "returned", "cancelled", "lost"]
Outcome = Literal["repaired", "unrepairable"]

MIN_YEAR = MIN_REPORT_YEAR
MAX_YEAR = MAX_REPORT_YEAR
MAX_BUDGET = Decimal("1000000.00")
MAX_COST = Decimal("100000.00")
ZERO = Decimal("0.00")

Note = Annotated[str, Field(max_length=500)]


def _cost(value: Decimal) -> Decimal:
    if not ZERO <= value <= MAX_COST:
        raise ValueError("the cost must be between 0.00 and 100000.00")
    return value


# --- budgets -------------------------------------------------------------------------------


class BudgetIn(RequestModel):
    amount: Money

    @field_validator("amount")
    @classmethod
    def _amount(cls, value: Decimal) -> Decimal:
        if not ZERO <= value <= MAX_BUDGET:
            raise ValueError("amount must be between 0.00 and 1000000.00")
        return value


class BudgetOut(BaseModel):
    branch_id: int
    year: int
    amount: str
    committed: str
    spent: str
    available: str


# --- inspections ---------------------------------------------------------------------------


class InspectionIn(RequestModel):
    condition: Condition
    note: Note = ""


class InspectionOut(BaseModel):
    id: int
    copy_id: int
    condition: str
    note: str
    inspected_by: int
    inspected_at: str


# --- jobs ------------------------------------------------------------------------------------


class JobCreateIn(RequestModel):
    copy_id: StrictInt
    kind: JobKind
    provider: Provider
    supplier_id: StrictInt | None = None
    priority: Priority = "normal"
    estimated_cost: Money
    note: Note = ""

    @field_validator("estimated_cost")
    @classmethod
    def _estimated(cls, value: Decimal) -> Decimal:
        return _cost(value)

    @model_validator(mode="after")
    def _supplier(self) -> JobCreateIn:
        check_supplier_rule(self.provider, self.supplier_id)
        return self


def check_supplier_rule(provider: str, supplier_id: int | None) -> None:
    """LIB-PRE-08: ``supplier_id`` is required for ``supplier`` and null for ``in_house``."""
    if provider == "supplier" and supplier_id is None:
        raise ValueError("supplier_id is required for a supplier job")
    if provider == "in_house" and supplier_id is not None:
        raise ValueError("supplier_id must be null for an in-house job")


class JobPatchIn(RequestModel):
    """Any subset of the fields; ``supplier_id`` may be ``null``."""

    kind: JobKind = None  # type: ignore[assignment]
    provider: Provider = None  # type: ignore[assignment]
    supplier_id: StrictInt | None = None
    priority: Priority = None  # type: ignore[assignment]
    estimated_cost: Money = None  # type: ignore[assignment]
    note: Note = None  # type: ignore[assignment]

    @field_validator("estimated_cost")
    @classmethod
    def _estimated(cls, value: Decimal) -> Decimal:
        return _cost(value)


class ReturnIn(RequestModel):
    outcome: Outcome
    actual_cost: Money
    cost_note: Note = ""

    @field_validator("actual_cost")
    @classmethod
    def _actual(cls, value: Decimal) -> Decimal:
        return _cost(value)


class JobOut(BaseModel):
    id: int
    copy_id: int
    barcode: str
    book_title: str
    branch_id: int
    kind: str
    provider: str
    supplier_id: int | None
    priority: str
    estimated_cost: str
    actual_cost: str | None
    status: str
    outcome: str | None
    loan_id: int | None
    shipment_id: int | None
    note: str
    cost_note: str
    cost_overrun: bool
    requested_at: str
    approved_at: str | None
    sent_at: str | None
    returned_at: str | None
    due_back: str | None
    cancel_reason: str | None
    overdue_marked_at: str | None
    is_overdue: bool
    claim_amount: str | None


# --- shipments -------------------------------------------------------------------------------


class ShipmentIn(RequestModel):
    supplier_id: StrictInt
    job_ids: Annotated[list[StrictInt], Field(min_length=1, max_length=50)]

    @field_validator("job_ids")
    @classmethod
    def _distinct(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value):
            raise ValueError("job_ids must be distinct")
        return value


class ShipmentOut(BaseModel):
    id: int
    code: str
    supplier_id: int
    branch_id: int
    job_ids: list[int]
    open_jobs: int
    sent_at: str


# --- processing, suggestions, reports ----------------------------------------------------------


class ProcessOut(BaseModel):
    overdue: int
    newly_overdue: int
    expired_requests: int


class SuggestionOut(BaseModel):
    copy_id: int
    barcode: str
    reason: str


class SuggestionsOut(BaseModel):
    items: list[SuggestionOut]


class PreservationReportOut(BaseModel):
    branch_id: int
    budget: str | None
    committed: str
    spent: str
    jobs_returned: int
    repaired: int
    unrepairable: int
    lost: int
    average_days: str | None
    overdue_now: int


class RecoveryOut(BaseModel):
    job_id: int
    copy_id: int
    loan_id: int
    member_id: int
    damage_fee: str
    actual_cost: str
    difference: str


class RecoveryTotalsOut(BaseModel):
    damage_fees: str
    costs: str
    difference: str


class RecoveryPage(BaseModel):
    items: list[RecoveryOut]
    page: int
    page_size: int
    total: int
    totals: RecoveryTotalsOut
