"""Response schemas of module 10 (section 16)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from lms.core.pagination import Page


class MostBorrowedItemOut(BaseModel):
    rank: int
    book_id: int
    title: str
    isbn: str
    loan_count: int


class MostBorrowedOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(serialization_alias="from", validation_alias="from")
    to: str
    branch_id: int | None
    items: list[MostBorrowedItemOut]


class OverdueItemOut(BaseModel):
    loan_id: int
    member_id: int
    member_no: str
    member_name: str
    book_id: int
    title: str
    copy_barcode: str
    due_date: str
    late_days: int
    accrued_late_fee: str


class OverduePage(Page[OverdueItemOut]):
    total_accrued: str


class MonthlySummaryOut(BaseModel):
    year: int
    month: int
    branch_id: int | None
    new_members: int
    loans_created: int
    loans_returned: int
    loans_lost: int
    reservations_created: int
    reservations_fulfilled: int
    reservations_expired: int
    fees_created: str
    payments_received: str
    fees_waived: str


class InventoryItemOut(BaseModel):
    branch_id: int | None
    status: str
    copies: int


class InventoryOut(BaseModel):
    items: list[InventoryItemOut]
